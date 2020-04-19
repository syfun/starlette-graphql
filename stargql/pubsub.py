import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict, Tuple

from .pubsub_async_iterator import PubSubEngine


class EventEmitter:
    events: Dict[str, Dict[int, Callable]]
    queue: asyncio.Queue
    run_task: asyncio.Task

    def __init__(self):
        self.events = defaultdict(dict)
        self.queue = asyncio.Queue()

    async def _run(self):
        while True:
            item = await self.queue.get()
            self.queue.task_done()
            if item == 'stop':
                break

            event = item.get('event')
            args = item.get('args')
            if event not in self.events:
                continue

            for listener in self.events[event].values():
                result = listener(*args)
                if asyncio.iscoroutine(result):
                    await result

    async def stop(self):
        await self.queue.put('stop')

    def add_listener(self, event: str, listener: Callable) -> None:
        self.events[event][hash(listener)] = listener

    def remove_listener(self, event, listener: Callable) -> None:
        self.events[event].pop(hash(listener), None)

    async def emit(self, event: str, *args: Any) -> None:
        # Delay run when first emit, why not do this in init?
        # asyncio.create_task need a running loop, but on common case,
        # not have a running loop when init EventEmitter
        self.run_task = asyncio.create_task(self._run())
        await self.queue.put({'event': event, 'args': args})


class PubSub(PubSubEngine):
    emitter: EventEmitter
    subscriptions: Dict[int, Tuple[str, Callable]]
    current_sub_id: int = 0

    def __init__(self):
        self.emitter = EventEmitter()
        self.subscriptions = {}

    async def publish(self, trigger_name: str, payload: Any) -> None:
        await self.emitter.emit(trigger_name, payload)

    async def subscribe(self, trigger_name: str, on_message: Callable, options: dict) -> int:
        self.emitter.add_listener(trigger_name, on_message)
        self.current_sub_id += 1
        self.subscriptions[self.current_sub_id] = (trigger_name, on_message)
        return self.current_sub_id

    async def unsubscribe(self, sub_id: int) -> None:
        if sub_id not in self.subscriptions:
            return

        trigger_name, on_message = self.subscriptions.pop(sub_id)
        self.emitter.remove_listener(trigger_name, on_message)

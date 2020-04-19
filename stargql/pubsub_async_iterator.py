import asyncio
from typing import Any, Callable, Union, List, AsyncIterator, TypeVar


try:
    from typing import Protocol
except ImportError:
    from typing_extensions import Protocol


class PubSubEngine(Protocol):
    async def publish(self, trigger_name: str, payload: Any) -> None:
        ...

    async def subscribe(self, trigger_name: str, on_message: Callable, options: dict) -> int:
        ...

    async def unsubscribe(self, sub_id: int) -> None:
        ...

    def async_iterator(self, triggers: Union[str, List[str]]) -> 'PubSubAsyncIterator':
        return PubSubAsyncIterator(self, triggers)


T = TypeVar('T')


class PubSubAsyncIterator(AsyncIterator[T]):
    pubsub: PubSubEngine
    running: bool
    push_queue: asyncio.Queue
    pull_queue: List[asyncio.Task]
    triggers: List[str]

    all_subscribed: asyncio.Task = None

    def __init__(self, pubsub: PubSubEngine, triggers: Union[str, List[str]]):
        self.pubsub = pubsub
        self.running = True
        self.triggers = triggers if isinstance(triggers, List) else [triggers]
        # self.options = options
        self.push_queue = asyncio.Queue()
        self.pull_queue = []

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        if not self.running:
            await self.empty_queue()
            raise StopAsyncIteration()

        if not self.all_subscribed:
            self.all_subscribed = asyncio.create_task(self.subscribe_all())
            await self.all_subscribed
        return await self.pull_value()

    async def close(self):
        await self.empty_queue()

    async def pull_value(self):
        value = await self.push_queue.get()
        if value == 'stop':
            raise StopAsyncIteration()
        return value

    # def pull_value(self) -> asyncio.Task:
    #     async def pull() -> T:
    #         value = await self.push_queue.get()
    #         self.push_queue.task_done()
    #         return value
    #
    #     task = asyncio.create_task(pull())
    #     self.pull_queue.append(task)
    #     return task

    async def push_value(self, event: T) -> None:
        await self.push_queue.put(event)

    async def subscribe_all(self) -> List[int]:
        return [
            await self.pubsub.subscribe(trigger, self.push_value, {}) for trigger in self.triggers
        ]

    async def unsubscribe_all(self, subscription_ids: List[int]) -> None:
        if not subscription_ids:
            return
        for subscription_id in subscription_ids:
            await self.pubsub.unsubscribe(subscription_id)

    async def empty_queue(self) -> None:
        if not self.running:
            return

        self.running = False
        await self.push_queue.put('stop')
        # if self.pull_queue:
        #     for task in self.pull_queue:
        #         task.cancel()
        #     await asyncio.gather(self.pull_queue)
        subscription_ids = await self.all_subscribed
        await self.unsubscribe_all(subscription_ids)

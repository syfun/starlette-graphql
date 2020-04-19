import json
from typing import Any, AsyncIterator, Callable, Optional, Dict

import aioredis


class RedisPubSub:
    _instance = None

    """Dumps publish payload, if none, use json.dumps"""
    dumps: Callable
    backend: Optional[aioredis.Redis] = None
    channels: Dict[str, aioredis.Channel] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> 'RedisPubSub':
        if not cls._instance:
            cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self, address: str, dumps: Callable = None) -> None:
        self.address = address
        self.dumps = dumps

    async def connect(self) -> None:
        self.backend = await aioredis.create_redis_pool(self.address)

    async def disconnect(self) -> None:
        self.backend.close()
        await self.backend.wait_closed()

    async def publish(self, trigger: str, payload: dict) -> None:
        if not self.channels:
            return
        channel = self.channels.get(trigger)
        if channel:
            dumps = self.dumps or json.dumps
            await self.backend.publish(channel, dumps(payload))

    async def subscribe(self, trigger_name: str, on_message: Callable, options: dict) -> int:
        channel = await self.backend.subscribe(trigger_name)

    def unsubscribe(self, sub_id: int) -> None:
        return

    def async_iterator(self, *triggers: str, options: Any = None) -> AsyncIterator:
        channels = await self.backend.subscribe(*triggers)

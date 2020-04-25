import asyncio
import inspect
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Dict, Sequence

from gql.subscription import PROTOCOL, MessageType, OperationMessage
from graphql import ExecutionResult, GraphQLError, GraphQLSchema, format_error, parse, subscribe
from starlette import status
from starlette.authentication import BaseUser
from starlette.types import Receive, Scope, Send
from starlette.websockets import Message, WebSocket


def create_async_iterator(seq: Sequence[Any]):
    async def inner():
        for i in seq:
            yield i

    return inner


@dataclass
class ConnectionContext:
    socket: WebSocket
    operations: Dict[str, AsyncIterator[ExecutionResult]]
    user: BaseUser = None


class Subscription:
    schema: GraphQLSchema
    keep_alive: bool
    authenticate: Awaitable

    def __init__(self, schema: GraphQLSchema, keep_alive: bool = False, authenticate: Awaitable = None) -> None:
        self.schema = schema
        self.keep_alive = keep_alive
        self.authenticate = authenticate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        socket = WebSocket(scope, receive=receive, send=send)
        await self.on_connect(socket)

        context = ConnectionContext(socket=socket, operations={})
        await self.on_message(context)

    async def on_connect(self, socket: WebSocket) -> None:
        await socket.accept(PROTOCOL)

    async def on_disconnect(self, socket: WebSocket, close_code: int) -> None:
        await socket.close(close_code)

    async def on_message(self, context: ConnectionContext) -> None:
        close_code = status.WS_1000_NORMAL_CLOSURE
        try:
            while True:
                message = await context.socket.receive()
                if message["type"] == "websocket.receive":
                    await self.dispatch(context, message)
                elif message["type"] == "websocket.disconnect":
                    close_code = int(message.get("code", status.WS_1000_NORMAL_CLOSURE))
                    # To fix shutdown server 1006 error.
                    if close_code == 1006:
                        close_code = status.WS_1000_NORMAL_CLOSURE
                    break
        except Exception as exc:
            close_code = status.WS_1011_INTERNAL_ERROR
            raise exc from None
        finally:
            await self.on_disconnect(context.socket, close_code)

    async def unsubscribe(self, context: ConnectionContext, op_id: str) -> None:
        if op_id not in context.operations:
            return

        op = context.operations[op_id]
        close_func = getattr(op, 'aclose')
        if inspect.isfunction(close_func):
            close_func()
        elif inspect.iscoroutinefunction(close_func):
            await close_func()

        context.operations.pop(op_id)

    async def unsubscribe_all(self, context: ConnectionContext) -> None:
        for op_id in context.operations:
            await self.unsubscribe(context, op_id)

    async def dispatch(self, context: ConnectionContext, data: Message) -> None:
        message = await self.decode(context, data)
        op_id = message.id
        if message.type == MessageType.GQL_CONNECTION_INIT:
            await self.init(context, message)
        elif message.type == MessageType.GQL_CONNECTION_TERMINATE:
            await context.socket.close(code=status.WS_1000_NORMAL_CLOSURE)
        elif message.type == MessageType.GQL_START:
            try:
                await self.start(context, message)
            except Exception as exc:
                await self.send_error(context, op_id, {'message': str(exc)})
                await self.unsubscribe(context, op_id)
        elif message.type == MessageType.GQL_STOP:
            await self.unsubscribe(context, op_id)
        else:
            await self.send_error(context, op_id, {'message': 'Invalid message type!'})

    async def init(self, context: ConnectionContext, message: OperationMessage) -> None:
        if self.authenticate:
            context.user = user = await self.authenticate(message.payload)
            if not user.is_authenticated:
                await self.send_error(
                    context,
                    message.id,
                    {'message': 'Invalid auth credentials.'},
                    error_type=MessageType.GQL_CONNECTION_ERROR,
                )
                return

        await self.send_message(context, MessageType.GQL_CONNECTION_ACK)
        # TODO: to support keep_alive

    async def start(self, context: ConnectionContext, message: OperationMessage) -> None:
        if context.user and not context.user.is_authenticated:
            await self.send_error(context, message.id, {'message': 'Invalid auth credentials.'})
            return

        op_id = message.id
        # if we already have a subscription with this id, unsubscribe from it first
        if op_id in context.operations:
            await self.unsubscribe(context, op_id)

        payload = message.payload
        try:
            doc = parse(payload.query)
        except Exception as exc:
            if isinstance(exc, GraphQLError):
                await self.send_execution_result(context, op_id, ExecutionResult(data=None, errors=[exc]))
            else:
                await self.send_error(context, op_id, {'message': str(exc)})
            return

        result_or_iterator = await subscribe(
            self.schema,
            doc,
            variable_values=payload.variables,
            context_value=context,
            operation_name=payload.operation_name,
        )
        if isinstance(result_or_iterator, ExecutionResult):
            result_or_iterator = create_async_iterator([result_or_iterator])

        context.operations[op_id] = result_or_iterator

        async def iter_result():
            async for result in result_or_iterator:
                await self.send_execution_result(context, op_id, result)

            await self.send_message(context, MessageType.GQL_COMPLETE, op_id=op_id)

        asyncio.create_task(iter_result())

    async def send_execution_result(self, context: ConnectionContext, op_id: str, result: ExecutionResult) -> None:
        payload = {
            'data': result.data,
            'errors': [format_error(error) for error in result.errors] if result.errors else None,
        }
        await self.send_message(
            context, MessageType.GQL_DATA, op_id=op_id, payload=payload,
        )

    async def send_message(
        self, context: ConnectionContext, message_type: MessageType, op_id: str = None, payload: dict = None,
    ) -> None:
        data = {'type': message_type.value}
        if op_id:
            data['id'] = op_id
        if payload:
            data['payload'] = payload
        await context.socket.send_json(data)

    async def send_error(
        self,
        context: ConnectionContext,
        op_id: str = None,
        playload: dict = None,
        error_type: MessageType = MessageType.GQL_ERROR,
    ):
        assert error_type in [MessageType.GQL_ERROR, MessageType.GQL_CONNECTION_ERROR]
        await self.send_message(context, error_type, op_id, payload=playload)

    async def send_keep_alive(self, context: ConnectionContext) -> None:
        await self.send_message(context, MessageType.GQL_CONNECTION_KEEP_ALIVE)

    async def decode(self, context: ConnectionContext, message: Message) -> OperationMessage:
        if message.get("text") is not None:
            text = message["text"]
        else:
            text = message["bytes"].decode("utf-8")

        try:
            return OperationMessage.build(json.loads(text))
        except json.decoder.JSONDecodeError as exc:
            await self.send_error(context, None, {'message': str(exc)}, MessageType.GQL_CONNECTION_ERROR)

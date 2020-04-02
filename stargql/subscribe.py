import asyncio
import json
from dataclasses import dataclass
from typing import Dict

from graphql import ExecutionResult, GraphQLError, GraphQLSchema, format_error, parse, subscribe
from starlette import status
from starlette.types import Receive, Scope, Send
from starlette.websockets import Message, WebSocket

from gql.subscribe import PROTOCOL, MessageType, OperationMessage


@dataclass
class ConnectionContext:
    socket: WebSocket
    operations: Dict[str, asyncio.Future]


class Subscription:
    schema: GraphQLSchema

    def __init__(self, schema: GraphQLSchema) -> None:
        self.schema = schema

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        socket = WebSocket(scope, receive=receive, send=send)
        await socket.accept(PROTOCOL)

        context = ConnectionContext(socket=socket, operations={})
        await self.on_message(context)

    async def on_message(self, context: ConnectionContext) -> None:
        close_code = status.WS_1000_NORMAL_CLOSURE
        try:
            while True:
                message = await context.socket.receive()
                if message["type"] == "websocket.receive":
                    await self.dispatch(context, message)
                elif message["type"] == "websocket.disconnect":
                    close_code = int(message.get("code", status.WS_1000_NORMAL_CLOSURE))
                    break
        except Exception as exc:
            close_code = status.WS_1011_INTERNAL_ERROR
            raise exc from None
        finally:
            await context.socket.close(close_code)

    async def dispatch(self, context: ConnectionContext, data: Message) -> None:
        message = await self.decode(context, data)
        if message.type == MessageType.GQL_CONNECTION_INIT:
            await self.init(context)
        elif message.type == MessageType.GQL_CONNECTION_TERMINATE:
            await self.terminate(context)
        elif message.type == MessageType.GQL_START:
            future = asyncio.ensure_future(self.start(context, message))
            context.operations[message.id] = future
        elif message.type == MessageType.GQL_STOP:
            await self.stop(context, message.id)
        else:
            for op in context.operations.values():
                op.cancel()
            await context.socket.close(code=status.WS_1003_UNSUPPORTED_DATA)

    async def init(self, context: ConnectionContext) -> None:
        await self.send_message(context, MessageType.GQL_CONNECTION_ACK)

    async def stop(self, context: ConnectionContext, op_id: str) -> None:
        if op_id in context.operations:
            op = context.operations[op_id]
            op.cancel()
            self.unsubscribe(context, op_id)
        await self.complete(context, op_id)

    async def terminate(self, context: ConnectionContext) -> None:
        for op in context.operations.values():
            op.cancel()
        await context.socket.close(code=status.WS_1000_NORMAL_CLOSURE)

    async def complete(self, context: ConnectionContext, op_id: str) -> None:
        await self.send_message(context, MessageType.GQL_COMPLETE, op_id=op_id)

    async def start(self, context: ConnectionContext, message: OperationMessage) -> None:
        # if message.id in self.operations:
        #     await self.unsubscribe(op_id=message.id)
        payload = message.payload
        assert payload
        try:
            doc = parse(payload.query)
        except GraphQLError as error:
            await self.send_execution_result(message.id, ExecutionResult(data=None, errors=[error]))
            return

        result_or_iterator = await subscribe(
            self.schema,
            doc,
            variable_values=payload.variables,
            operation_name=payload.operation_name,
        )
        if isinstance(result_or_iterator, ExecutionResult):
            await self.send_execution_result(context, message.id, result_or_iterator)
            return

        async for result in result_or_iterator:
            await self.send_execution_result(context, message.id, result)

        await self.complete(context, message.id)

    def unsubscribe(self, context: ConnectionContext, op_id: str) -> None:
        context.operations.pop(op_id, None)

    async def send_execution_result(
        self, context: ConnectionContext, op_id: str, result: ExecutionResult
    ) -> None:
        payload = {
            'data': result.data,
            'errors': [format_error(error) for error in result.errors] if result.errors else None,
        }
        await self.send_message(
            context, MessageType.GQL_DATA, op_id=op_id, payload=payload,
        )

    async def send_message(
        self, context: ConnectionContext, type: MessageType, op_id: str = None, payload: dict = None
    ) -> None:
        data = {'type': type.value}
        if op_id:
            data['id'] = op_id
        if payload:
            data['payload'] = payload
        await context.socket.send_json(data)

    async def decode(self, context: ConnectionContext, message: Message) -> OperationMessage:
        if message.get("text") is not None:
            text = message["text"]
        else:
            text = message["bytes"].decode("utf-8")

        try:
            return OperationMessage.build(json.loads(text))
        except json.decoder.JSONDecodeError:
            await context.socket.close(code=status.WS_1003_UNSUPPORTED_DATA)
            raise RuntimeError("Malformed JSON data received.")

import json
import traceback
import typing

from gql import make_schema, make_schema_from_file
from gql.playground import PLAYGROUND_HTML
from gql.resolver import default_field_resolver, register_resolvers
from gql.utils import place_files_in_operations
from graphql import GraphQLError, GraphQLSchema, graphql, Middleware
from starlette import status
from starlette.applications import Starlette
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.types import Receive, Scope, Send

from .subscription import Subscription

ERROR_FORMATER = typing.Callable[[GraphQLError], typing.Dict[str, typing.Any]]


class GraphQL(Starlette):
    def __init__(
        self,
        schema: GraphQLSchema = None,
        *,
        type_defs: str = None,
        schema_file: str = None,
        federation: bool = False,
        playground: bool = True,
        debug: bool = False,
        routes: typing.List[BaseRoute] = None,
        path: str = '/',
        subscription_path: str = '/',
        subscription_authenticate: typing.Awaitable = None,
        error_formater: ERROR_FORMATER = None,
        graphql_middleware: Middleware = None,
        context_builder: typing.Callable = None,
        **kwargs,
    ):
        routes = routes or []
        if schema:
            self.schema = schema
        elif type_defs:
            self.schema = make_schema(type_defs, federation=federation)
        elif schema_file:
            self.schema = make_schema_from_file(schema_file, federation=federation)
        else:
            raise Exception('Must provide type def string or file.')
        register_resolvers(self.schema)

        routes.extend(
            [
                Route(
                    path,
                    ASGIApp(
                        self.schema,
                        debug=debug,
                        playground=playground,
                        error_formater=error_formater,
                        graphql_middleware=graphql_middleware,
                        context_builder=context_builder,
                    ),
                ),
                WebSocketRoute(
                    subscription_path,
                    Subscription(self.schema, authenticate=subscription_authenticate),
                ),
            ]
        )
        super().__init__(debug=debug, routes=routes, **kwargs)


class ASGIApp:
    def __init__(
        self,
        schema: GraphQLSchema,
        debug: bool = False,
        playground: bool = True,
        error_formater: ERROR_FORMATER = None,
        graphql_middleware: Middleware = None,
        context_builder: typing.Callable = None,
    ) -> None:
        self.schema = schema
        self.playground = playground
        self.error_formater = self.format_error
        self.debug = debug
        self.middleware = graphql_middleware
        self.context_builder = context_builder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive, send=send)
        response = await self.handle_graphql(request)
        await response(scope, receive, send)

    def format_error(self, error: GraphQLError) -> typing.Dict[str, typing.Any]:
        if not error:
            raise ValueError("Received null or undefined error.")
        formatted = dict(  # noqa: E701 (pycqa/flake8#394)
            message=error.message or "An unknown error occurred.",
            locations=[l._asdict() for l in error.locations] if error.locations else None,
            path=error.path,
        )
        if self.debug and error.original_error:
            original_error = error.original_error
            exception = error.extensions.get('exception', {})
            exception['traceback'] = traceback.format_exception(
                type(original_error), original_error, original_error.__traceback__
            )
            error.extensions['exception'] = exception
        if error.extensions:
            formatted.update(extensions=error.extensions)
        return formatted

    async def handle_graphql(self, request: Request) -> Response:
        if request.method in ('GET', 'HEAD'):
            if 'text/html' in request.headers.get('Accept', ''):
                if not self.playground:
                    return PlainTextResponse('Not Found', status_code=status.HTTP_404_NOT_FOUND)
                return HTMLResponse(PLAYGROUND_HTML)

            data = request.query_params  # type: typing.Mapping[str, typing.Any]

        elif request.method == 'POST':
            content_type = request.headers.get('Content-Type', '')

            if 'application/json' in content_type:
                data = await request.json()
            elif 'application/graphql' in content_type:
                body = await request.body()
                data = {'query': body.decode()}
            elif 'query' in request.query_params:
                data = request.query_params
            elif 'multipart/form-data' in content_type:
                form = await request.form()
                try:
                    operations = json.loads(form.get('operations', '{}'))
                    files_map = json.loads(form.get('map', '{}'))
                except (TypeError, ValueError):
                    return PlainTextResponse(
                        'operations or map sent invalid JSON',
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                data = place_files_in_operations(operations, files_map, form)
            else:
                return PlainTextResponse(
                    'Unsupported Media Type', status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                )
        else:
            return PlainTextResponse(
                'Method Not Allowed', status_code=status.HTTP_405_METHOD_NOT_ALLOWED
            )

        try:
            query = data['query']
            variables = data.get('variables')
            operation_name = data.get('operationName')
        except KeyError:
            return PlainTextResponse(
                'No GraphQL query found in the request', status_code=status.HTTP_400_BAD_REQUEST,
            )

        background = BackgroundTasks()
        context = self.context_builder() if self.context_builder else {}
        context.update(request=request, background=background)

        result = await graphql(
            self.schema,
            query,
            variable_values=variables,
            operation_name=operation_name,
            context_value=context,
            field_resolver=default_field_resolver,
            middleware=self.middleware,
        )
        error_data = [self.error_formater(err) for err in result.errors] if result.errors else None
        response_data = {'data': result.data, 'errors': error_data}
        # status_code = status.HTTP_400_BAD_REQUEST if result.errors else status.HTTP_200_OK

        return JSONResponse(response_data, status_code=status.HTTP_200_OK, background=background)

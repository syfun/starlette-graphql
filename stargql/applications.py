import json
import typing

from gql.build_schema import build_schema, build_schema_from_file
from gql.playground import PLAYGROUND_HTML
from gql.resolver import register_resolvers, default_field_resolver
from gql.utils import place_files_in_operations
from graphql import GraphQLSchema, format_error, graphql
from starlette import status
from starlette.applications import Starlette
from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.types import Receive, Scope, Send

from .subscription import Subscription


class GraphQL(Starlette):
    def __init__(
        self,
        *,
        type_defs: str = None,
        schema_file: str = None,
        playground: bool = True,
        debug: bool = False,
        routes: typing.List[BaseRoute] = None,
        path: str = '/',
        subscription_path: str = '/',
        **kwargs,
    ):
        routes = routes or []
        if type_defs:
            self.schema = build_schema(type_defs)
        elif schema_file:
            self.schema = build_schema_from_file(schema_file)
        else:
            raise Exception('Must provide type def string or file.')
        register_resolvers(self.schema)

        routes.extend(
            [
                Route(path, ASGIApp(self.schema, playground=playground)),
                WebSocketRoute(subscription_path, Subscription(self.schema)),
            ]
        )
        super().__init__(debug=debug, routes=routes, **kwargs)


class ASGIApp:
    def __init__(self, schema: GraphQLSchema, playground: bool = True) -> None:
        self.schema = schema
        self.playground = playground

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive=receive, send=send)
        response = await self.handle_graphql(request)
        await response(scope, receive, send)

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
        context = {'request': request, 'background': background}

        result = await graphql(
            self.schema,
            query,
            variable_values=variables,
            operation_name=operation_name,
            context_value=context,
            field_resolver=default_field_resolver,
        )
        error_data = [format_error(err) for err in result.errors] if result.errors else None
        response_data = {'data': result.data, 'errors': error_data}
        status_code = status.HTTP_400_BAD_REQUEST if result.errors else status.HTTP_200_OK

        return JSONResponse(response_data, status_code=status_code, background=background)

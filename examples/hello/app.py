import uvicorn

from gql import query
from stargql import GraphQL


@query
async def hello(parent, info, name: str) -> str:
    return name


app = GraphQL(schema_file='schema.gql')

if __name__ == '__main__':
    uvicorn.run(app, port=8080)

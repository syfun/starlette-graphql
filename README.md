# Starlette GraphQL

The starlette GraphQL implement, which  support query, mutate and subscription. Based on [python-gql](https://github.com/syfun/python-gql).

## Requirement

Python 3.7+

## Installation

`pip install starlette-graphql`


## Getting started

```python
# app.py
from gql import query, gql
from stargql import GraphQL

type_defs = gql("""
type Query {
    hello(name: String!): String!
}
""")


@query
async def hello(parent, info, name: str) -> str:
    return name


app = GraphQL(type_defs=type_defs)
```

Use [uvicorn](https://www.uvicorn.org) to run app.

`uvicorn app:app --reload`

## Upload File

```python
import uvicorn
from gql import gql, mutate
from stargql import GraphQL

type_defs = gql("""
 scalar Upload
 
 type File {
    filename: String!
  }

  type Query {
    uploads: [File]
  }

  type Mutation {
    singleUpload(file: Upload!): File!
    multiUpload(files: [Upload!]!): [File!]!
  }
""")


@mutate
def single_upload(parent, info, file):
    return file


@mutate
def multi_upload(parent, info, files):
    return files


app = GraphQL(type_defs=type_defs)


if __name__ == '__main__':
    uvicorn.run(app, port=8080)

```

## Subscription

For more about subscription, please see [gql-subscriptions](https://github.com/syfun/starlette-graphql).

## Apollo Federation

[Example](https://github.com/syfun/starlette-graphql/tree/master/examples/federation)

For more abount subscription, please see [Apollo Federation](https://www.apollographql.com/docs/apollo-server/federation/introduction/)

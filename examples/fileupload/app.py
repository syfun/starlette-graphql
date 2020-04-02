import uvicorn

from gql import gql, mutate
from stargql import GraphQL

type_defs = gql(
    """
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
"""
)


@mutate
def single_upload(parent, info, file):
    return file


@mutate
def multi_upload(parent, info, files):
    return files


app = GraphQL(type_defs=type_defs)


if __name__ == '__main__':
    uvicorn.run(app, port=8080)

import uvicorn

from gql import gql, reference_resolver, query
from stargql import GraphQL

from helper import get_user_by_id, users

type_defs = gql("""
  type Query {
    me: User
  }

  type User @key(fields: "id") {
    id: ID!
    name: String
    username: String
  }

""")

@query('me')
def get_me(_, info):
    return users[0]


@reference_resolver('User')
def user_reference(_, info, representation):
    return get_user_by_id(representation['id'])


app = GraphQL(type_defs=type_defs, federation=True)

if __name__ == '__main__':
    uvicorn.run(app, port=8082)

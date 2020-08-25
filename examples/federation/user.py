import uvicorn

from gql import gql, reference_resolver
from stargql import GraphQL

type_defs = gql("""
  type Query {
    me: User
  }

  type User @key(fields: "id") {
    id: ID!
    username: String
  }

""")

users = {
    '1': {'id': '1', 'username': 'Jack'},
    '2': {'id': '2', 'username': 'Rose'}
}
@reference_resolver('User')
def user_reference(_, info, representation):
    return users.get(representation['id'])



app = GraphQL(type_defs=type_defs, federation=True)

if __name__ == '__main__':
    uvicorn.run(app, port=8080)

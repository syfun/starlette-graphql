import uvicorn

from gql import gql, reference_resolver, field_resolver
from stargql import GraphQL

from .helper import get_review_by_id

type_defs = gql('''
type Query {
    reviews(first: Int = 5): [Review]
  }

  type Review @key(fields: 'id') {
    id: ID!
    body: String
    author: User @provides(fields: 'email')
    product: Product @provides(fields: 'upc')
  }

  type User @key(fields: 'email') @extends {
    email: String! @external
    reviews: [Review]
  }

  type Product @key(fields: 'upc') @extends {
    upc: String! @external
    reviews: [Review]
  }
''')


@reference_resolver('Review')
def resolve_reviews_reference(_, _info, representation):
    return get_review_by_id(representation['id'])


@field_resolver('Review', 'author')
def resolve_review_author(review, *_):
    return {'email': review['user']['email']}


@field_resolver('Review', 'product')
def resolve_review_product(review, *_):
    return {'upc': review['product']['upc']}


@field_resolver('User', 'review')
def resolve_user_reviews(representation, *_):
    return get_user_reviews(representation['email'])


@field_resolver('Product', 'review')
def resolve_product_reviews(representation, *_):
    return get_product_reviews(representation['upc'])


app = GraphQL(type_defs=type_defs, federation=True)

if __name__ == '__main__':
    uvicorn.run(app, port=8080)

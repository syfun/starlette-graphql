import uvicorn

from gql import gql, reference_resolver, field_resolver, query
from stargql import GraphQL

from helper import get_review_by_id, get_user_reviews, get_product_reviews, reviews

type_defs = gql(
    '''
type Query {
    reviews(first: Int = 5): [Review]
  }

  type Review @key(fields: "id") {
    id: ID!
    body: String
    author: User @provides(fields: "username")
    product: Product @provides(fields: "upc")
  }

  type User @key(fields: "id") @extends {
    id: ID! @external
    username: String @external
    reviews: [Review]
  }

  type Product @key(fields: "upc") @extends {
    upc: String! @external
    reviews: [Review]
  }
'''
)


@query('reviews')
def list_reviews(_, info, first: int = 5):
    return reviews[:first]


@reference_resolver('Review')
def resolve_reviews_reference(_, info, representation):
    return get_review_by_id(representation['id'])


@field_resolver('Review', 'author')
def resolve_review_author(review, *_):
    return {'id': review['authorID']}


@field_resolver('Review', 'product')
def resolve_review_product(review, *_):
    return {'upc': review['product']['upc']}


@field_resolver('User', 'reviews')
def resolve_user_reviews(representation, *_):
    return get_user_reviews(representation['id'])


@field_resolver('Product', 'reviews')
def resolve_product_reviews(representation, *_):
    return get_product_reviews(representation['upc'])


app = GraphQL(type_defs=type_defs, federation=True)

if __name__ == '__main__':
    uvicorn.run(app, port=8083)

import uvicorn
from gql import gql, query, reference_resolver

from stargql import GraphQL

from helper import get_production_by_upc, products

type_defs = gql(
    """
  type Query {
    topProducts(first: Int = 5): [Product]
  }
  type Product @key(fields: "upc") {
    upc: String!
    name: String
    price: Int
    weight: Int
  }
"""
)


@reference_resolver('Product')
def user_reference(_, info, representation):
    return get_production_by_upc(representation['upc'])


@query('topProducts')
def top_products(_, info, first: int = 5):
    return products[:first]


app = GraphQL(type_defs=type_defs, federation=True)

if __name__ == '__main__':
    uvicorn.run(app, port=8081)

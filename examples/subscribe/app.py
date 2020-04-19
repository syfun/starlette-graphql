import asyncio

import uvicorn
from gql import gql, query, subscribe, mutate

from stargql import GraphQL
from stargql.pubsub import PubSub

type_defs = gql(
    """
  type Subscription {
    postAdded: Post
  }

  type Query {
    posts: [Post]
  }

  type Mutation {
    addPost(author: String, comment: String): Post
  }

  type Post {
    author: String
    comment: String
  }
"""
)


class Ticker:
    def __init__(self, delay, is_stop=False):
        self.delay = delay
        self.is_stop = is_stop

    def __aiter__(self):
        return self

    def stop(self):
        self.is_stop = True

    async def __anext__(self):
        if self.is_stop:
            raise StopAsyncIteration()
        await asyncio.sleep(self.delay)
        if self.is_stop:
            raise StopAsyncIteration()
        return {'postAdded': {'author': 'Jack', 'comment': 'Good'}}


async def ticker(delay, to):
    """Yield numbers from 0 to `to` every `delay` seconds."""
    for i in range(to):
        await asyncio.sleep(delay)
        yield {'postAdded': {'author': 'Jack', 'comment': 'Good'}}


pubsub = PubSub()


@query
def posts(parent, info):
    return [{'author': 'Jack', 'comment': 'Good!'}]


@subscribe
async def post_added(parent, info, *args):
    return pubsub.async_iterator('POST_ADDED')


@mutate
async def add_post(parent, info, **kwargs):
    await pubsub.publish('POST_ADDED', {'postAdded': kwargs})
    return kwargs


app = GraphQL(type_defs=type_defs)


if __name__ == '__main__':
    uvicorn.run(app, port=8080)

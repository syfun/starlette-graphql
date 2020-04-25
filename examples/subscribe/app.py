from functools import wraps
from typing import Callable, Awaitable, AsyncIterator, Any, Dict

import uvicorn
from gql import gql, subscribe, mutate
from gql_subscriptions.pubsubs.redis import RedisPubSub
from stargql import GraphQL

# from gql.pubsub import PubSub

type_defs = gql(
    """
  type Subscription {
    postAdded(author: String): Post
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

pubsub = RedisPubSub('redis://localhost:6379')

ResolverFn = Callable[[Any, Any, Dict[str, Any]], Awaitable[AsyncIterator]]
FilterFn = Callable[[Any, Any, Dict[str, Any]], bool]


def with_filter(filter_fn: FilterFn,) -> Callable[[ResolverFn], ResolverFn]:
    def wrap(func: ResolverFn) -> ResolverFn:
        @wraps(func)
        async def _wrap(parent: Any, info: Any, **kwargs: Any) -> Awaitable[AsyncIterator]:
            iterator = await func(parent, info, **kwargs)
            async for result in iterator:
                if filter_fn(result, info, **kwargs):
                    yield result

        return _wrap

    return wrap


def filter_post(payload, info, **kwargs):
    if 'author' not in kwargs:
        return False
    return payload['postAdded'].get('author') == kwargs['author']


@subscribe
# @with_filter(filter_post)
async def post_added(parent, info, **kwargs):
    return pubsub.async_iterator('POST_ADDED')


@mutate
async def add_post(parent, info, **kwargs):
    await pubsub.publish('POST_ADDED', {'postAdded': kwargs})
    return kwargs


async def shutdown():
    await pubsub.disconnect()


app = GraphQL(type_defs=type_defs, on_shutdown=[shutdown])


if __name__ == '__main__':
    uvicorn.run(app, port=8080, debug=True)

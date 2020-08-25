reviews = [
    {"id": "1", "authorID": "1", "product": {"upc": "1"}, "body": "Love it!"},
    {"id": "2", "authorID": "1", "product": {"upc": "2"}, "body": "Too expensive."},
    {"id": "3", "authorID": "2", "product": {"upc": "3"}, "body": "Could be better."},
    {"id": "4", "authorID": "2", "product": {"upc": "1"}, "body": "Prefer something else."}
]


def get_review_by_id(review_id):
    for review in reviews:
        if review["id"] == review_id:
            return review

    return None


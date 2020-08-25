reviews = [
    {'id': '1', 'authorID': '1', 'product': {'upc': '1'}, 'body': 'Love it!'},
    {'id': '2', 'authorID': '1', 'product': {'upc': '2'}, 'body': 'Too expensive.'},
    {'id': '3', 'authorID': '2', 'product': {'upc': '3'}, 'body': 'Could be better.'},
    {'id': '4', 'authorID': '2', 'product': {'upc': '1'}, 'body': 'Prefer something else.'},
]
users = [
    {'id': '1', 'name': 'Ada Lovelace', 'birthDate': '1815-12-10', 'username': '@ada'},
    {'id': '2', 'name': 'Alan Turing', 'birthDate': '1912-06-23', 'username': '@complete'},
]
products = [
    {'upc': '1', 'name': 'Table', 'price': 899, 'weight': 100},
    {'upc': '2', 'name': 'Couch', 'price': 1299, 'weight': 1000},
    {'upc': '3', 'name': 'Chair', 'price': 54, 'weight': 50},
]


def find_one(dict_list, key, value):
    for item in dict_list:
        if item[key] == value:
            return item

    return None


def find_many(dict_list, key, value):
    return filter(lambda x: x[key] == value, dict_list)


def get_review_by_id(review_id):
    return find_one(reviews, 'id', review_id)


def get_production_by_upc(upc):
    return find_one(products, 'upc', upc)


def get_user_reviews(user_id):
    return find_many(reviews, 'authorID', user_id)


def get_product_reviews(upc):
    return find_many(reviews, 'product', {'upc': upc})


def get_user_by_id(user_id):
    return find_one(users, 'id', user_id)


from urllib.parse import urljoin

import requests
from django.conf import settings

from rest_framework.exceptions import NotFound, APIException, ValidationError
from rest_framework import status


ALLOWED_SORTS = ("price_asc", "price_desc", "popularity", "new")
UPSTREAM_SORTS = {
    "popularity": "popular",
    "new": "created_desc",
}
FILTER_PARAM_ALIASES = {
    "category_id": "category_id",
    "price_min": "min_price",
    "price_max": "max_price",
    "seller_id": "seller_id",
}
PUBLIC_PRODUCT_PARAMS = ("category_id", "sort")
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
B2B_TIMEOUT_SEC = 3
MIN_SEARCH_LENGTH = 3
MAX_SEARCH_LENGTH = 200


class UpstreamUnavailable(Exception):
    pass


class BrokenHierarchyException(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = {
        "error": "orphan_node",
        "message": "category hierarchy is broken"
    }
    default_code = "orphan_node"


class UpstreamException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"}
    default_code = "UPSTREAM_UNAVAILABLE"

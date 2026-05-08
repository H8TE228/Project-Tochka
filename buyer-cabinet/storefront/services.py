from urllib.parse import urljoin

import requests
from django.conf import settings


ALLOWED_SORTS = ("rating", "popularity", "price_asc", "price_desc", "date_desc", "discount_desc")
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
B2B_TIMEOUT_SEC = 3


class UpstreamUnavailable(Exception):
    pass


def normalize_pagination(value, default=0, minimum=0, maximum=None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


def validate_sort(sort: str | None) -> str:
    sort = sort or "rating"
    if sort not in ALLOWED_SORTS:
        allowed = ", ".join(ALLOWED_SORTS)
        raise ValueError(f"Invalid sort parameter. Allowed: {allowed}")
    return sort


def query_params_as_pairs(query_params) -> list[tuple[str, str]]:
    pairs = []
    for key, values in query_params.lists():
        for value in values:
            pairs.append((key, value))
    return pairs


def b2b_get(path: str, params: list[tuple[str, str]]):
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.get(
            url,
            params=params,
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response


def product_short(product: dict) -> dict:
    skus = product.get("skus") or []
    visible_skus = [sku for sku in skus if int(sku.get("active_quantity") or 0) > 0]
    priced_skus = visible_skus or skus

    min_price = 0
    if priced_skus:
        min_price = min(
            int(sku.get("price") or 0) - int(sku.get("discount") or 0)
            for sku in priced_skus
        )

    image = ""
    images = product.get("images") or []
    if images:
        image = images[0].get("url", "")
    elif priced_skus:
        image = priced_skus[0].get("image", "")

    return {
        "id": product.get("id"),
        "title": product.get("title", ""),
        "image": image,
        "price": min_price,
        "in_stock": bool(visible_skus),
        "is_in_cart": False,
    }


def catalog_response(upstream_data, limit: int, offset: int) -> dict:
    if isinstance(upstream_data, dict) and "items" in upstream_data:
        return {
            "items": upstream_data.get("items", []),
            "total_count": int(upstream_data.get("total_count", len(upstream_data.get("items", [])))),
            "limit": int(upstream_data.get("limit", limit)),
            "offset": int(upstream_data.get("offset", offset)),
        }

    products = upstream_data if isinstance(upstream_data, list) else []
    items = [product_short(product) for product in products]
    return {
        "items": items[offset: offset + limit],
        "total_count": len(items),
        "limit": limit,
        "offset": offset,
    }

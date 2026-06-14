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


def get_category_tree(categories: list[dict]) -> list[dict]:
    tree = []
    nodes = {}
    existing_ids = set()
    for category in categories:
        cat = dict(category)
        cat_id = cat["id"]
        parent_id = cat["parent_id"]

        existing_ids.add(cat_id)

        if cat_id not in nodes: 
            nodes[cat_id] = {"children": []}
        
        nodes[cat_id].update(cat)
        current_node = nodes[cat_id]

        if parent_id is None:
            tree.append(current_node)
        else:
            if parent_id not in nodes:
                nodes[parent_id] = {"children": []}
            nodes[parent_id]["children"].append(current_node)

    for node_id in nodes:
        if node_id not in existing_ids:
            raise ValueError(f"Найдена категория сирота c родительским id {node_id}")
    return tree


def get_category_index(categories: list[dict]) -> dict[str, dict]:
    return {str(category["id"]): category for category in categories}


def get_category_path(categories: list[dict], category_id: str) -> list[dict]:
    index = get_category_index(categories=categories)
    category = index.get(str(category_id))
    if category is None:
        raise NotFound(code="NOT_FOUND", detail="Category not found")
    path = []
    seen = set()
    current = category
    while current is not None:
        current_id = str(current["id"])
        if current_id in seen:
            raise BrokenHierarchyException()
        seen.add(current_id)
        path.append(current)
        parent_id = current.get("parent_id")
        if parent_id is None:
            break
        parent = index.get(str(parent_id))
        if parent is None:
            raise BrokenHierarchyException()
        current = parent
    path.reverse()
    return path


def normalize_pagination(value, default=0, minimum=0, maximum=None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    number = max(number, minimum)
    if maximum is not None:
        number = min(number, maximum)
    return number


def validate_sort(sort: str | None) -> str | None:
    if not sort:
        return None
    if sort not in ALLOWED_SORTS:
        allowed = ", ".join(ALLOWED_SORTS)
        raise ValueError(f"Invalid sort parameter. Allowed: {allowed}")
    return sort


def validate_search(search: str | None) -> str | None:
    if search is None or search == "":
        return None
    if len(search) < MIN_SEARCH_LENGTH:
        raise ValueError("Search query must be at least 3 characters")
    if len(search) > MAX_SEARCH_LENGTH:
        raise ValueError("Search query must be at most 200 characters")
    return search


def query_params_as_pairs(query_params) -> list[tuple[str, str]]:
    pairs = []
    for key, values in query_params.lists():
        for value in values:
            pairs.append((key, value))
    return pairs


def public_products_param_key(key: str) -> str | None:
    if key == "q":
        return "search"
    if key in PUBLIC_PRODUCT_PARAMS:
        return key
    if key.startswith("filter[") and key.endswith("]"):
        filter_name = key[len("filter["):-1]
        if filter_name in FILTER_PARAM_ALIASES:
            return FILTER_PARAM_ALIASES[filter_name]
        return f"filters[{filter_name}]"
    return None


def public_products_params(query_params, limit: int, offset: int) -> list[tuple[str, str]]:
    params = []
    page = offset // limit + 1

    for key, values in query_params.lists():
        if key in ("limit", "offset"):
            continue
        upstream_key = public_products_param_key(key)
        if upstream_key is None:
            continue
        for value in values:
            if upstream_key == "sort":
                value = UPSTREAM_SORTS.get(value, value)
            params.append((upstream_key, value))

    params.append(("page", str(page)))
    params.append(("size", str(limit)))
    return params


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


def b2b_get_product(product_id: str) -> dict:
    try:
        upstream_response = b2b_get(f"/api/v1/public/products/{product_id}", [])
    except UpstreamUnavailable:
        raise UpstreamException()
    if upstream_response.status_code == 404:
        raise NotFound(code="NOT_FOUND", detail="Product not found")
    if upstream_response.status_code >= 400:
        raise ValidationError(detail="Invalid product_id")
    return upstream_response.json()


def b2b_get_products(params: list[tuple[str, str]]) -> dict:
    try:
        upstream_response = b2b_get("/api/v1/public/products", params)
    except UpstreamUnavailable:
        raise UpstreamException()
    if upstream_response.status_code >= 400:
        raise ValidationError(detail="Invalid params")
    return upstream_response.json()


def b2b_post(path: str, json_data: dict | None, params: list[tuple[str, str]]):
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.post(
            url,
            params=params,
            json=json_data,
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response


def int_value(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def stock_quantity(sku: dict) -> int:
    return int_value(
        sku.get(
            "active_quantity",
            sku.get("available_quantity", sku.get("stock_quantity") or 0),
        )
    )


def sku_price(sku: dict) -> int:
    return int_value(sku.get("price"))


def product_name(product: dict) -> str:
    return product.get("name") or product.get("title") or ""


def priced_skus(skus: list[dict]) -> list[dict]:
    in_stock = [sku for sku in skus if stock_quantity(sku) > 0]
    return in_stock or skus


def min_price(skus: list[dict]) -> int:
    candidates = priced_skus(skus)
    if not candidates:
        return 0
    return min(sku_price(sku) for sku in candidates)


def image_ref(image: dict, fallback_id: str | None = None) -> dict:
    return {
        "id": image.get("id") or fallback_id or "",
        "url": image.get("url", ""),
        "ordering": int_value(image.get("ordering", image.get("order"))),
    }


def product_image_refs(product: dict, skus: list[dict]) -> list[dict]:
    images = [image_ref(image) for image in product.get("images") or []]
    if images:
        return images

    for sku in priced_skus(skus):
        sku_images = sku.get("images") or []
        if sku_images:
            return [image_ref(sku_images[0])]
        if sku.get("image"):
            return [
                {
                    "id": sku.get("image_id") or sku.get("id") or "",
                    "url": sku.get("image", ""),
                    "ordering": 0,
                }
            ]
    return []


def characteristic_response(characteristic: dict) -> dict:
    return {
        "name": characteristic.get("name", ""),
        "value": characteristic.get("value", ""),
    }


def product_short(product: dict) -> dict:
    skus = product.get("skus") or []
    return {
        "id": product.get("id"),
        "name": product_name(product),
        "min_price": min_price(skus),
        "has_stock": any(stock_quantity(sku) > 0 for sku in skus),
        "images": product_image_refs(product, skus),
    }


def catalog_response(upstream_data, limit: int, offset: int) -> dict:
    if isinstance(upstream_data, dict) and "items" in upstream_data:
        upstream_items = upstream_data.get("items", [])
        return {
            "items": [product_short(product) for product in upstream_items],
            "total_count": int(
                upstream_data.get("total_count", upstream_data.get("total", len(upstream_items)))
            ),
            "limit": limit,
            "offset": offset,
        }

    products = upstream_data if isinstance(upstream_data, list) else []
    items = [product_short(product) for product in products]
    return {
        "items": items[offset: offset + limit],
        "total_count": len(items),
        "limit": limit,
        "offset": offset,
    }


def sku_response(sku: dict) -> dict:
    sku_images = sku.get("images") or []
    image_url = sku.get("image", "")
    if not image_url and sku_images:
        image_url = sku_images[0].get("url", "")

    available_quantity = stock_quantity(sku)
    return {
        "id": sku.get("id"),
        "name": sku.get("name", ""),
        "price": int_value(sku.get("price")),
        "discount": int_value(sku.get("discount")),
        "image": image_url,
        "available_quantity": available_quantity,
        "in_stock": available_quantity > 0,
        "characteristics": [
            characteristic_response(characteristic)
            for characteristic in sku.get("characteristics") or []
        ],
    }


def product_card_response(product: dict) -> dict:
    skus = product.get("skus") or []
    return {
        "id": product.get("id"),
        "slug": product.get("slug", ""),
        "name": product_name(product),
        "description": product.get("description", ""),
        "min_price": min_price(skus),
        "has_stock": any(stock_quantity(sku) > 0 for sku in skus),
        "images": product_image_refs(product, skus),
        "characteristics": [
            characteristic_response(characteristic)
            for characteristic in product.get("characteristics") or []
        ],
        "skus": [sku_response(sku) for sku in skus],
    }


# ============================================================
# US-ORD-01: B2B reserve / unreserve helpers
# ============================================================

def b2b_reserve(idempotency_key: str, order_id: str, items: list[dict]):
    """
    POST /api/v1/inventory/reserve к B2B.
    items: [{"sku_id": "...", "quantity": N}, ...]
    Возвращает requests.Response.
    Поднимает UpstreamUnavailable при сетевой ошибке.
    """
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", "api/v1/inventory/reserve")
    try:
        response = requests.post(
            url,
            json={"idempotency_key": idempotency_key, "order_id": order_id, "items": items},
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response


def b2b_unreserve(order_id: str, items: list[dict]):
    """
    POST /api/v1/unreserve к B2B.
    items: [{"sku_id": "...", "quantity": N}, ...]
    Возвращает requests.Response.
    Поднимает UpstreamUnavailable при сетевой ошибке.
    """
    url = urljoin(settings.B2B_URL.rstrip("/") + "/", "api/v1/unreserve")
    try:
        response = requests.post(
            url,
            json={"order_id": order_id, "items": items},
            headers={"X-Service-Key": settings.SERVICE_API_KEY},
            timeout=B2B_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        raise UpstreamUnavailable from exc
    return response

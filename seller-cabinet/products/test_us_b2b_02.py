"""US-B2B-02: добавление SKU.

Канон: flows/b2b-flows.md#add-sku
OpenAPI: neomarket-protocols/b2b/neomarket-b2b.yaml — POST /api/v1/skus
"""
from unittest.mock import patch

import pytest

from products.models import Product

pytestmark = pytest.mark.django_db(transaction=True)


def _payload(product_id):
    return {
        "product_id": str(product_id),
        "name": "256GB Black",
        "price": 12999000,
        "cost_price": 9500000,
        "discount": 0,
        "image": "/s3/iphone-black.jpg",
        "characteristics": [{"name": "Цвет", "value": "Чёрный"}],
    }


def _payload_with_images_array(product_id):
    """Новый формат по openapi: SKUCreate с массивом images."""
    return {
        "product_id": str(product_id),
        "name": "256GB Black",
        "price": 12999000,
        "cost_price": 9500000,
        "discount": 0,
        "images": [
            {"url": "/s3/iphone-black-1.jpg", "ordering": 0},
            {"url": "/s3/iphone-black-2.jpg", "ordering": 1},
        ],
        "characteristics": [{"name": "Цвет", "value": "Чёрный"}],
    }


def test_first_sku_transitions_product_to_on_moderation(api_client, product_factory):
    product = product_factory(status=Product.Status.CREATED)
    with patch("products.services._post_event"):
        resp = api_client.post("/api/v1/skus", _payload(product.id), format="json")
    assert resp.status_code == 201
    product.refresh_from_db()
    assert product.status == Product.Status.ON_MODERATION


def test_first_sku_emits_created_event_to_moderation(api_client, product_factory, seller):
    product = product_factory(status=Product.Status.CREATED)
    with patch("products.services._post_event") as mock_post:
        api_client.post("/api/v1/skus", _payload(product.id), format="json")

    assert mock_post.called
    url, payload, key = mock_post.call_args.args
    assert url.endswith("/api/v1/events/product")
    assert payload["event"] == "CREATED"
    assert payload["product_id"] == str(product.id)
    assert payload["seller_id"] == str(seller.auth_user_id)
    assert "idempotency_key" in payload
    assert "date" in payload
    assert key


def test_second_sku_no_state_change(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)

    with patch("products.services._post_event") as mock_post:
        resp = api_client.post("/api/v1/skus", _payload(product.id), format="json")

    assert resp.status_code == 201
    product.refresh_from_db()
    assert product.status == Product.Status.ON_MODERATION
    assert not mock_post.called


def test_add_sku_to_hard_blocked_returns_403(api_client, product_factory):
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    resp = api_client.post("/api/v1/skus", _payload(product.id), format="json")
    assert resp.status_code == 403
    assert resp.data["code"] == "FORBIDDEN"


def test_missing_image_returns_400(api_client, product_factory):
    product = product_factory(status=Product.Status.CREATED)
    payload = _payload(product.id)
    del payload["image"]
    resp = api_client.post("/api/v1/skus", payload, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
    assert "image" in resp.data["message"].lower()


def test_create_sku_accepts_images_array_format(api_client, product_factory):
    """openapi.SKUCreate: images — массив объектов {url, ordering}."""
    product = product_factory(status=Product.Status.CREATED)
    with patch("products.services._post_event"):
        resp = api_client.post(
            "/api/v1/skus",
            _payload_with_images_array(product.id),
            format="json",
        )
    assert resp.status_code == 201
    assert "images" in resp.data
    assert len(resp.data["images"]) == 2
    for img in resp.data["images"]:
        assert "id" in img
        assert "url" in img
        assert "ordering" in img


def test_sku_response_includes_canonical_openapi_fields(api_client, product_factory):
    """openapi.SKUResponse required-поля присутствуют в ответе."""
    product = product_factory(status=Product.Status.CREATED)
    with patch("products.services._post_event"):
        resp = api_client.post("/api/v1/skus", _payload(product.id), format="json")
    assert resp.status_code == 201
    data = resp.data
    for field in ("id", "product_id", "name", "price", "discount", "cost_price",
                  "stock_quantity", "active_quantity", "reserved_quantity",
                  "article", "images", "characteristics"):
        assert field in data, f"Missing openapi field: {field}"
"""US-B2B-01: создание карточки товара.

Канон: flows/b2b-flows.md#create-product
OpenAPI: neomarket-protocols/b2b/neomarket-b2b.yaml — POST /api/v1/products
"""
import uuid

import pytest

from products.models import Product

pytestmark = pytest.mark.django_db


def _valid_payload(category_id):
    return {
        "title": "iPhone 15 Pro Max",
        "description": "Apple flagship 2024",
        "category_id": str(category_id),
        "images": [{"url": "/s3/iphone-1.jpg", "ordering": 0}],
        "characteristics": [{"name": "Бренд", "value": "Apple"}],
    }


def test_create_product_returns_201_with_created_status(api_client, seller, category):
    """DoD: 201, status=CREATED, skus=[]. Все openapi-required поля присутствуют."""
    resp = api_client.post("/api/v1/products", _valid_payload(category.id), format="json")
    assert resp.status_code == 201

    data = resp.data
    assert data["status"] == "CREATED"
    assert data["skus"] == []
    assert data["deleted"] is False
    assert data["blocked"] is False

    # openapi.ProductResponse required поля (закрывает фидбек арбитра по US-B2B-01 п.4)
    assert "id" in data
    assert data["seller_id"] == str(seller.auth_user_id)
    assert data["category_id"] == str(category.id)
    assert "slug" in data
    assert "blocking_reason_id" in data
    assert "moderator_comment" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_seller_id_taken_from_jwt(api_client, seller, another_seller, category):
    payload = _valid_payload(category.id)
    payload["seller_id"] = str(another_seller.auth_user_id)

    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 201

    product = Product.objects.get(id=resp.data["id"])
    assert product.seller.auth_user_id == seller.auth_user_id
    assert product.seller_id != another_seller.id
    assert resp.data["seller_id"] == str(seller.auth_user_id)


def test_missing_images_returns_400(api_client, category):
    payload = _valid_payload(category.id)
    del payload["images"]
    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
    assert "images" in resp.data["message"]


def test_missing_category_returns_400(api_client):
    payload = {
        "title": "X",
        "description": "Y",
        "images": [{"url": "/s3/x.jpg", "ordering": 0}],
    }
    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
    assert "category" in resp.data["message"]


def test_invalid_category_id_returns_400(api_client):
    payload = {
        "title": "X",
        "description": "Y",
        "category_id": str(uuid.uuid4()),
        "images": [{"url": "/s3/x.jpg", "ordering": 0}],
    }
    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
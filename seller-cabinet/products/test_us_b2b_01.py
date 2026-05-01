"""US-B2B-01: создание карточки товара. Канон: flows/b2b-flows.md#create-product."""
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


def test_create_product_returns_201_with_created_status(api_client, category):
    resp = api_client.post("/api/v1/products", _valid_payload(category.id), format="json")
    assert resp.status_code == 201
    assert resp.data["status"] == "CREATED"
    assert resp.data["skus"] == []
    assert resp.data["deleted"] is False
    assert resp.data["blocked"] is False


def test_seller_id_taken_from_jwt(api_client, seller, another_seller, category):
    """seller_id из JWT, попытка передать чужой в body игнорируется."""
    payload = _valid_payload(category.id)
    payload["seller_id"] = str(another_seller.auth_user_id)

    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 201

    product = Product.objects.get(id=resp.data["id"])
    assert product.seller.auth_user_id == seller.auth_user_id
    assert product.seller_id != another_seller.id


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
    """Несуществующий category_id → 400, не 500."""
    payload = {
        "title": "X",
        "description": "Y",
        "category_id": str(uuid.uuid4()),
        "images": [{"url": "/s3/x.jpg", "ordering": 0}],
    }
    resp = api_client.post("/api/v1/products", payload, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"
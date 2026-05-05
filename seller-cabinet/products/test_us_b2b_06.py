"""US-B2B-06: создание накладной. Канон: flows/b2b-flows.md#create-invoice."""
import pytest

from products.models import Product

pytestmark = pytest.mark.django_db


def test_create_invoice_with_moderated_sku_returns_201(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku = sku_factory(product)

    resp = api_client.post(
        "/api/v1/invoices",
        {"items": [{"sku_id": str(sku.id), "quantity": 10}]},
        format="json",
    )

    assert resp.status_code == 201
    data = resp.data
    assert "id" in data
    assert data["status"] == "PENDING"
    assert "created_at" in data
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["sku_id"] == str(sku.id)
    assert item["sku_name"] == sku.name
    assert item["quantity"] == 10
    assert item["accepted_quantity"] is None


def test_empty_items_returns_400(api_client):
    resp = api_client.post("/api/v1/invoices", {"items": []}, format="json")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"


def test_non_moderated_sku_returns_400(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku = sku_factory(product)

    resp = api_client.post(
        "/api/v1/invoices",
        {"items": [{"sku_id": str(sku.id), "quantity": 5}]},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"


def test_others_sku_returns_403(api_client, product_factory, sku_factory, another_seller):
    product = product_factory(status=Product.Status.MODERATED, owner=another_seller)
    sku = sku_factory(product)

    resp = api_client.post(
        "/api/v1/invoices",
        {"items": [{"sku_id": str(sku.id), "quantity": 3}]},
        format="json",
    )

    assert resp.status_code == 403
    assert resp.data["code"] == "NOT_OWNER"

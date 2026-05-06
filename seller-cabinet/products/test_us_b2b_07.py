import pytest

from products.models import Product

pytestmark = pytest.mark.django_db


def test_catalog_returns_moderated_in_stock_products(service_api_client, product_factory, sku_factory):
    visible = product_factory(status=Product.Status.MODERATED)
    sku_factory(visible, active_quantity=5)

    hidden_not_moderated = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(hidden_not_moderated, active_quantity=5)

    hidden_no_stock = product_factory(status=Product.Status.MODERATED)
    sku_factory(hidden_no_stock, active_quantity=0)

    resp = service_api_client.get("/api/v1/products")

    assert resp.status_code == 200
    ids = {item["id"] for item in resp.data}
    assert str(visible.id) in ids
    assert str(hidden_not_moderated.id) not in ids
    assert str(hidden_no_stock.id) not in ids


def test_catalog_excludes_hard_blocked(service_api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    sku_factory(product, active_quantity=5)

    resp = service_api_client.get("/api/v1/products")

    assert resp.status_code == 200
    ids = {item["id"] for item in resp.data}
    assert str(product.id) not in ids


def test_catalog_missing_service_key_returns_401(product_factory, sku_factory):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, active_quantity=5)
    client = APIClient()
    resp = client.get("/api/v1/products")
    assert resp.status_code == 401


def test_catalog_response_has_no_cost_price(service_api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, cost_price=777, reserved_quantity=3, active_quantity=5)

    resp = service_api_client.get("/api/v1/products")

    assert resp.status_code == 200
    sku = resp.data[0]["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


def test_batch_ids_returns_visible_subset(service_api_client, product_factory, sku_factory):
    visible = product_factory(status=Product.Status.MODERATED)
    visible_sku = sku_factory(visible, active_quantity=5)

    hidden = product_factory(status=Product.Status.BLOCKED)
    hidden_sku = sku_factory(hidden, active_quantity=5)

    resp = service_api_client.get(f"/api/v1/products?ids={visible_sku.id},{hidden_sku.id}")

    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["id"] == str(visible.id)
    assert [sku["id"] for sku in resp.data[0]["skus"]] == [str(visible_sku.id)]

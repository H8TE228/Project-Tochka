import pytest

from products.models import Product

pytestmark = pytest.mark.django_db


def _catalog_items(resp):
    return resp.data["items"]


def test_catalog_returns_moderated_in_stock_products(service_api_client, product_factory, sku_factory):
    visible = product_factory(status=Product.Status.MODERATED)
    sku_factory(visible, active_quantity=5)

    hidden_not_moderated = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(hidden_not_moderated, active_quantity=5)

    hidden_no_stock = product_factory(status=Product.Status.MODERATED)
    sku_factory(hidden_no_stock, active_quantity=0)

    resp = service_api_client.get("/api/v1/public/products", {"page": 1, "size": 100})

    assert resp.status_code == 200
    assert "items" in resp.data
    ids = {item["id"] for item in _catalog_items(resp)}
    assert str(visible.id) in ids
    assert str(hidden_not_moderated.id) not in ids
    assert str(hidden_no_stock.id) not in ids


def test_catalog_excludes_hard_blocked(service_api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    sku_factory(product, active_quantity=5)

    resp = service_api_client.get("/api/v1/public/products", {"page": 1, "size": 100})

    assert resp.status_code == 200
    ids = {item["id"] for item in _catalog_items(resp)}
    assert str(product.id) not in ids


def test_catalog_missing_service_key_returns_401(product_factory, sku_factory):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, active_quantity=5)
    client = APIClient()
    resp = client.get("/api/v1/public/products")
    assert resp.status_code == 401


def test_catalog_bearer_without_service_key_returns_401(product_factory, sku_factory):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, active_quantity=5)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer test-token")
    resp = client.get("/api/v1/public/products")
    assert resp.status_code == 401


def test_catalog_response_has_no_cost_price(service_api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, cost_price=777, reserved_quantity=3, active_quantity=5)

    resp = service_api_client.get("/api/v1/public/products", {"page": 1, "size": 10})

    assert resp.status_code == 200
    sku = _catalog_items(resp)[0]["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


def test_catalog_response_has_title(service_api_client, product_factory, sku_factory):
    visible = product_factory(status=Product.Status.MODERATED, title="Visible Phone")
    sku_factory(visible, active_quantity=5)

    resp = service_api_client.get("/api/v1/public/products", {"page": 1, "size": 10})

    assert resp.status_code == 200
    item = next(i for i in _catalog_items(resp) if i["id"] == str(visible.id))
    assert item["title"] == "Visible Phone"


def test_catalog_paginated_shape(service_api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku_factory(product, active_quantity=5)

    resp = service_api_client.get("/api/v1/public/products", {"page": 1, "size": 10})

    assert resp.status_code == 200
    for key in ("items", "total", "page", "size", "pages"):
        assert key in resp.data
    assert resp.data["page"] == 1
    assert resp.data["size"] == 10


def test_batch_product_ids_returns_visible_subset(service_api_client, product_factory, sku_factory):
    visible = product_factory(status=Product.Status.MODERATED)
    visible_sku = sku_factory(visible, active_quantity=5)

    hidden = product_factory(status=Product.Status.BLOCKED)
    sku_factory(hidden, active_quantity=5)

    resp = service_api_client.post(
        "/api/v1/products",
        {"product_ids": [str(visible.id), str(hidden.id)]},
        format="json",
    )

    assert resp.status_code == 200
    assert len(_catalog_items(resp)) == 1
    assert _catalog_items(resp)[0]["id"] == str(visible.id)
    assert [sku["id"] for sku in _catalog_items(resp)[0]["skus"]] == [str(visible_sku.id)]

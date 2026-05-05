"""US-B2B-04: удаление товара. Канон: flows/b2b-flows.md#delete-product."""
from unittest.mock import patch

import pytest

from products.models import Product

# transaction=True обязательно — иначе transaction.on_commit не сработает
pytestmark = pytest.mark.django_db(transaction=True)


def test_delete_sets_deleted_true(api_client, product_factory):
    product = product_factory(status=Product.Status.MODERATED)
    with patch("products.services._post_event"):
        resp = api_client.delete(f"/api/v1/products/{product.id}")
    assert resp.status_code == 200
    assert resp.data == {"ok": True}
    product.refresh_from_db()
    assert product.deleted is True


def test_delete_emits_event_to_moderation(api_client, product_factory, seller):
    product = product_factory(status=Product.Status.MODERATED)
    with patch("products.services._post_event") as mock_post:
        api_client.delete(f"/api/v1/products/{product.id}")

    mod_call = next(
        (c for c in mock_post.call_args_list if c.args[1].get("event") == "DELETED"),
        None,
    )
    assert mod_call is not None, "Событие DELETED в Moderation не было отправлено"
    url, payload, key = mod_call.args
    assert url.endswith("/api/v1/events/product")
    assert payload["product_id"] == str(product.id)
    assert payload["seller_id"] == str(seller.auth_user_id)
    assert "idempotency_key" in payload
    assert "date" in payload
    assert key


def test_delete_emits_product_deleted_to_b2c(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku1 = sku_factory(product)
    sku2 = sku_factory(product)

    with patch("products.services._post_event") as mock_post:
        api_client.delete(f"/api/v1/products/{product.id}")

    b2c_call = next(
        (c for c in mock_post.call_args_list if c.args[1].get("event") == "PRODUCT_DELETED"),
        None,
    )
    assert b2c_call is not None, "Событие PRODUCT_DELETED в B2C не было отправлено"
    url, payload, key = b2c_call.args
    assert url.endswith("/api/v1/events/product")
    assert payload["product_id"] == str(product.id)
    assert set(payload["sku_ids"]) == {str(sku1.id), str(sku2.id)}
    assert "idempotency_key" in payload
    assert "date" in payload
    assert key


def test_delete_already_deleted_returns_400(api_client, product_factory):
    product = product_factory(status=Product.Status.MODERATED, deleted=True)
    resp = api_client.delete(f"/api/v1/products/{product.id}")
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"


def test_delete_others_product_returns_403(api_client, product_factory, another_seller):
    product = product_factory(status=Product.Status.MODERATED, owner=another_seller)
    resp = api_client.delete(f"/api/v1/products/{product.id}")
    assert resp.status_code == 403
    assert resp.data["code"] == "NOT_OWNER"


def test_deleted_product_not_in_seller_list(api_client, product_factory):
    product = product_factory(status=Product.Status.MODERATED)
    with patch("products.services._post_event"):
        api_client.delete(f"/api/v1/products/{product.id}")
    resp = api_client.get("/api/v1/products")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.data]
    assert str(product.id) not in ids

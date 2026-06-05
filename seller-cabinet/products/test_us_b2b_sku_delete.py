"""Soft delete SKU: DELETE /api/v1/skus/{sku_id}."""
import pytest

from products.models import Product

pytestmark = pytest.mark.django_db(transaction=True)


def test_delete_sku_returns_204_and_marks_deleted(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku = sku_factory(product, reserved_quantity=0)

    resp = api_client.delete(f"/api/v1/skus/{sku.id}")

    assert resp.status_code == 204
    assert resp.data is None
    sku.refresh_from_db()
    assert sku.deleted is True


def test_delete_sku_with_active_reserve_returns_409_conflict(
    api_client, product_factory, sku_factory
):
    product = product_factory(status=Product.Status.MODERATED)
    sku = sku_factory(product, reserved_quantity=3)

    resp = api_client.delete(f"/api/v1/skus/{sku.id}")

    assert resp.status_code == 409
    assert resp.data["code"] == "CONFLICT"
    sku.refresh_from_db()
    assert sku.deleted is False


def test_delete_others_sku_returns_403(
    api_client, product_factory, sku_factory, another_seller
):
    product = product_factory(status=Product.Status.MODERATED, owner=another_seller)
    sku = sku_factory(product, reserved_quantity=0)

    resp = api_client.delete(f"/api/v1/skus/{sku.id}")

    assert resp.status_code == 403
    assert resp.data["code"] == "NOT_OWNER"
    sku.refresh_from_db()
    assert sku.deleted is False

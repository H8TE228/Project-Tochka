"""US-B2B-03: редактирование товара/SKU.

Канон: flows/b2b-flows.md#edit-product
OpenAPI: neomarket-protocols/b2b/neomarket-b2b.yaml
- PATCH /api/v1/products/{product_id}
- PATCH /api/v1/skus/{sku_id}

PUT поддерживается для backward compat (делегирует на PATCH).
"""
from unittest.mock import patch

import pytest

from products.models import Product

pytestmark = pytest.mark.django_db(transaction=True)


def _patch_product_payload(category_id):
    return {
        "title": "Updated title",
        "description": "Updated description",
        "category_id": str(category_id),
        "images": [{"url": "/s3/new.jpg", "ordering": 0}],
        "characteristics": [],
    }


def _patch_sku_payload():
    return {
        "name": "Renamed",
        "price": 99999,
        "cost_price": 80000,
        "discount": 0,
        "image": "/s3/new.jpg",
        "characteristics": [],
    }


def test_edit_moderated_product_returns_to_on_moderation(api_client, product_factory, category):
    product = product_factory(status=Product.Status.MODERATED)
    with patch("products.services._post_event") as mock_post:
        resp = api_client.patch(
            f"/api/v1/products/{product.id}",
            _patch_product_payload(category.id),
            format="json",
        )
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.status == Product.Status.ON_MODERATION
    assert mock_post.called
    assert mock_post.call_args.args[1]["event"] == "EDITED"


def test_edit_blocked_product_returns_to_on_moderation(api_client, product_factory, category):
    product = product_factory(status=Product.Status.BLOCKED)
    with patch("products.services._post_event") as mock_post:
        resp = api_client.patch(
            f"/api/v1/products/{product.id}",
            _patch_product_payload(category.id),
            format="json",
        )
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.status == Product.Status.ON_MODERATION
    assert mock_post.called
    assert mock_post.call_args.args[1]["event"] == "EDITED"


def test_reserves_preserved_after_sku_edit(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku = sku_factory(product, active_quantity=20, reserved_quantity=7)

    payload = _patch_sku_payload()
    payload["price"] = 55555
    payload["active_quantity"] = 0
    payload["reserved_quantity"] = 0

    resp = api_client.patch(f"/api/v1/skus/{sku.id}", payload, format="json")
    assert resp.status_code == 200

    sku.refresh_from_db()
    assert sku.active_quantity == 20
    assert sku.reserved_quantity == 7
    assert sku.price == 55555


def test_edit_hard_blocked_returns_403(api_client, product_factory, category):
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    resp = api_client.patch(
        f"/api/v1/products/{product.id}",
        _patch_product_payload(category.id),
        format="json",
    )
    assert resp.status_code == 403
    assert resp.data["code"] == "FORBIDDEN"


def test_edit_others_product_returns_403(api_client, product_factory, another_seller, category):
    foreign_product = product_factory(status=Product.Status.MODERATED, owner=another_seller)
    resp = api_client.patch(
        f"/api/v1/products/{foreign_product.id}",
        _patch_product_payload(category.id),
        format="json",
    )
    assert resp.status_code == 403
    assert resp.data["code"] == "NOT_OWNER"


def test_patch_partial_update_only_title(api_client, product_factory):
    """openapi.ProductUpdate: PATCH семантика — обновление одного поля."""
    product = product_factory(status=Product.Status.CREATED, title="Original")
    with patch("products.services._post_event"):
        resp = api_client.patch(
            f"/api/v1/products/{product.id}",
            {"title": "Only Title Changed"},
            format="json",
        )
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.title == "Only Title Changed"


def test_put_still_works_for_backward_compat(api_client, product_factory, category):
    """PUT делегирует на PATCH — старые клиенты не сломаны."""
    product = product_factory(status=Product.Status.MODERATED)
    with patch("products.services._post_event"):
        resp = api_client.put(
            f"/api/v1/products/{product.id}",
            _patch_product_payload(category.id),
            format="json",
        )
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.status == Product.Status.ON_MODERATION
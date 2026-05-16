"""US-B2B-05: просмотр карточки товара. Канон: flows/b2b-flows.md#view-product."""
import uuid

import pytest

from products.models import BlockingReason, Product

pytestmark = pytest.mark.django_db


def test_get_moderated_product_returns_full_payload(api_client, product_factory, sku_factory):
    product = product_factory(status=Product.Status.MODERATED)
    sku = sku_factory(product)

    resp = api_client.get(f"/api/v1/products/{product.id}")

    assert resp.status_code == 200
    data = resp.data
    assert data["id"] == str(product.id)
    assert data["title"] == product.title
    assert data["status"] == "MODERATED"
    assert data["deleted"] is False
    assert data["blocked"] is False
    assert data["blocking_reason"] is None
    assert data["field_reports"] == []
    assert data["category_id"] == str(product.category.id)
    assert data["seller_id"] == str(product.seller.auth_user_id)
    # Seller cabinet включает cost_price и reserved_quantity (канон B2B-5)
    assert len(data["skus"]) == 1
    sku_data = data["skus"][0]
    assert sku_data["id"] == str(sku.id)
    assert sku_data["cost_price"] == sku.cost_price
    assert sku_data["reserved_quantity"] == sku.reserved_quantity


def test_get_blocked_product_returns_blocking_reason_and_field_reports(
    api_client, product_factory
):
    reason = BlockingReason.objects.create(title="Описание не соответствует товару")
    field_reports = [
        {
            "field_name": "description",
            "sku_id": None,
            "comment": "Материал не совпадает с фото",
        },
    ]
    product = product_factory(
        status=Product.Status.BLOCKED,
        blocking_reason=reason,
        moderator_comment="Несоответствие описания и фотографий",
        field_reports=field_reports,
    )

    resp = api_client.get(f"/api/v1/products/{product.id}")

    assert resp.status_code == 200
    data = resp.data
    assert data["status"] == "BLOCKED"
    assert data["blocked"] is True
    br = data["blocking_reason"]
    assert br is not None
    assert br["id"] == str(reason.id)
    assert br["title"] == reason.title
    assert br["comment"] == "Несоответствие описания и фотографий"
    assert len(data["field_reports"]) == 1
    assert data["field_reports"][0]["field_name"] == "description"


def test_get_others_product_returns_404(api_client, product_factory, another_seller):
    product = product_factory(status=Product.Status.MODERATED, owner=another_seller)
    resp = api_client.get(f"/api/v1/products/{product.id}")
    assert resp.status_code == 404


def test_get_nonexistent_returns_404(api_client):
    resp = api_client.get(f"/api/v1/products/{uuid.uuid4()}")
    assert resp.status_code == 404

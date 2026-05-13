import uuid

import pytest
from rest_framework.test import APIClient

from products.models import ProcessedRequest

pytestmark = pytest.mark.django_db(transaction=True)


def _fulfill(order_id, sku_id, quantity):
    return {
        "order_id": str(order_id),
        "sku_id": str(sku_id),
        "quantity": quantity,
    }


def test_fulfill_decreases_reserved_quantity_active_quantity_unchanged(
    service_api_client, product_factory, sku_factory
):
    """Happy path: fulfill_decreases_reserved_quantity, active_quantity_unchanged."""
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, active_quantity=3, reserved_quantity=5)
    active_before = sku.active_quantity

    order_id = uuid.uuid4()
    resp = service_api_client.post(
        "/api/v1/fulfill",
        _fulfill(order_id, sku.id, 2),
        format="json",
    )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    sku.refresh_from_db()
    assert sku.active_quantity == active_before == 3
    assert sku.reserved_quantity == 3


def test_idempotent_fulfill_no_double_deduction(service_api_client, product_factory, sku_factory):
    """Unhappy: повторный запрос с тем же order_id → 200, данные не меняются."""
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, active_quantity=0, reserved_quantity=5)
    order_id = uuid.uuid4()
    body = _fulfill(order_id, sku.id, 2)

    first = service_api_client.post("/api/v1/fulfill", body, format="json")
    second = service_api_client.post("/api/v1/fulfill", body, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    sku.refresh_from_db()
    assert sku.reserved_quantity == 3
    assert (
        ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.FULFILL, idempotency_key=order_id
        ).count()
        == 1
    )


def test_missing_service_key_returns_401(product_factory, sku_factory):
    """Unhappy: missing_service_key_returns_401"""
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, reserved_quantity=1)
    client = APIClient()
    resp = client.post(
        "/api/v1/fulfill",
        _fulfill(uuid.uuid4(), sku.id, 1),
        format="json",
    )
    assert resp.status_code == 401

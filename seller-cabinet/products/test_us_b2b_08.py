import uuid
from unittest.mock import patch

import pytest

from products.models import ProcessedRequest

pytestmark = pytest.mark.django_db(transaction=True)


def _command(items, idem=None):
    return {
        "items": items,
        "idempotency_key": str(idem or uuid.uuid4()),
    }


def test_reserve_all_skus_succeeds(service_api_client, product_factory, sku_factory):
    product = product_factory(status="MODERATED")
    sku1 = sku_factory(product, active_quantity=10, reserved_quantity=0)
    sku2 = sku_factory(product, active_quantity=15, reserved_quantity=1)
    payload = _command(
        [{"sku_id": str(sku1.id), "quantity": 3}, {"sku_id": str(sku2.id), "quantity": 5}]
    )

    resp = service_api_client.post("/api/v1/reserve", payload, format="json")

    assert resp.status_code == 200
    sku1.refresh_from_db()
    sku2.refresh_from_db()
    assert sku1.active_quantity == 7 and sku1.reserved_quantity == 3
    assert sku2.active_quantity == 10 and sku2.reserved_quantity == 6


def test_partial_insufficient_stock_returns_409_all_rollback(service_api_client, product_factory, sku_factory):
    product = product_factory(status="MODERATED")
    sku1 = sku_factory(product, active_quantity=4, reserved_quantity=0)
    sku2 = sku_factory(product, active_quantity=1, reserved_quantity=0)
    payload = _command(
        [{"sku_id": str(sku1.id), "quantity": 2}, {"sku_id": str(sku2.id), "quantity": 2}]
    )

    resp = service_api_client.post("/api/v1/reserve", payload, format="json")

    assert resp.status_code == 409
    sku1.refresh_from_db()
    sku2.refresh_from_db()
    assert sku1.active_quantity == 4 and sku1.reserved_quantity == 0
    assert sku2.active_quantity == 1 and sku2.reserved_quantity == 0


def test_idempotent_reserve_returns_200_without_double_deduction(service_api_client, product_factory, sku_factory):
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, active_quantity=10, reserved_quantity=0)
    idem = uuid.uuid4()
    payload = _command([{"sku_id": str(sku.id), "quantity": 3}], idem=idem)

    first = service_api_client.post("/api/v1/reserve", payload, format="json")
    second = service_api_client.post("/api/v1/reserve", payload, format="json")

    assert first.status_code == 200
    assert second.status_code == 200
    sku.refresh_from_db()
    assert sku.active_quantity == 7
    assert sku.reserved_quantity == 3
    assert ProcessedRequest.objects.filter(action="RESERVE", idempotency_key=idem).count() == 1


def test_sku_out_of_stock_event_emitted(service_api_client, product_factory, sku_factory):
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, active_quantity=2, reserved_quantity=0)
    payload = _command([{"sku_id": str(sku.id), "quantity": 2}])

    with patch("products.services._post_event") as mock_post:
        resp = service_api_client.post("/api/v1/reserve", payload, format="json")

    assert resp.status_code == 200
    assert any(call.args[1].get("event") == "SKU_OUT_OF_STOCK" for call in mock_post.call_args_list)


def test_unreserve_restores_quantities(service_api_client, product_factory, sku_factory):
    product = product_factory(status="MODERATED")
    sku = sku_factory(product, active_quantity=5, reserved_quantity=4)
    payload = _command([{"sku_id": str(sku.id), "quantity": 3}])

    resp = service_api_client.post("/api/v1/unreserve", payload, format="json")

    assert resp.status_code == 200
    sku.refresh_from_db()
    assert sku.active_quantity == 8
    assert sku.reserved_quantity == 1

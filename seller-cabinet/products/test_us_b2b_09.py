import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from products.models import BlockingReason, ProcessedModerationEvent, Product

pytestmark = pytest.mark.django_db(transaction=True)

MODERATION_URL = "/api/v1/moderation/events"


def _event_payload(
    product_id,
    event_type,
    hard_block=False,
    field_reports=None,
    blocking_reason_id=None,
    idem=None,
):
    return {
        "product_id": str(product_id),
        "event_type": event_type,
        "hard_block": hard_block,
        "occurred_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "field_reports": field_reports,
        "blocking_reason_id": str(blocking_reason_id) if blocking_reason_id else None,
        "idempotency_key": str(idem or uuid.uuid4()),
    }


def test_moderated_event_clears_blocking_data(service_api_client, product_factory, sku_factory):
    reason = BlockingReason.objects.create(title="wrong brand")
    product = product_factory(
        status=Product.Status.BLOCKED,
        blocking_reason=reason,
        moderator_comment="details",
        field_reports=[{"field_name": "title", "comment": "bad"}],
    )
    sku_factory(product)

    resp = service_api_client.post(
        MODERATION_URL,
        _event_payload(product.id, event_type="MODERATED"),
        format="json",
    )

    assert resp.status_code == 204
    assert resp.content == b""
    product.refresh_from_db()
    assert product.status == Product.Status.MODERATED
    assert product.blocking_reason is None
    assert product.field_reports == []


def test_blocked_soft_saves_field_reports(service_api_client, product_factory, sku_factory):
    reason = BlockingReason.objects.create(title="description mismatch")
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)
    reports = [{"field_name": "description", "comment": "invalid"}]

    resp = service_api_client.post(
        MODERATION_URL,
        _event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=False,
            field_reports=reports,
            blocking_reason_id=reason.id,
        ),
        format="json",
    )

    assert resp.status_code == 204
    product.refresh_from_db()
    assert product.status == Product.Status.BLOCKED
    assert product.blocking_reason_id == reason.id
    assert product.field_reports == reports


def test_blocked_hard_sets_terminal_status(service_api_client, product_factory, sku_factory):
    reason = BlockingReason.objects.create(title="policy violation")
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)

    with patch("products.services._post_event") as mock_post:
        resp = service_api_client.post(
            MODERATION_URL,
            _event_payload(
                product.id,
                event_type="BLOCKED",
                hard_block=True,
                field_reports=[{"field_name": "title", "comment": "forbidden"}],
                blocking_reason_id=reason.id,
            ),
            format="json",
        )

    assert resp.status_code == 204
    product.refresh_from_db()
    assert product.status == Product.Status.HARD_BLOCKED
    assert product.blocking_reason_id == reason.id
    assert any(call.args[1].get("event") == "PRODUCT_BLOCKED" for call in mock_post.call_args_list)


def test_hard_blocked_product_rejects_seller_edits(api_client, product_factory, category):
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    payload = {
        "title": "Updated title",
        "description": "Updated description",
        "category_id": str(category.id),
        "images": [{"url": "/s3/new.jpg", "ordering": 0}],
        "characteristics": [],
    }

    put_resp = api_client.put(f"/api/v1/products/{product.id}", payload, format="json")
    delete_resp = api_client.delete(f"/api/v1/products/{product.id}")

    assert put_resp.status_code == 403
    assert delete_resp.status_code == 403


def test_duplicate_event_same_idempotency_key_no_side_effects(service_api_client, product_factory, sku_factory):
    reason = BlockingReason.objects.create(title="desc")
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)
    idem = uuid.uuid4()
    payload = _event_payload(
        product.id,
        event_type="BLOCKED",
        hard_block=False,
        field_reports=[{"field_name": "description", "comment": "invalid"}],
        blocking_reason_id=reason.id,
        idem=idem,
    )

    first = service_api_client.post(MODERATION_URL, payload, format="json")
    second = service_api_client.post(MODERATION_URL, payload, format="json")

    assert first.status_code == 204
    assert second.status_code == 204
    assert (
        ProcessedModerationEvent.objects.filter(
            service_id="test-service",
            idempotency_key=idem,
        ).count()
        == 1
    )


def test_different_services_same_idempotency_key_do_not_collide(
    service_api_client, service_key, product_factory, sku_factory
):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)
    idem = uuid.uuid4()
    payload = _event_payload(product.id, event_type="MODERATED", idem=idem)

    client_a = APIClient()
    client_a.credentials(HTTP_X_SERVICE_KEY=service_key, HTTP_X_SERVICE_ID="moderation")
    client_b = APIClient()
    client_b.credentials(HTTP_X_SERVICE_KEY=service_key, HTTP_X_SERVICE_ID="b2c-gateway")

    assert client_a.post(MODERATION_URL, payload, format="json").status_code == 204
    assert client_b.post(MODERATION_URL, payload, format="json").status_code == 204
    assert ProcessedModerationEvent.objects.filter(idempotency_key=idem).count() == 2


def test_missing_service_key_returns_401(product_factory, sku_factory):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)
    client = APIClient()
    resp = client.post(
        MODERATION_URL,
        _event_payload(product.id, event_type="MODERATED"),
        format="json",
    )
    assert resp.status_code == 401


def test_missing_service_id_returns_400(service_api_client, product_factory, sku_factory):
    from rest_framework.test import APIClient

    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product)
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY="test-service-key")
    resp = client.post(
        MODERATION_URL,
        _event_payload(product.id, event_type="MODERATED"),
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["code"] == "INVALID_REQUEST"

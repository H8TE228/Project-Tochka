"""
Тесты для B2BEventView (POST /api/v1/b2b/events).

Канон: flows/b2b-flows.md#apply-moderation
OpenAPI: b2b/openapi.yaml — POST /api/v1/events/moderation
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from rest_framework import status

from modapi.models import ProductModeration, ProductBlockingReason


pytestmark = pytest.mark.django_db


def _b2b_event_payload(
    event_type,
    product_id,
    seller_id=None,
    json_before=None,
    json_after=None,
    idempotency_key=None,
    occurred_at=None,
):
    """Базовая структура B2B события."""
    payload = {
        "event_type": event_type,
        "idempotency_key": str(idempotency_key or uuid.uuid4()),
        "occurred_at": occurred_at or "2024-01-01T12:00:00Z",
        "payload": {
            "product_id": str(product_id),
        },
    }

    if event_type == "PRODUCT_CREATED":
        payload["payload"].update({
            "seller_id": str(seller_id or uuid.uuid4()),
            "json_after": json_after or {"title": "New Product"},
        })
    elif event_type == "PRODUCT_EDITED":
        payload["payload"].update({
            "seller_id": str(seller_id or uuid.uuid4()),
            "json_before": json_before or {"title": "Old Product"},
            "json_after": json_after or {"title": "Updated Product"},
        })
    elif event_type == "PRODUCT_DELETED":
        pass  # Только product_id

    return payload


def test_created_pending(service_api_client, db):
    """Событие CREATED создаёт карточку в PENDING."""
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()

    payload = _b2b_event_payload(
        event_type="PRODUCT_CREATED",
        product_id=product_id,
        seller_id=seller_id,
    )

    mock_response = {
        "id": str(product_id),
        "seller_id": str(seller_id),
        "title": "New Product",
    }

    with patch("modapi.services.b2b_get") as mock_b2b:
        mock_b2b.return_value.status_code = 200
        mock_b2b.return_value.json.return_value = mock_response

        resp = service_api_client.post("/api/v1/b2b/events", payload, format="json")
        assert resp.status_code == status.HTTP_202_ACCEPTED

    mod_obj = ProductModeration.objects.get(product_id=product_id)
    assert mod_obj.status == ProductModeration.Status.PENDING
    assert mod_obj.kind == ProductModeration.Kind.CREATE


def test_edited_returns_to_review(service_api_client, product_moderation_factory, db):
    """EDITED после MODERATED/BLOCKED возвращает карточку в очередь."""
    product_id = uuid.uuid4()
    mod_obj = product_moderation_factory(
        product_id=product_id,
        status=ProductModeration.Status.MODERATED,
        json_after={"title": "Approved"},
    )

    payload = _b2b_event_payload(
        event_type="PRODUCT_EDITED",
        product_id=product_id,
        seller_id=mod_obj.seller_id,
        json_before=mod_obj.json_after,
        json_after={"title": "Updated"},
    )

    mock_response = {
        "id": str(product_id),
        "seller_id": str(mod_obj.seller_id),
        "title": "Updated",
    }

    with patch("modapi.services.b2b_get") as mock_b2b:
        mock_b2b.return_value.status_code = 200
        mock_b2b.return_value.json.return_value = mock_response

        resp = service_api_client.post("/api/v1/b2b/events", payload, format="json")
        assert resp.status_code == status.HTTP_202_ACCEPTED

    mod_obj.refresh_from_db()
    assert mod_obj.status == ProductModeration.Status.PENDING
    assert mod_obj.kind == ProductModeration.Kind.EDIT


def test_edited_updates_in_review(service_api_client, product_moderation_factory, db):
    """EDITED во время IN_REVIEW обновляет поля."""
    product_id = uuid.uuid4()
    mod_obj = product_moderation_factory(
        product_id=product_id,
        status=ProductModeration.Status.IN_REVIEW,
        json_before={"title": "Original"},
        json_after={"title": "Under Review"},
    )

    payload = _b2b_event_payload(
        event_type="PRODUCT_EDITED",
        product_id=product_id,
        seller_id=mod_obj.seller_id,
        json_before=mod_obj.json_after,
        json_after={"title": "Edited"},
    )

    mock_response = {
        "id": str(product_id),
        "seller_id": str(mod_obj.seller_id),
        "title": "Edited",
    }

    with patch("modapi.services.b2b_get") as mock_b2b:
        mock_b2b.return_value.status_code = 200
        mock_b2b.return_value.json.return_value = mock_response

        resp = service_api_client.post("/api/v1/b2b/events", payload, format="json")
        assert resp.status_code == status.HTTP_202_ACCEPTED

    mod_obj.refresh_from_db()
    assert mod_obj.status == ProductModeration.Status.PENDING
    assert mod_obj.json_before == {"title": "Under Review"}
    assert mod_obj.json_after == mock_response


def test_deleted_archived(service_api_client, product_moderation_factory, db):
    """DELETED уводит карточку из очереди."""
    product_id = uuid.uuid4()
    product_moderation_factory(
        product_id=product_id,
        status=ProductModeration.Status.PENDING,
    )

    payload = _b2b_event_payload(
        event_type="PRODUCT_DELETED",
        product_id=product_id,
    )

    resp = service_api_client.post("/api/v1/b2b/events", payload, format="json")
    assert resp.status_code == status.HTTP_202_ACCEPTED

    assert not ProductModeration.objects.filter(product_id=product_id).exists()


def test_duplicate_event_no_side_effects(service_api_client, db):
    """Повторное событие с тем же ключом идемпотентности → 202 без побочных эффектов."""
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    idempotency_key = uuid.uuid4()

    payload = _b2b_event_payload(
        event_type="PRODUCT_CREATED",
        product_id=product_id,
        seller_id=seller_id,
        idempotency_key=idempotency_key,
    )

    mock_response = {
        "id": str(product_id),
        "seller_id": str(seller_id),
        "title": "Product",
    }

    with patch("modapi.services.b2b_get") as mock_b2b:
        mock_b2b.return_value.status_code = 200
        mock_b2b.return_value.json.return_value = mock_response

        resp1 = service_api_client.post("/api/v1/b2b/events", payload, format="json")
        assert resp1.status_code == status.HTTP_202_ACCEPTED

        first_count = ProductModeration.objects.count()

        resp2 = service_api_client.post("/api/v1/b2b/events", payload, format="json")
        assert resp2.status_code == status.HTTP_202_ACCEPTED

    assert ProductModeration.objects.count() == first_count


def test_missing_service_header_401(db):
    """Запрос без межсервисного заголовка → 401."""
    client = APIClient()

    payload = _b2b_event_payload(
        event_type="PRODUCT_CREATED",
        product_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
    )

    resp = client.post("/api/v1/b2b/events", payload, format="json")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

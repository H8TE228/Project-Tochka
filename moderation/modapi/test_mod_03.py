"""
Тесты для TicketApproveView (POST /api/v1/tickets/{ticket_id}/approve).
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework import status

from modapi.models import ProductModeration


pytestmark = pytest.mark.django_db


def test_approve_transitions_to_moderated_and_emits_event(jwt_client, product_moderation_factory, db, settings):
    """Happy path: статус → MODERATED, событие в B2B уходит."""
    settings.B2B_URL = "http://b2b.test"
    settings.SERVICE_API_KEY = "test-service-key"
    
    moderator_id = uuid.uuid4()
    product_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)

    ticket = product_moderation_factory(
        status="IN_REVIEW",
        product_id=product_id,
        seller_id=seller_id,
        moderator_id=moderator_id,
        queue_priority=1,
        json_after={"title": "Product under review", "skus": [{"id": "sku-1"}]},
    )

    mock_product_response = {
        "id": str(product_id),
        "seller_id": str(seller_id),
        "title": "Product under review",
        "skus": [{"id": "sku-1", "name": "SKU 1", "price": 100}],
    }

    mock_event_response = type("MockResponse", (), {"status_code": status.HTTP_204_NO_CONTENT})()

    with patch("modapi.services.b2b_get") as mock_get, \
             patch("modapi.services.b2b_post") as mock_post:
        mock_get.return_value.status_code = status.HTTP_200_OK
        mock_get.return_value.json.return_value = mock_product_response
        mock_post.return_value = mock_event_response

        resp = client.post(f"/api/v1/tickets/{ticket.id}/approve", {"comment": "Looks good"}, format="json")

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "MODERATED"
        assert resp.data["product_id"] == str(product_id)
        assert resp.data["assigned_moderator_id"] == str(moderator_id)

        ticket.refresh_from_db()
        assert ticket.status == ProductModeration.Status.MODERATED
        assert ticket.moderator_comment == "Looks good"
        assert ticket.date_moderation is not None

        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json_data"]
        assert call_json["event_type"] == "MODERATED"
        assert call_json["product_id"] == str(product_id)
        assert call_json["moderator_id"] == str(moderator_id)
        assert call_json["moderator_comment"] == "Looks good"


def test_approve_others_card_returns_403(jwt_client, product_moderation_factory, db):
    """Модератор не может одобрить карточку, закреплённую за другим."""
    moderator_id_1 = uuid.uuid4()
    moderator_id_2 = uuid.uuid4()
    client = jwt_client(user_id=moderator_id_1)

    ticket = product_moderation_factory(
        status="IN_REVIEW",
        moderator_id=moderator_id_2,
        queue_priority=1,
        json_after={"title": "Someone else's ticket"},
    )

    resp = client.post(f"/api/v1/tickets/{ticket.id}/approve", {}, format="json")

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "TICKET_WRONG_MODERATOR"
    assert "Not assigned to you" in resp.data["message"]


def test_approve_after_edited_returns_409(jwt_client, product_moderation_factory, db):
    """Продавец отредактировал во время review, повторный approve → 409."""
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)

    ticket = product_moderation_factory(
        status="PENDING",
        moderator_id=moderator_id,
        queue_priority=1,
        json_after={"title": "Edited product"},
    )

    resp = client.post(f"/api/v1/tickets/{ticket.id}/approve", {}, format="json")

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "TICKET_WRONG_STATUS"
    assert "Product is not in review" in resp.data["message"]


def test_approve_without_sku_returns_409(jwt_client, product_moderation_factory, db, settings):
    """Товар без SKU нельзя одобрить."""
    settings.B2B_URL = "http://b2b.test"
    settings.SERVICE_API_KEY = "test-service-key"
    
    moderator_id = uuid.uuid4()
    product_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)

    ticket = product_moderation_factory(
        status="IN_REVIEW",
        product_id=product_id,
        moderator_id=moderator_id,
        queue_priority=1,
        json_after={"title": "Product without SKUs"},
    )

    mock_product_response = {
        "id": str(product_id),
        "title": "Product without SKUs",
        "skus": [],
    }

    with patch("modapi.services.b2b_get") as mock_get:
        mock_get.return_value.status_code = status.HTTP_200_OK
        mock_get.return_value.json.return_value = mock_product_response

        resp = client.post(f"/api/v1/tickets/{ticket.id}/approve", {}, format="json")

        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.data["code"] == "TICKET_HAS_NO_SKUS"
        assert "Product has no SKUs" in resp.data["message"]

        ticket.refresh_from_db()
        assert ticket.status == ProductModeration.Status.IN_REVIEW

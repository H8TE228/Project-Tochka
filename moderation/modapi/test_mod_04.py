"""
US-MOD-04: soft-block flow (POST /api/v1/tickets/{ticket_id}/block).

Канон: flows/moderation-flows.md#soft-block.
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework import status

from modapi.models import ProductModeration, ProductModerationFieldReport


pytestmark = pytest.mark.django_db(transaction=True)


def _payload(reasons, field_path="description"):
    """
    Принимает либо одну причину, либо итерируемый список.
    Возвращает body по спецификации openapi:774 BlockDecisionRequest.
    """
    if hasattr(reasons, "id"):
        reasons = [reasons]
    return {
        "blocking_reason_ids": [str(r.id) for r in reasons],
        "comment": "Fix description and upload a clearer image.",
        "field_reports": [
            {
                "field_path": field_path,
                "message": "Description does not match the product.",
            },
            {
                "field_path": "product_images",
                "sku_id": str(uuid.uuid4()),
                "message": "Main image is blurry.",
            },
        ],
    }


def _in_review_card(product_moderation_factory, moderator_id):
    return product_moderation_factory(
        status=ProductModeration.Status.IN_REVIEW,
        moderator_id=moderator_id,
        json_after={"title": "Card"},
    )


def test_soft_block_transitions_to_blocked_with_field_reports(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    reason = blocking_reason_factory(hard_block=False)
    card = _in_review_card(product_moderation_factory, moderator_id)

    with patch("modapi.services._post_moderation_event"):
        resp = client.post(
            f"/api/v1/tickets/{card.id}/block",
            _payload(reason),
            format="json",
        )

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["status"] == ProductModeration.Status.BLOCKED

    card.refresh_from_db()
    assert card.status == ProductModeration.Status.BLOCKED
    assert card.blocking_reason_id == reason.id
    assert card.moderator_comment == "Fix description and upload a clearer image."

    reports = list(
        ProductModerationFieldReport.objects.filter(product_moderation=card)
        .order_by("field_path")
        .values("field_path", "message")
    )
    assert reports == [
        {
            "field_path": "description",
            "message": "Description does not match the product.",
        },
        {
            "field_path": "product_images",
            "message": "Main image is blurry.",
        },
    ]


def test_soft_block_emits_event_to_b2b(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    reason = blocking_reason_factory(hard_block=False)
    card = _in_review_card(product_moderation_factory, moderator_id)

    with patch("modapi.services._post_moderation_event") as mock_post:
        resp = client.post(
            f"/api/v1/tickets/{card.id}/block",
            _payload(reason),
            format="json",
        )

    assert resp.status_code == status.HTTP_200_OK
    assert mock_post.call_count == 1
    _, payload, _ = mock_post.call_args.args
    assert payload["product_id"] == str(card.product_id)
    assert payload["event_type"] == "BLOCKED"
    assert payload["hard_block"] is False
    assert payload["blocking_reason_id"] == str(reason.id)
    assert payload["field_reports"][0]["field_path"] == "description"
    assert payload["field_reports"][1]["sku_id"] is not None
    assert isinstance(payload["field_reports"][1]["sku_id"], str)


def test_soft_block_unknown_reason_returns_400(
    jwt_client,
    product_moderation_factory,
):
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    card = _in_review_card(product_moderation_factory, moderator_id)
    payload = {
        "blocking_reason_ids": [str(uuid.uuid4())],
        "field_reports": [],
    }

    resp = client.post(
        f"/api/v1/tickets/{card.id}/block",
        payload,
        format="json",
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "INVALID_REQUEST"


def test_soft_block_others_card_returns_403(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    owner_id = uuid.uuid4()
    another_moderator_id = uuid.uuid4()
    client = jwt_client(user_id=another_moderator_id)
    reason = blocking_reason_factory(hard_block=False)
    card = _in_review_card(product_moderation_factory, owner_id)

    resp = client.post(
        f"/api/v1/tickets/{card.id}/block",
        _payload(reason),
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "FORBIDDEN"


def test_soft_block_field_report_missing_message_returns_400(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    """field_path — свободная строка; валидация ловит отсутствие обязательного message."""
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    reason = blocking_reason_factory(hard_block=False)
    card = _in_review_card(product_moderation_factory, moderator_id)
    payload = _payload(reason)
    del payload["field_reports"][0]["message"]

    resp = client.post(
        f"/api/v1/tickets/{card.id}/block",
        payload,
        format="json",
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "INVALID_REQUEST"


def test_block_on_hard_blocked_ticket_returns_409(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    """Повторная блокировка тикета не в IN_REVIEW → 409 WRONG_STATUS (канон, openapi)."""
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    reason = blocking_reason_factory(hard_block=True)
    card = product_moderation_factory(
        status=ProductModeration.Status.HARD_BLOCKED,
        moderator_id=moderator_id,
        json_after={"title": "Card"},
    )

    resp = client.post(
        f"/api/v1/tickets/{card.id}/block",
        _payload(reason),
        format="json",
    )

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "WRONG_STATUS"


def test_block_with_hard_reason_transitions_to_hard_blocked(
    jwt_client,
    product_moderation_factory,
    blocking_reason_factory,
):
    """
    MOD-05 contract fix: hard_block=True причина — это валидный сценарий,
    не 400. Тикет переходит в HARD_BLOCKED (терминал), событие в B2B
    несёт hard_block=true.
    """
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)
    reason = blocking_reason_factory(hard_block=True)
    card = _in_review_card(product_moderation_factory, moderator_id)

    with patch("modapi.services._post_moderation_event") as mock_post:
        resp = client.post(
            f"/api/v1/tickets/{card.id}/block",
            _payload(reason),
            format="json",
        )

    assert resp.status_code == status.HTTP_200_OK, resp.content
    assert resp.data["status"] == ProductModeration.Status.HARD_BLOCKED
    card.refresh_from_db()
    assert card.status == ProductModeration.Status.HARD_BLOCKED
    # Событие в B2B несёт hard_block=true
    assert mock_post.call_count == 1
    _url, payload, _key = mock_post.call_args.args
    assert payload["event_type"] == "BLOCKED"
    assert payload["hard_block"] is True

"""
Тесты для QueueClaimView (POST /api/v1/queue/claim).
"""
import uuid

import pytest
from rest_framework import status

from modapi.models import ProductModeration


pytestmark = pytest.mark.django_db


def test_next_returns_oldest_pending(jwt_client, product_moderation_factory, db):
    """Happy path: PENDING → IN_REVIEW с закреплением за модератором."""
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)

    # Создаём карточки в очереди с разными priority и timestamps
    older_p1 = product_moderation_factory(
        status="PENDING",
        queue_priority=1,
        json_after={"title": "Old Priority 1"},
    )
    newer_p1 = product_moderation_factory(
        status="PENDING",
        queue_priority=1,
        json_after={"title": "New Priority 1"},
    )
    product_moderation_factory(
        status="PENDING",
        queue_priority=2,
        json_after={"title": "Priority 2"},
    )

    resp = client.post("/api/v1/queue/claim", {}, format="json")

    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["id"] == str(older_p1.id)
    assert resp.data["kind"] == ProductModeration.Kind.CREATE
    assert resp.data["status"] == "IN_REVIEW"
    assert "created_at" in resp.data
    assert resp.data["moderator_id"] == str(moderator_id)

    # Проверяем, что статус изменился в БД
    older_p1.refresh_from_db()
    assert older_p1.status == ProductModeration.Status.IN_REVIEW
    assert older_p1.moderator_id == moderator_id


def test_concurrent_two_moderators_get_different_cards(jwt_client, product_moderation_factory, db):
    """Две сессии в одной транзакции не получают одну карточку."""
    moderator_id_1 = uuid.uuid4()
    moderator_id_2 = uuid.uuid4()
    client_1 = jwt_client(user_id=moderator_id_1)
    client_2 = jwt_client(user_id=moderator_id_2)

    # Создаём две карточки в очереди
    product_moderation_factory(
        status="PENDING",
        queue_priority=1,
        json_after={"title": "Card 1"},
    )
    product_moderation_factory(
        status="PENDING",
        queue_priority=1,
        json_after={"title": "Card 2"},
    )

    # Оба модератора берут карточку
    resp1 = client_1.post("/api/v1/queue/claim", {}, format="json")
    resp2 = client_2.post("/api/v1/queue/claim", {}, format="json")

    assert resp1.status_code == status.HTTP_200_OK
    assert resp2.status_code == status.HTTP_200_OK

    # Карточки должны быть разными
    assert resp1.data["id"] != resp2.data["id"]

    # Оба модератора закреплены за своими карточками
    assert resp1.data["moderator_id"] == str(moderator_id_1)
    assert resp2.data["moderator_id"] == str(moderator_id_2)


def test_empty_queue_returns_204(jwt_client, db):
    """Пустая очередь возвращает 204."""
    client = jwt_client()

    resp = client.post("/api/v1/queue/claim", {}, format="json")

    assert resp.status_code == status.HTTP_204_NO_CONTENT
    assert resp.data == {"detail": "No pending products available."}


def test_moderator_already_has_in_review_returns_409(jwt_client, product_moderation_factory, db):
    """Попытка взять вторую карточку с активной IN_REVIEW отклоняется."""
    moderator_id = uuid.uuid4()
    client = jwt_client(user_id=moderator_id)

    # У модератора уже есть карточка в IN_REVIEW
    product_moderation_factory(
        status="IN_REVIEW",
        queue_priority=1,
        moderator_id=moderator_id,
        json_after={"title": "Already reviewing"},
    )

    # Создаём доступную карточку в очереди
    product_moderation_factory(
        status="PENDING",
        queue_priority=1,
        json_after={"title": "Available"},
    )

    resp = client.post("/api/v1/queue/claim", {}, format="json")

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "ALREADY_IN_REVIEW"
    assert "already have a pending product in review" in resp.data["message"].lower()

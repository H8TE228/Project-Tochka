"""
US-MOD-05: жёсткая блокировка (необратимая).

Канон-flow MOD-5: POST /api/v1/tickets/{ticket_id}/decline
Флаг hard_block=true → ProductModeration.status = HARD_BLOCKED (терминальный).
Событие BLOCKED + hard_block=true уходит в B2B.
Любые правки товара после блокировки → 403.

DoD-тесты:
- hard_block_transitions_to_terminal_and_emits_event
- hard_block_event_carries_hard_block_true
- any_modify_on_hard_blocked_returns_403
- edited_event_on_hard_blocked_is_ignored
- deleted_event_removes_hard_blocked
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from products.models import Product, ProductModeration
from seller_cabinet.authentication import TokenUser

pytestmark = pytest.mark.django_db


# ===== Fixtures =====

@pytest.fixture
def moderator_id():
    return uuid.uuid4()


@pytest.fixture
def moderator_user(moderator_id):
    user = TokenUser.__new__(TokenUser)
    user.id = moderator_id
    user.email = "moderator@test.local"
    user.role = "moderator"
    return user


@pytest.fixture
def moderator_client(moderator_user):
    client = APIClient()
    client.force_authenticate(user=moderator_user)
    return client


@pytest.fixture
def in_review_card(product_factory, moderator_id):
    """Карточка IN_REVIEW, закреплена за текущим модератором."""
    product = product_factory(status=Product.Status.ON_MODERATION)
    return ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.IN_REVIEW,
        moderator_id=moderator_id,
    )


# ===== DoD Tests =====

@pytest.mark.django_db(transaction=True)
def test_hard_block_transitions_to_terminal_and_emits_event(moderator_client, in_review_card):
    """
    Happy path: hard_block=true → ProductModeration.status = HARD_BLOCKED (терминальный),
    событие BLOCKED + hard_block=true отправляется в B2B.
    """
    with patch("products.services._post_event") as mock_post:
        resp = moderator_client.post(
            f"/api/v1/tickets/{in_review_card.id}/decline",
            {"hard_block": True, "moderator_comment": "Counterfeit product"},
            format="json",
        )

    assert resp.status_code == 200, resp.content
    assert resp.data["status"] == ProductModeration.ModerationStatus.HARD_BLOCKED

    in_review_card.refresh_from_db()
    assert in_review_card.status == ProductModeration.ModerationStatus.HARD_BLOCKED
    assert in_review_card.date_moderation is not None

    mock_post.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_hard_block_event_carries_hard_block_true(moderator_client, in_review_card):
    """
    Событие, уходящее в B2B при hard block:
    - event_type = "BLOCKED"
    - hard_block = True
    - product_id совпадает с product_id тикета
    """
    with patch("products.services._post_event") as mock_post:
        moderator_client.post(
            f"/api/v1/tickets/{in_review_card.id}/decline",
            {"hard_block": True},
            format="json",
        )

    mock_post.assert_called_once()
    call_url, call_payload, _ = mock_post.call_args[0]
    assert "/api/v1/moderation/events" in call_url
    assert call_payload["event_type"] == "BLOCKED"
    assert call_payload["hard_block"] is True
    assert call_payload["product_id"] == str(in_review_card.product_id)


def test_any_modify_on_hard_blocked_returns_403(api_client, product_factory):
    """
    Любая попытка изменить HARD_BLOCKED товар → 403 FORBIDDEN.
    Покрывает: PUT product, DELETE product, POST sku.
    """
    product = product_factory(status=Product.Status.HARD_BLOCKED)

    resp_put = api_client.put(
        f"/api/v1/products/{product.id}",
        {
            "title": "New Title",
            "description": "New Description",
            "category_id": str(product.category.id),
            "images": [{"url": "/s3/img.jpg", "ordering": 0}],
        },
        format="json",
    )
    assert resp_put.status_code == 403
    assert resp_put.data["code"] == "FORBIDDEN"

    resp_del = api_client.delete(f"/api/v1/products/{product.id}")
    assert resp_del.status_code == 403
    assert resp_del.data["code"] == "FORBIDDEN"

    resp_sku = api_client.post(
        "/api/v1/skus",
        {
            "product_id": str(product.id),
            "name": "Size M",
            "price": 10000,
            "cost_price": 5000,
            "image": "/s3/sku.jpg",
        },
        format="json",
    )
    assert resp_sku.status_code == 403
    assert resp_sku.data["code"] == "FORBIDDEN"


def test_edited_event_on_hard_blocked_is_ignored(service_api_client, product_factory):
    """
    Событие EDITED от B2B для HARD_BLOCKED товара → игнорируется идемпотентно.
    ProductModeration остаётся в статусе HARD_BLOCKED, moderator_id не сбрасывается.
    """
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    moderator_uuid = uuid.uuid4()
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.HARD_BLOCKED,
        moderator_id=moderator_uuid,
    )

    resp = service_api_client.post(
        "/api/v1/events/product",
        {
            "event": "EDITED",
            "product_id": str(product.id),
            "seller_id": str(product.seller.auth_user_id),
            "date": "2024-01-01T12:00:00Z",
            "idempotency_key": str(uuid.uuid4()),
        },
        format="json",
    )
    assert resp.status_code == 204

    card.refresh_from_db()
    assert card.status == ProductModeration.ModerationStatus.HARD_BLOCKED
    assert card.moderator_id == moderator_uuid


def test_deleted_event_removes_hard_blocked(service_api_client, product_factory):
    """
    Событие DELETED для HARD_BLOCKED товара → удаляет карточку модерации.
    Product.status остаётся HARD_BLOCKED (за статус товара отвечает B2B).
    """
    product = product_factory(status=Product.Status.HARD_BLOCKED)
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.HARD_BLOCKED,
        moderator_id=uuid.uuid4(),
    )

    resp = service_api_client.post(
        "/api/v1/events/product",
        {
            "event": "DELETED",
            "product_id": str(product.id),
            "seller_id": str(product.seller.auth_user_id),
            "date": "2024-01-01T12:00:00Z",
            "idempotency_key": str(uuid.uuid4()),
        },
        format="json",
    )
    assert resp.status_code == 204

    assert not ProductModeration.objects.filter(id=card.id).exists()

    product.refresh_from_db()
    assert product.status == Product.Status.HARD_BLOCKED

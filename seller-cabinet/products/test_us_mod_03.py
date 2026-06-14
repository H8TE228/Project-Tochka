"""
US-MOD-03: одобрение товара модератором.

Канон-flow MOD-3: POST /api/v1/tickets/{ticket_id}/approve
Endpoint переводит карточку IN_REVIEW → MODERATED и эмитирует
событие MODERATED в B2B (канон: POST /api/v1/events/moderation).

DoD:
- approve_transitions_to_moderated_and_emits_event
- approve_others_card_returns_403
- approve_after_edited_returns_409
- approve_without_sku_returns_409
"""
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from products.models import Product, ProductModeration
from seller_cabinet.authentication import TokenUser

pytestmark = pytest.mark.django_db


# ---------- Фикстуры модератора ----------

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


# ---------- Фикстура карточки модерации ----------

@pytest.fixture
def moderation_card(product_factory, moderator_id):
    """Карточка в статусе IN_REVIEW, закреплена за текущим модератором."""
    product = product_factory(status=Product.Status.ON_MODERATION)
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.IN_REVIEW,
        moderator_id=moderator_id,
    )
    return card


# ---------- Тесты DoD ----------

@pytest.mark.django_db(transaction=True)
def test_approve_transitions_to_moderated_and_emits_event(
    moderator_client, moderation_card, sku_factory
):
    """
    Happy path: статус → MODERATED, событие MODERATED отправлено в B2B.

    ADR: для доставки события выбран on_commit (упрощённый outbox).
    Альтернативы:
    1. Синхронный POST внутри транзакции — быстро, но держит lock во время HTTP-вызова;
       если B2B недоступен, придётся откатывать транзакцию (сложнее UX для модератора).
    2. on_commit + fire-and-forget (_post_event) — выбранный вариант: DB-транзакция
       коммитится независимо от B2B; событие уходит после коммита; при потере —
       повторный approve пересоздаёт событие (B2B идемпотентен по idempotency_key).
    3. Полноценный outbox с фоновым воркером — максимальная надёжность, но
       требует scheduler/celery и дополнительной таблицы, избыточно для MVP.
    Критерии выбора: (1) надёжность при отказе B2B — статус сохраняется даже если
    событие потеряно; (2) низкая сложность реализации — не нужен фоновый процесс.
    """
    sku_factory(product=moderation_card.product)

    with patch("products.services._post_event") as mock_post:
        resp = moderator_client.post(
            f"/api/v1/tickets/{moderation_card.id}/approve",
            format="json",
        )

    assert resp.status_code == 200
    assert resp.data["status"] == "APPROVED"
    assert str(moderation_card.id) == resp.data["id"]
    assert str(moderation_card.product.id) == resp.data["product_id"]
    assert str(moderation_card.seller_id) == resp.data["seller_id"]
    assert "kind" in resp.data
    assert "queue_priority" in resp.data
    assert "created_at" in resp.data

    moderation_card.refresh_from_db()
    assert moderation_card.status == ProductModeration.ModerationStatus.MODERATED
    assert moderation_card.date_moderation is not None

    # Событие MODERATED ушло в B2B
    mock_post.assert_called_once()
    call_url, call_payload, _ = mock_post.call_args[0]
    assert "/api/v1/moderation/events" in call_url
    assert call_payload["event_type"] == "MODERATED"
    assert call_payload["product_id"] == str(moderation_card.product.id)


def test_approve_others_card_returns_403(
    moderator_client, product_factory, sku_factory
):
    """
    403: модератор не может одобрить карточку, закреплённую за другим.
    """
    other_moderator_id = uuid.uuid4()
    product = product_factory(status=Product.Status.ON_MODERATION)
    sku_factory(product=product)
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.IN_REVIEW,
        moderator_id=other_moderator_id,  # чужой модератор
    )

    resp = moderator_client.post(
        f"/api/v1/tickets/{card.id}/approve",
        format="json",
    )

    assert resp.status_code == 403
    assert resp.data.get("code") == "FORBIDDEN"


def test_approve_after_edited_returns_409(
    moderator_client, product_factory
):
    """
    409: продавец отредактировал товар во время review — карточка вернулась
    в PENDING (moderator_id сброшен). Повторный approve → 409.
    """
    product = product_factory(status=Product.Status.ON_MODERATION)
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        # EDITED сбрасывает status → PENDING и moderator_id → null
        status=ProductModeration.ModerationStatus.PENDING,
        moderator_id=None,
    )

    resp = moderator_client.post(
        f"/api/v1/tickets/{card.id}/approve",
        format="json",
    )

    assert resp.status_code == 409
    assert resp.data.get("code") == "NOT_IN_REVIEW"


def test_approve_without_sku_returns_409(
    moderator_client, moderation_card
):
    """
    409: товар без SKU нельзя одобрить.
    moderation_card.product создан без SKU.
    """
    # Убеждаемся, что у товара нет SKU
    assert not moderation_card.product.skus.exists()

    resp = moderator_client.post(
        f"/api/v1/tickets/{moderation_card.id}/approve",
        format="json",
    )

    assert resp.status_code == 409
    assert resp.data.get("code") == "NO_SKU"

"""
US-MOD-01: приём событий о товаре от B2B.

POST /api/v1/events/product — межсервисный endpoint.
Идемпотентен по (service_id, idempotency_key).
Авторизация: X-Service-Key (RequireServiceKeyAuthentication).

DoD-тесты:
- created_pending
- edited_returns_to_review
- edited_updates_in_review
- deleted_archived
- duplicate_event_no_side_effects
- missing_service_header_401
"""
import uuid

import pytest
from rest_framework.test import APIClient

from products.models import ProductModeration

pytestmark = pytest.mark.django_db


def _payload(event, product, idempotency_key=None):
    return {
        "event": event,
        "product_id": str(product.id),
        "seller_id": str(product.seller.auth_user_id),
        "date": "2024-01-01T12:00:00Z",
        "idempotency_key": str(idempotency_key or uuid.uuid4()),
    }


def test_created_pending(service_api_client, product_factory):
    """CREATED event creates a moderation card in PENDING."""
    product = product_factory()

    resp = service_api_client.post(
        "/api/v1/events/product",
        _payload("CREATED", product),
        format="json",
    )
    assert resp.status_code == 204

    card = ProductModeration.objects.get(product_id=product.id)
    assert card.status == ProductModeration.ModerationStatus.PENDING
    assert card.seller_id == product.seller.auth_user_id


def test_edited_returns_to_review(service_api_client, product_factory):
    """EDITED after MODERATED/BLOCKED resets card to PENDING (back to review queue)."""
    from products.models import Product
    product = product_factory(status=Product.Status.MODERATED)
    moderator_id = uuid.uuid4()
    ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.MODERATED,
        moderator_id=moderator_id,
    )

    resp = service_api_client.post(
        "/api/v1/events/product",
        _payload("EDITED", product),
        format="json",
    )
    assert resp.status_code == 204

    card = ProductModeration.objects.get(product_id=product.id)
    assert card.status == ProductModeration.ModerationStatus.PENDING
    assert card.moderator_id is None


def test_edited_updates_in_review(service_api_client, product_factory):
    """EDITED during IN_REVIEW resets card to PENDING and clears moderator."""
    product = product_factory()
    moderator_id = uuid.uuid4()
    ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.IN_REVIEW,
        moderator_id=moderator_id,
    )

    resp = service_api_client.post(
        "/api/v1/events/product",
        _payload("EDITED", product),
        format="json",
    )
    assert resp.status_code == 204

    card = ProductModeration.objects.get(product_id=product.id)
    assert card.status == ProductModeration.ModerationStatus.PENDING
    assert card.moderator_id is None


def test_deleted_archived(service_api_client, product_factory):
    """DELETED event removes the moderation card from the queue."""
    product = product_factory()
    card = ProductModeration.objects.create(
        product=product,
        seller_id=product.seller.auth_user_id,
        status=ProductModeration.ModerationStatus.PENDING,
    )

    resp = service_api_client.post(
        "/api/v1/events/product",
        _payload("DELETED", product),
        format="json",
    )
    assert resp.status_code == 204
    assert not ProductModeration.objects.filter(id=card.id).exists()


def test_duplicate_event_no_side_effects(service_api_client, product_factory):
    """Повторное событие с тем же idempotency_key -> 204, нет побочных эффектов."""
    product = product_factory()
    ikey = uuid.uuid4()

    resp1 = service_api_client.post(
        "/api/v1/events/product", _payload("CREATED", product, ikey), format="json"
    )
    assert resp1.status_code == 204
    assert ProductModeration.objects.filter(product_id=product.id).count() == 1

    resp2 = service_api_client.post(
        "/api/v1/events/product", _payload("CREATED", product, ikey), format="json"
    )
    assert resp2.status_code == 204
    assert ProductModeration.objects.filter(product_id=product.id).count() == 1


def test_missing_service_header_401(product_factory):
    """Request without X-Service-Key -> 401 Unauthorized."""
    product = product_factory()
    client = APIClient()

    resp = client.post(
        "/api/v1/events/product",
        _payload("CREATED", product),
        format="json",
    )
    assert resp.status_code == 401

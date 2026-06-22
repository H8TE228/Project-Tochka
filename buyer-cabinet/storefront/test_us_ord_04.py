"""US-ORD-04: реакция B2C на события товаров от B2B.

POST /api/v1/events/product — межсервисный endpoint.
Идемпотентен по idempotency_key.
Авторизация: X-Service-Key (RequireServiceKeyAuthentication).

DoD-тесты:
- product_blocked_marks_cart_items_unavailable
- orders_not_affected_by_product_blocked
- idempotent_event_no_side_effects
- missing_service_key_returns_401
"""
import uuid

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from storefront.models import (
    Cart, CartItem, Order, OrderItem, ProcessedProductEvent,
)

pytestmark = pytest.mark.django_db

FAKE_USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FAKE_PRODUCT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SKU_1 = uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc1")
SKU_2 = uuid.UUID("cccccccc-cccc-cccc-cccc-ccccccccccc2")
SKU_OTHER = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture
def service_key(settings):
    settings.SERVICE_API_KEY = "test-service-key"
    settings.SECRET_KEY = "test-secret-key-for-jwt-that-is-long-enough"
    return settings.SERVICE_API_KEY


@pytest.fixture
def service_api_client(service_key):
    client = APIClient()
    client.credentials(HTTP_X_SERVICE_KEY=service_key)
    return client


def _payload(event, sku_ids, idempotency_key=None, product_id=FAKE_PRODUCT_ID):
    return {
        "event": event,
        "product_id": str(product_id),
        "sku_ids": [str(sid) for sid in sku_ids],
        "idempotency_key": str(idempotency_key or uuid.uuid4()),
        "date": "2024-01-01T12:00:00Z",
    }


def _cart_with_items(*sku_ids):
    cart = Cart.objects.create(user_id=FAKE_USER_ID)
    for sku_id in sku_ids:
        CartItem.objects.create(cart=cart, sku_id=sku_id, quantity=2)
    return cart


def test_product_blocked_marks_cart_items_unavailable(service_api_client):
    """PRODUCT_BLOCKED → все cart_items с этими sku_ids получают unavailable_reason."""
    _cart_with_items(SKU_1, SKU_2)
    other_cart = Cart.objects.create(session_id="guest-session")
    CartItem.objects.create(cart=other_cart, sku_id=SKU_OTHER, quantity=1)

    resp = service_api_client.post(
        "/api/v1/b2b/events",
        _payload("PRODUCT_BLOCKED", [SKU_1, SKU_2]),
        format="json",
    )
    assert resp.status_code == 200

    blocked = CartItem.objects.filter(sku_id__in=[SKU_1, SKU_2])
    assert blocked.count() == 2
    for item in blocked:
        assert item.unavailable_reason == CartItem.REASON_PRODUCT_BLOCKED

    untouched = CartItem.objects.get(sku_id=SKU_OTHER)
    assert untouched.unavailable_reason is None


def test_orders_not_affected_by_product_blocked(service_api_client):
    """Заказы с теми же sku_ids не изменяются после PRODUCT_BLOCKED."""
    order = Order.objects.create(
        user_id=FAKE_USER_ID,
        status=Order.STATUS_PAID,
        total_amount=15000,
        delivery_address="addr",
        idempotency_key=uuid.uuid4(),
    )
    item_1 = OrderItem.objects.create(
        order=order,
        sku_id=SKU_1,
        product_id=FAKE_PRODUCT_ID,
        product_title="Phone",
        sku_name="128GB",
        quantity=2,
        unit_price=5000,
        line_total=10000,
    )
    item_2 = OrderItem.objects.create(
        order=order,
        sku_id=SKU_2,
        product_id=FAKE_PRODUCT_ID,
        product_title="Phone",
        sku_name="256GB",
        quantity=1,
        unit_price=5000,
        line_total=5000,
    )

    _cart_with_items(SKU_1, SKU_2)

    resp = service_api_client.post(
        "/api/v1/b2b/events",
        _payload("PRODUCT_BLOCKED", [SKU_1, SKU_2]),
        format="json",
    )
    assert resp.status_code == 200

    order.refresh_from_db()
    item_1.refresh_from_db()
    item_2.refresh_from_db()
    assert order.status == Order.STATUS_PAID
    assert order.total_amount == 15000
    assert item_1.quantity == 2
    assert item_1.unit_price == 5000
    assert item_2.quantity == 1
    assert item_2.unit_price == 5000


def test_idempotent_event_no_side_effects(service_api_client):
    """Повторное событие с тем же idempotency_key → 200 без эффекта."""
    _cart_with_items(SKU_1)
    ikey = uuid.uuid4()

    resp1 = service_api_client.post(
        "/api/v1/b2b/events",
        _payload("PRODUCT_BLOCKED", [SKU_1], idempotency_key=ikey),
        format="json",
    )
    assert resp1.status_code == 200
    item = CartItem.objects.get(sku_id=SKU_1)
    assert item.unavailable_reason == CartItem.REASON_PRODUCT_BLOCKED
    assert ProcessedProductEvent.objects.filter(idempotency_key=ikey).count() == 1

    item.unavailable_reason = None
    item.save(update_fields=["unavailable_reason", "updated_at"])

    resp2 = service_api_client.post(
        "/api/v1/b2b/events",
        _payload("PRODUCT_BLOCKED", [SKU_1], idempotency_key=ikey),
        format="json",
    )
    assert resp2.status_code == 200
    item.refresh_from_db()
    assert item.unavailable_reason is None
    assert ProcessedProductEvent.objects.filter(idempotency_key=ikey).count() == 1


@override_settings(SERVICE_API_KEY="test-service-key")
def test_missing_service_key_returns_401():
    """Запрос без X-Service-Key → 401 Unauthorized."""
    client = APIClient()
    resp = client.post(
        "/api/v1/b2b/events",
        _payload("PRODUCT_BLOCKED", [SKU_1]),
        format="json",
    )
    assert resp.status_code == 401

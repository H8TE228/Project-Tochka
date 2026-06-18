"""US-ORD-05: финальное списание резерва при доставке.

При переходе заказа в DELIVERED вызывается fulfill в B2B.
При падении B2B — асинхронный ретрай, статус DELIVERED не откатывается.

DoD-тесты:
- delivered_status_triggers_fulfill_to_b2b
- fulfill_failure_retried_asynchronously
- repeated_fulfill_idempotent
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from storefront.models import Order, OrderItem

pytestmark = pytest.mark.django_db(transaction=True)

USER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SKU_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PRODUCT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _create_order(status=Order.STATUS_DELIVERING, quantity=2):
    order = Order.objects.create(
        user_id=USER_ID,
        status=status,
        total_amount=9900000,
        delivery_address="ул. Тестовая 1",
        idempotency_key=uuid.uuid4(),
    )
    OrderItem.objects.create(
        order=order,
        sku_id=SKU_ID,
        product_id=PRODUCT_ID,
        product_title="Смартфон Test",
        sku_name="128GB Black",
        quantity=quantity,
        unit_price=4950000,
        line_total=9900000,
    )
    return order


def _fulfill_ok():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "order_id": "test",
        "status": "FULFILLED",
        "processed_at": "2024-01-01T12:00:00Z",
    }
    return mock


def _mark_delivered(order):
    order.status = Order.STATUS_DELIVERED
    order.save(update_fields=["status", "updated_at"])


@patch("storefront.fulfillment.b2b_fulfill", return_value=_fulfill_ok())
def test_delivered_status_triggers_fulfill_to_b2b(mock_fulfill):
    """Happy path: при DELIVERED вызывается fulfill в B2B."""
    order = _create_order(status=Order.STATUS_DELIVERING)
    _mark_delivered(order)

    mock_fulfill.assert_called_once_with(
        str(order.id),
        [{"sku_id": str(SKU_ID), "quantity": 2}],
    )
    order.refresh_from_db()
    assert order.status == Order.STATUS_DELIVERED


@patch("storefront.fulfillment.enqueue_fulfill_retry")
@patch("storefront.fulfillment.b2b_fulfill")
def test_fulfill_failure_retried_asynchronously(mock_fulfill, mock_enqueue_retry):
    """B2B падает → fulfill ретраится, заказ остаётся DELIVERED."""
    from storefront.services import UpstreamUnavailable

    mock_fulfill.side_effect = UpstreamUnavailable("b2b down")
    order = _create_order(status=Order.STATUS_DELIVERING)
    _mark_delivered(order)

    mock_fulfill.assert_called_once()
    mock_enqueue_retry.assert_called_once_with(str(order.id))
    order.refresh_from_db()
    assert order.status == Order.STATUS_DELIVERED


@patch("storefront.fulfillment.b2b_fulfill", return_value=_fulfill_ok())
def test_repeated_fulfill_idempotent(mock_fulfill):
    """Повторный fulfill с тем же order_id → B2B вызывается, идемпотентность на стороне B2B."""
    from storefront.fulfillment import fulfill_order

    order = _create_order(status=Order.STATUS_DELIVERED)

    assert fulfill_order(order) is True
    assert fulfill_order(order) is True
    assert mock_fulfill.call_count == 2
    calls = mock_fulfill.call_args_list
    assert calls[0].args[0] == calls[1].args[0] == str(order.id)
    assert calls[0].args[1] == calls[1].args[1]

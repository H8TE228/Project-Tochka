"""US-ORD-03: отмена заказа.

DoD-обязательные тесты (имена нельзя менять):
- cancel_paid_order_transitions_to_cancelled
- unreserve_failure_transitions_to_cancel_pending
- cancel_assembling_order_returns_409
- other_user_order_returns_404
"""
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status as http_status

from storefront.services import UpstreamUnavailable
from .models import Order, OrderItem, User


USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SKU_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PRODUCT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def make_jwt(user_id):
    import jwt
    from django.conf import settings
    payload = {"user_id": str(user_id), "email": f"{user_id}@test.com", "role": "buyer"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _create_order(user_id, order_status=Order.STATUS_PAID):
    order = Order.objects.create(
        user_id=user_id,
        status=order_status,
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
        quantity=2,
        unit_price=4950000,
        line_total=9900000,
    )
    return order


def _unreserve_ok():
    mock = MagicMock()
    mock.status_code = 200
    return mock


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class OrderCancelTests(TestCase):
    def setUp(self):
        User.objects.create(id=1, username="buyer_a", email=f"{USER_A_ID}@test.com")
        User.objects.create(id=2, username="buyer_b", email=f"{USER_B_ID}@test.com")

        self.client_a = APIClient()
        self.client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt(USER_A_ID)}")

        self.client_b = APIClient()
        self.client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt(USER_B_ID)}")

    # -------------- happy: cancel_paid_order_transitions_to_cancelled --------------
    @patch("storefront.views.b2b_unreserve")
    def test_cancel_paid_order_transitions_to_cancelled(self, mock_unreserve):
        """
        Happy path: PAID заказ, B2B unreserve возвращает 200.
        Ожидаем: 200, статус → CANCELLED.
        """
        mock_unreserve.return_value = _unreserve_ok()
        order = _create_order(USER_A_ID, order_status=Order.STATUS_PAID)

        resp = self.client_a.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == http_status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["status"] == Order.STATUS_CANCELLED

        order.refresh_from_db()
        assert order.status == Order.STATUS_CANCELLED

        mock_unreserve.assert_called_once()

    # -------------- unhappy: unreserve_failure_transitions_to_cancel_pending --------------
    @patch("storefront.views.b2b_unreserve")
    def test_unreserve_failure_transitions_to_cancel_pending(self, mock_unreserve):
        """
        B2B unreserve недоступен → намерение принято, статус → CANCEL_PENDING.
        Async retry выполнит unreserve позже (scaffold: только статус без retry).
        """
        mock_unreserve.side_effect = UpstreamUnavailable("b2b down")
        order = _create_order(USER_A_ID, order_status=Order.STATUS_PAID)

        resp = self.client_a.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == http_status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["status"] == Order.STATUS_CANCEL_PENDING

        order.refresh_from_db()
        assert order.status == Order.STATUS_CANCEL_PENDING

    # -------------- unhappy: cancel_assembling_order_returns_409 --------------
    def test_cancel_assembling_order_returns_409(self):
        """
        Заказ в DELIVERED нельзя отменить → 409 CANCEL_NOT_ALLOWED с current_status.
        ASSEMBLING и DELIVERING — отменяемые статусы; DELIVERED — терминальный.
        B2B не вызывается, статус заказа не меняется.
        """
        order = _create_order(USER_A_ID, order_status=Order.STATUS_DELIVERED)

        resp = self.client_a.post(f"/api/v1/orders/{order.id}/cancel")
        assert resp.status_code == http_status.HTTP_409_CONFLICT, resp.content

        data = resp.json()
        assert data["code"] == "CANCEL_NOT_ALLOWED"
        assert data["current_status"] == Order.STATUS_DELIVERED

        order.refresh_from_db()
        assert order.status == Order.STATUS_DELIVERED

    # -------------- unhappy: other_user_order_returns_404 --------------
    def test_other_user_order_returns_404(self):
        """
        IDOR: попытка отменить чужой заказ → 404, не 403.
        Факт существования заказа другого пользователя не раскрывается.
        """
        order_b = _create_order(USER_B_ID, order_status=Order.STATUS_PAID)

        resp = self.client_a.post(f"/api/v1/orders/{order_b.id}/cancel")
        assert resp.status_code == http_status.HTTP_404_NOT_FOUND, (
            f"Expected 404 (IDOR protection), got {resp.status_code}"
        )
        assert resp.status_code != http_status.HTTP_403_FORBIDDEN

        data = resp.json()
        assert data.get("code") == "ORDER_NOT_FOUND"

        order_b.refresh_from_db()
        assert order_b.status == Order.STATUS_PAID

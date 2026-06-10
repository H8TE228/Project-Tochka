"""US-ORD-01: оформление заказа (checkout).

DoD-обязательные тесты (имена нельзя менять):
- checkout_creates_paid_order_with_fixed_prices
- partial_reserve_failure_returns_409
- idempotency_returns_existing_order
- b2b_unavailable_returns_503
"""
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status as http_status

from .models import Order, OrderItem, User


FAKE_USER_ID = uuid.UUID("deadbeef-dead-beef-dead-beefdeadbeef")

SKU_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
SKU_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
PRODUCT_A = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def make_jwt(user_id=FAKE_USER_ID):
    import jwt
    from django.conf import settings
    payload = {"user_id": str(user_id), "email": "buyer@test.com", "role": "buyer"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _b2b_products_response(skus_available=True):
    """Имитирует GET /api/v1/public/products — возвращает продукт с двумя SKU."""
    sku_a = {
        "id": SKU_A,
        "name": "128GB Black",
        "price": 9900000,  # в копейках
        "active_quantity": 10 if skus_available else 0,
    }
    sku_b = {
        "id": SKU_B,
        "name": "256GB White",
        "price": 12000000,
        "active_quantity": 5 if skus_available else 0,
    }
    return {
        "items": [
            {
                "id": PRODUCT_A,
                "title": "Смартфон X",
                "status": "MODERATED",
                "skus": [sku_a, sku_b],
            }
        ],
        "total_count": 1,
    }


def _reserve_success():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "reserved": True,
        "items": [
            {"sku_id": SKU_A, "reserved_quantity": 2, "remaining_stock": 8},
            {"sku_id": SKU_B, "reserved_quantity": 1, "remaining_stock": 4},
        ],
    }
    return mock


def _reserve_409(failed_sku=SKU_B):
    mock = MagicMock()
    mock.status_code = 409
    mock.json.return_value = {
        "reserved": False,
        "failed_items": [
            {"sku_id": failed_sku, "requested": 1, "available": 0, "reason": "INSUFFICIENT_STOCK"},
        ],
    }
    return mock


def _b2b_503():
    mock = MagicMock()
    mock.status_code = 503
    return mock


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class CheckoutTests(TestCase):
    def setUp(self):
        User.objects.create(id=1, username="buyer_ord", email="buyer@test.com")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt()}")

    def _checkout_payload(self, idempotency_key=None):
        return {
            "idempotency_key": str(idempotency_key or uuid.uuid4()),
            "items": [
                {"sku_id": SKU_A, "quantity": 2},
                {"sku_id": SKU_B, "quantity": 1},
            ],
            "delivery_address": "ул. Ленина 1, кв. 5",
        }

    # -------------- happy: checkout_creates_paid_order_with_fixed_prices --------------
    @patch("storefront.views.b2b_reserve")
    @patch("storefront.views.b2b_get_products")
    def test_checkout_creates_paid_order_with_fixed_prices(self, mock_get_products, mock_reserve):
        """
        Happy path: B2B доступен, все SKU в наличии, резервирование прошло.
        Ответ: 201, status=PAID, unit_price зафиксирован в OrderItem.
        """
        mock_get_products.return_value = _b2b_products_response(skus_available=True)
        mock_reserve.return_value = _reserve_success()

        payload = self._checkout_payload()
        resp = self.client.post("/api/v1/orders", payload, format="json")
        assert resp.status_code == http_status.HTTP_201_CREATED, resp.content

        data = resp.json()
        assert data["status"] == "PAID"
        assert len(data["items"]) == 2

        # Цены зафиксированы в OrderItem
        item_a = next(i for i in data["items"] if str(i["sku_id"]) == SKU_A)
        assert item_a["unit_price"] == 9900000
        assert item_a["line_total"] == 9900000 * 2
        assert item_a["product_title"] == "Смартфон X"

        # В БД тоже фиксация
        order = Order.objects.get(id=data["id"])
        assert order.status == Order.STATUS_PAID
        assert OrderItem.objects.filter(order=order).count() == 2

    # -------------- unhappy: partial_reserve_failure_returns_409 --------------
    @patch("storefront.views.b2b_reserve")
    @patch("storefront.views.b2b_get_products")
    def test_partial_reserve_failure_returns_409(self, mock_get_products, mock_reserve):
        """
        Хотя бы один SKU не резервируется → 409 RESERVE_FAILED с failed_items.
        All-or-nothing: заказ не создаётся.
        """
        mock_get_products.return_value = _b2b_products_response(skus_available=True)
        mock_reserve.return_value = _reserve_409(failed_sku=SKU_B)

        payload = self._checkout_payload()
        resp = self.client.post("/api/v1/orders", payload, format="json")
        assert resp.status_code == http_status.HTTP_409_CONFLICT, resp.content

        data = resp.json()
        assert data["code"] == "RESERVE_FAILED"
        assert "failed_items" in data
        assert any(fi["sku_id"] == SKU_B for fi in data["failed_items"])

        # Заказ НЕ создан
        assert Order.objects.count() == 0

    # -------------- happy: idempotency_returns_existing_order --------------
    @patch("storefront.views.b2b_reserve")
    @patch("storefront.views.b2b_get_products")
    def test_idempotency_returns_existing_order(self, mock_get_products, mock_reserve):
        """
        Повторный POST с тем же idempotency_key возвращает существующий заказ (200),
        не создаёт дублей и не вызывает повторное резервирование.
        """
        mock_get_products.return_value = _b2b_products_response(skus_available=True)
        mock_reserve.return_value = _reserve_success()

        idempotency_key = uuid.uuid4()
        payload = self._checkout_payload(idempotency_key=idempotency_key)

        # Первый запрос
        resp1 = self.client.post("/api/v1/orders", payload, format="json")
        assert resp1.status_code == http_status.HTTP_201_CREATED

        # Сбрасываем моки чтобы убедиться что второй запрос не дёргает B2B
        mock_get_products.reset_mock()
        mock_reserve.reset_mock()

        # Повторный запрос с тем же ключом
        resp2 = self.client.post("/api/v1/orders", payload, format="json")
        assert resp2.status_code == http_status.HTTP_200_OK, resp2.content
        assert resp2.json()["id"] == resp1.json()["id"]

        # B2B не вызывался при повторном запросе
        mock_get_products.assert_not_called()
        mock_reserve.assert_not_called()

        # Дублей нет
        assert Order.objects.count() == 1

    # -------------- unhappy: b2b_unavailable_returns_503 --------------
    @patch("storefront.views.b2b_get_products")
    def test_b2b_unavailable_returns_503(self, mock_get_products):
        """
        B2B недоступен (UpstreamUnavailable) при проверке наличия товаров → 503.
        """
        from storefront.services import UpstreamUnavailable
        mock_get_products.side_effect = UpstreamUnavailable("b2b down")

        payload = self._checkout_payload()
        resp = self.client.post("/api/v1/orders", payload, format="json")
        assert resp.status_code == http_status.HTTP_503_SERVICE_UNAVAILABLE, resp.content
        assert resp.json()["code"] == "B2B_UNAVAILABLE"

    # Дополнительные сценарии
    def test_checkout_requires_auth(self):
        """Без JWT → 401 или 403 (требуется авторизация)."""
        anon = APIClient()
        resp = anon.post("/api/v1/orders", self._checkout_payload(), format="json")
        assert resp.status_code in (
            http_status.HTTP_401_UNAUTHORIZED,
            http_status.HTTP_403_FORBIDDEN,
        ), resp.content

    def test_empty_items_returns_400(self):
        """items: [] → 400 (невалидный запрос)."""
        payload = {
            "idempotency_key": str(uuid.uuid4()),
            "items": [],
        }
        resp = self.client.post("/api/v1/orders", payload, format="json")
        assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

    @patch("storefront.views.b2b_reserve")
    @patch("storefront.views.b2b_get_products")
    def test_get_order_list(self, mock_get_products, mock_reserve):
        """GET /api/v1/orders возвращает список заказов пользователя."""
        mock_get_products.return_value = _b2b_products_response(skus_available=True)
        mock_reserve.return_value = _reserve_success()

        self.client.post("/api/v1/orders", self._checkout_payload(), format="json")

        resp = self.client.get("/api/v1/orders")
        assert resp.status_code == http_status.HTTP_200_OK
        data = resp.json()
        assert data["total_count"] == 1
        assert len(data["items"]) == 1

    @patch("storefront.views.b2b_reserve")
    @patch("storefront.views.b2b_get_products")
    def test_get_order_detail(self, mock_get_products, mock_reserve):
        """GET /api/v1/orders/{id} возвращает детали заказа с позициями."""
        mock_get_products.return_value = _b2b_products_response(skus_available=True)
        mock_reserve.return_value = _reserve_success()

        create_resp = self.client.post("/api/v1/orders", self._checkout_payload(), format="json")
        order_id = create_resp.json()["id"]

        resp = self.client.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == http_status.HTTP_200_OK
        assert resp.json()["id"] == order_id
        assert len(resp.json()["items"]) == 2

    def test_get_order_404_for_unknown(self):
        """GET /api/v1/orders/{unknown_id} → 404."""
        resp = self.client.get(f"/api/v1/orders/{uuid.uuid4()}")
        assert resp.status_code == http_status.HTTP_404_NOT_FOUND

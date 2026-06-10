"""US-CART-03: корзина покупателя.

DoD-обязательные тесты (имена нельзя менять):
- add_sku_increments_quantity_if_already_in_cart
- get_cart_enriched_with_b2b_data
- unavailable_sku_shown_with_reason
- guest_cart_merged_on_login
"""
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from .models import Cart, CartItem, User


FAKE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
FAKE_PRODUCT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
FAKE_SKU_ID_1 = uuid.UUID("44444444-4444-4444-4444-444444444401")
FAKE_SKU_ID_2 = uuid.UUID("44444444-4444-4444-4444-444444444402")


def make_jwt_token(user_id=FAKE_USER_ID):
    import jwt
    from django.conf import settings
    payload = {"user_id": str(user_id), "email": "buyer@test", "role": "buyer"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _b2b_payload(skus):
    """Сборка ответа B2B GET /products — один продукт с переданными SKU."""
    return {
        "items": [
            {
                "id": str(FAKE_PRODUCT_ID),
                "title": "Test Phone",
                "skus": skus,
            }
        ],
        "total_count": 1,
        "limit": 1000,
        "offset": 0,
    }


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class CartTests(TestCase):
    def setUp(self):
        # User создаётся для совместимости с auth-таблицей; для cart реально нужен только id.
        User.objects.create(id=1, username="buyer1", email="buyer@test")
        self.client = APIClient()
        self.auth_client = APIClient()
        self.auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt_token()}")

    # -------------- happy: add_sku_increments_quantity_if_already_in_cart --------------
    @patch("storefront.views.b2b_get_products")
    def test_add_sku_increments_quantity_if_already_in_cart(self, mock_b2b):
        """Повторное добавление того же SKU увеличивает quantity, не дублирует строку."""
        mock_b2b.return_value = _b2b_payload([
            {"id": str(FAKE_SKU_ID_1), "name": "Black", "price": 100, "active_quantity": 100, "image": ""},
        ])

        body = {"sku_id": str(FAKE_SKU_ID_1), "quantity": 2}
        first = self.auth_client.post("/api/v1/cart/items", body, format="json")
        assert first.status_code in (200, 201), first.content

        body2 = {"sku_id": str(FAKE_SKU_ID_1), "quantity": 3}
        second = self.auth_client.post("/api/v1/cart/items", body2, format="json")
        assert second.status_code in (200, 201), second.content

        # Должна быть одна позиция, quantity = 2 + 3 = 5
        assert CartItem.objects.filter(sku_id=FAKE_SKU_ID_1).count() == 1
        item = CartItem.objects.get(sku_id=FAKE_SKU_ID_1)
        assert item.quantity == 5

    # -------------- happy: get_cart_enriched_with_b2b_data --------------
    @patch("storefront.views.b2b_get_products")
    def test_get_cart_enriched_with_b2b_data(self, mock_b2b):
        """GET /cart обогащает позиции данными из B2B: price, name, image, total_amount."""
        mock_b2b.return_value = _b2b_payload([
            {"id": str(FAKE_SKU_ID_1), "name": "Black 256GB", "price": 50000, "active_quantity": 10, "image": "/s3/x.jpg"},
        ])

        # положим SKU в корзину
        self.auth_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_1), "quantity": 2},
            format="json",
        )

        resp = self.auth_client.get("/api/v1/cart")
        assert resp.status_code == 200, resp.content
        assert len(resp.data["items"]) == 1
        row = resp.data["items"][0]
        assert row["sku_id"] == str(FAKE_SKU_ID_1)
        assert row["quantity"] == 2
        assert row["price"] == 50000
        assert row["name"] == "Black 256GB"
        assert row["image"] == "/s3/x.jpg"
        assert row["available"] is True
        assert row["unavailable_reason"] is None
        # total = 50000 * 2
        assert resp.data["total_amount"] == 100000

    # -------------- unhappy: unavailable_sku_shown_with_reason --------------
    @patch("storefront.views.b2b_get_products")
    def test_unavailable_sku_shown_with_reason(self, mock_b2b):
        """Out-of-stock SKU остаётся в ответе с unavailable_reason, но в total_amount не входит."""
        mock_b2b.return_value = _b2b_payload([
            # SKU_1 в наличии 5
            {"id": str(FAKE_SKU_ID_1), "name": "OK SKU", "price": 1000, "active_quantity": 5, "image": ""},
            # SKU_2 кончился
            {"id": str(FAKE_SKU_ID_2), "name": "Out of stock SKU", "price": 9999, "active_quantity": 0, "image": ""},
        ])

        # Положим обе позиции по 1 шт
        self.auth_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_1), "quantity": 1},
            format="json",
        )
        self.auth_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_2), "quantity": 1},
            format="json",
        )

        resp = self.auth_client.get("/api/v1/cart")
        assert resp.status_code == 200, resp.content
        rows_by_sku = {r["sku_id"]: r for r in resp.data["items"]}

        # Доступный SKU
        assert rows_by_sku[str(FAKE_SKU_ID_1)]["available"] is True
        assert rows_by_sku[str(FAKE_SKU_ID_1)]["unavailable_reason"] is None

        # Недоступный SKU остаётся виден, с причиной
        assert rows_by_sku[str(FAKE_SKU_ID_2)]["available"] is False
        assert rows_by_sku[str(FAKE_SKU_ID_2)]["unavailable_reason"] == "out_of_stock"

        # В total_amount недоступная позиция не входит → 1000 * 1
        assert resp.data["total_amount"] == 1000

    # -------------- unhappy: guest_cart_merged_on_login --------------
    @patch("storefront.views.b2b_get_products")
    def test_guest_cart_merged_on_login(self, mock_b2b):
        """
        Merge гостя в пользователя: при конфликте по SKU берётся MAX(guest, auth).
        Гостевая корзина удаляется после merge.
        """
        mock_b2b.return_value = _b2b_payload([
            {"id": str(FAKE_SKU_ID_1), "name": "Shared SKU", "price": 100, "active_quantity": 100, "image": ""},
            {"id": str(FAKE_SKU_ID_2), "name": "Guest-only SKU", "price": 200, "active_quantity": 100, "image": ""},
        ])

        # Гость: SKU_1 = 5 шт + SKU_2 = 1 шт
        guest_session = "guest-session-abc-123"
        guest_client = APIClient()
        guest_client.credentials(HTTP_X_SESSION_ID=guest_session)
        guest_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_1), "quantity": 5},
            format="json",
        )
        guest_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_2), "quantity": 1},
            format="json",
        )

        # Пользователь сначала имел SKU_1 = 2 → после merge должно стать MAX(2, 5) = 5
        self.auth_client.post(
            "/api/v1/cart/items",
            {"sku_id": str(FAKE_SKU_ID_1), "quantity": 2},
            format="json",
        )

        # Merge: тот же auth client + X-Session-Id заголовок
        merge_client = APIClient()
        merge_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {make_jwt_token()}",
            HTTP_X_SESSION_ID=guest_session,
        )
        resp = merge_client.post("/api/v1/cart/merge")
        assert resp.status_code == 200, resp.content

        # Гостевой корзины больше нет
        assert not Cart.objects.filter(session_id=guest_session).exists()

        # Пользовательская корзина содержит обе позиции
        user_cart = Cart.objects.get(user_id=FAKE_USER_ID)
        items = {ci.sku_id: ci.quantity for ci in user_cart.items.all()}
        assert items[FAKE_SKU_ID_1] == 5  # MAX(2, 5)
        assert items[FAKE_SKU_ID_2] == 1  # только у гостя был, перенесён
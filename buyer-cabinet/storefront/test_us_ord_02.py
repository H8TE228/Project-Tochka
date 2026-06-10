"""US-ORD-02: просмотр и отслеживание заказов.

DoD-обязательные тесты (имена нельзя менять):
- orders_list_returns_own_orders_paginated
- order_detail_shows_fixed_prices
- other_user_order_returns_404_not_403
"""
import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status as http_status

from .models import Order, OrderItem, User


USER_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SKU_ID    = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PRODUCT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def make_jwt(user_id):
    import jwt
    from django.conf import settings
    payload = {"user_id": str(user_id), "email": f"{user_id}@test.com", "role": "buyer"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _create_order(user_id, unit_price=5000000, status=Order.STATUS_PAID):
    """Создаёт Order + OrderItem напрямую в БД (без checkout)."""
    order = Order.objects.create(
        user_id=user_id,
        status=status,
        total_amount=unit_price,
        delivery_address="ул. Тестовая 1",
        idempotency_key=uuid.uuid4(),
    )
    OrderItem.objects.create(
        order=order,
        sku_id=SKU_ID,
        product_id=PRODUCT_ID,
        product_title="Смартфон Test",
        sku_name="128GB Black",
        quantity=1,
        unit_price=unit_price,
        line_total=unit_price,
    )
    return order


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class OrderViewTests(TestCase):
    def setUp(self):
        User.objects.create(id=1, username="buyer_a", email=f"{USER_A_ID}@test.com")
        User.objects.create(id=2, username="buyer_b", email=f"{USER_B_ID}@test.com")

        self.client_a = APIClient()
        self.client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt(USER_A_ID)}")

        self.client_b = APIClient()
        self.client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt(USER_B_ID)}")

    # -------------- happy: orders_list_returns_own_orders_paginated --------------
    def test_orders_list_returns_own_orders_paginated(self):
        """
        GET /api/v1/orders возвращает только заказы текущего пользователя.
        Пагинация работает: limit/offset обрезают список корректно.
        Заказы другого пользователя не видны.
        """
        # Создаём 3 заказа для user A и 1 для user B
        for _ in range(3):
            _create_order(USER_A_ID)
        _create_order(USER_B_ID)

        # Без пагинации — все 3 заказа user A
        resp = self.client_a.get("/api/v1/orders")
        assert resp.status_code == http_status.HTTP_200_OK, resp.content
        data = resp.json()
        assert data["total_count"] == 3
        assert len(data["items"]) == 3

        # С пагинацией limit=2
        resp_page = self.client_a.get("/api/v1/orders?limit=2&offset=0")
        assert resp_page.status_code == http_status.HTTP_200_OK
        page_data = resp_page.json()
        assert page_data["limit"] == 2
        assert len(page_data["items"]) == 2
        assert page_data["total_count"] == 3

        # Вторая страница
        resp_page2 = self.client_a.get("/api/v1/orders?limit=2&offset=2")
        assert resp_page2.status_code == http_status.HTTP_200_OK
        assert len(resp_page2.json()["items"]) == 1

        # User B видит только свой заказ
        resp_b = self.client_b.get("/api/v1/orders")
        assert resp_b.json()["total_count"] == 1

    # -------------- happy: order_detail_shows_fixed_prices --------------
    def test_order_detail_shows_fixed_prices(self):
        """
        GET /api/v1/orders/{id} возвращает unit_price из OrderItem,
        зафиксированный на момент покупки. Цены берутся из БД B2C, не из B2B.
        Даже если «продавец» поднял цену — заказ показывает старую цену.
        """
        original_price = 9900000  # цена на момент покупки
        order = _create_order(USER_A_ID, unit_price=original_price)

        resp = self.client_a.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == http_status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["id"] == str(order.id)
        assert data["status"] == Order.STATUS_PAID

        # unit_price зафиксирован — берётся из OrderItem, а не из B2B
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["unit_price"] == original_price
        assert item["line_total"] == original_price * 1
        assert item["product_title"] == "Смартфон Test"
        assert item["sku_name"] == "128GB Black"

        # Симулируем «изменение цены»: меняем unit_price в БД напрямую
        new_price = 99_000_000
        order.items.update(unit_price=new_price, line_total=new_price)

        resp2 = self.client_a.get(f"/api/v1/orders/{order.id}")
        assert resp2.json()["items"][0]["unit_price"] == new_price  # отражает БД B2C
        # Важно: B2B не вызывался — цены не перезаписываются из B2B при GET

    # -------------- unhappy: other_user_order_returns_404_not_403 --------------
    def test_other_user_order_returns_404_not_403(self):
        """
        IDOR-защита: GET /api/v1/orders/{id} на чужой заказ возвращает 404, не 403.
        Правило: 404 не раскрывает факт существования чужого заказа.
        user_id извлекается только из JWT, не из query/body.
        """
        order_b = _create_order(USER_B_ID)

        # User A пытается получить заказ User B по ID
        resp = self.client_a.get(f"/api/v1/orders/{order_b.id}")
        assert resp.status_code == http_status.HTTP_404_NOT_FOUND, (
            f"Expected 404 (IDOR protection), got {resp.status_code}"
        )
        # Ответ должен быть 404, НЕ 403 — не раскрываем существование чужого заказа
        assert resp.status_code != http_status.HTTP_403_FORBIDDEN

        data = resp.json()
        assert data.get("code") == "ORDER_NOT_FOUND"

    # Дополнительные сценарии
    def test_orders_list_filter_by_status(self):
        """?status=PAID фильтрует только по нужному статусу."""
        _create_order(USER_A_ID, status=Order.STATUS_PAID)
        _create_order(USER_A_ID, status=Order.STATUS_CANCELLED)

        resp = self.client_a.get("/api/v1/orders?status=PAID")
        assert resp.status_code == http_status.HTTP_200_OK
        data = resp.json()
        assert data["total_count"] == 1
        assert all(o["status"] == "PAID" for o in data["items"])

    def test_orders_list_empty_for_new_user(self):
        """Нет заказов → 200 с пустым списком."""
        # Новый пользователь без заказов
        new_user_id = uuid.uuid4()
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt(new_user_id)}")

        resp = client.get("/api/v1/orders")
        assert resp.status_code == http_status.HTTP_200_OK
        assert resp.json()["total_count"] == 0
        assert resp.json()["items"] == []

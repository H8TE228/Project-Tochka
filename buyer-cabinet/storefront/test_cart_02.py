"""US-CART-02: подписки на изменения товара."""
import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from .models import Subscription, User


FAKE_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
FAKE_PRODUCT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def make_jwt_token(user_id=FAKE_USER_ID):
    import jwt
    from django.conf import settings
    payload = {"user_id": str(user_id), "email": "buyer@test", "role": "buyer"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class SubscriptionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id=1, username="buyer1", email="buyer@test"
        )
        # JWT обязательно содержит user_id; ниже из middleware подтягивается этот же user.
        # Так как у нас тут TokenUser (см. authentication.py), Subscription.user должен
        # ссылаться на реальный User. Подменим auth — пусть тесты используют реальный User.
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt_token()}")

    @patch("storefront.views._b2b_check_product_exists")
    def test_subscribe_returns_201_with_notify_on(self, mock_check):
        """Happy path: подписка создаётся, возвращается 201 с notify_on."""
        mock_check.return_value = None  # товар существует
        resp = self.client.post(
            "/api/v1/subscribe",
            {
                "product_id": str(FAKE_PRODUCT_ID),
                "notify_on": ["back_in_stock", "price_dropped"],
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.content
        assert resp.data["product_id"] == str(FAKE_PRODUCT_ID)
        assert set(resp.data["notify_on"]) == {"back_in_stock", "price_dropped"}
        assert Subscription.objects.count() == 1

    @patch("storefront.views._b2b_check_product_exists")
    def test_duplicate_subscription_returns_409(self, mock_check):
        """Повторная подписка на тот же товар → 409 CONFLICT."""
        mock_check.return_value = None
        body = {"product_id": str(FAKE_PRODUCT_ID), "notify_on": ["back_in_stock"]}
        first = self.client.post("/api/v1/subscribe", body, format="json")
        assert first.status_code == status.HTTP_201_CREATED

        second = self.client.post("/api/v1/subscribe", body, format="json")
        assert second.status_code == status.HTTP_409_CONFLICT
        assert second.data["code"] == "CONFLICT"
        assert Subscription.objects.count() == 1

    @patch("storefront.views._b2b_check_product_exists")
    def test_invalid_notify_on_returns_400(self, mock_check):
        """Пустой / невалидный notify_on → 400."""
        mock_check.return_value = None
        # 1) пустой массив
        resp_empty = self.client.post(
            "/api/v1/subscribe",
            {"product_id": str(FAKE_PRODUCT_ID), "notify_on": []},
            format="json",
        )
        assert resp_empty.status_code == status.HTTP_400_BAD_REQUEST, resp_empty.content

        # 2) неизвестное значение
        resp_unknown = self.client.post(
            "/api/v1/subscribe",
            {"product_id": str(FAKE_PRODUCT_ID), "notify_on": ["lol_unknown_event"]},
            format="json",
        )
        assert resp_unknown.status_code == status.HTTP_400_BAD_REQUEST, resp_unknown.content

    def test_subscribe_to_unknown_product_returns_404(self):
        """Несуществующий товар → 404."""
        # _b2b_check_product_exists делает запрос в B2B; мокаем его поход
        from rest_framework.exceptions import NotFound as DRFNotFound

        with patch("storefront.views._b2b_check_product_exists") as mock_check:
            mock_check.side_effect = DRFNotFound("Product not found")
            resp = self.client.post(
                "/api/v1/subscribe",
                {"product_id": str(FAKE_PRODUCT_ID), "notify_on": ["back_in_stock"]},
                format="json",
            )
        assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.content

    @patch("storefront.views._b2b_check_product_exists")
    def test_delete_subscription_returns_204(self, mock_check):
        """DELETE подписки → 204."""
        mock_check.return_value = None
        created = self.client.post(
            "/api/v1/subscribe",
            {"product_id": str(FAKE_PRODUCT_ID), "notify_on": ["back_in_stock"]},
            format="json",
        )
        sub_id = created.data["id"]
        resp = self.client.delete(f"/api/v1/subscribe/{sub_id}")
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Subscription.objects.filter(id=sub_id).exists()

    def test_subscribe_requires_auth(self):
        """Без JWT — 401/403."""
        client = APIClient()
        resp = client.post(
            "/api/v1/subscribe",
            {"product_id": str(FAKE_PRODUCT_ID), "notify_on": ["back_in_stock"]},
            format="json",
        )
        assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
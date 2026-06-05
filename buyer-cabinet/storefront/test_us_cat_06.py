"""US-CAT-06: Избранное (Favorites)"""
from unittest.mock import patch, MagicMock
import uuid

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from buyer_cabinet.authentication import TokenUser
from .models import Favorite


FAKE_USER_ID = uuid.UUID("12345678-1234-1234-1234-123456789001")
FAKE_PRODUCT_ID = uuid.UUID("87654321-4321-4321-4321-210987654321")
FAKE_JWT_PAYLOAD = {
    "user_id": str(FAKE_USER_ID),
    "email": "test@example.com",
    "role": "buyer",
}


def make_jwt_token():
    import jwt
    from django.conf import settings
    return jwt.encode(FAKE_JWT_PAYLOAD, settings.SECRET_KEY, algorithm="HS256")


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class FavoriteProductViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt_token()}")

    @patch("storefront.models.Favorite.objects")
    @patch("storefront.services.b2b_get")
    def test_add_to_favorites_returns_201(self, b2b_get_mock, objects_mock):
        """Happy path: добавление товара в избранное → 201 Created."""
        b2b_get_mock.return_value = FakeResponse(200, {"id": str(FAKE_PRODUCT_ID), "name": "Test Product", "skus": [], "images": []})
        
        favorite_instance = MagicMock()
        favorite_instance.id = str(uuid.uuid4())
        favorite_instance.user_id = FAKE_USER_ID
        favorite_instance.product_id = FAKE_PRODUCT_ID
        favorite_instance.added_at = "2024-01-01T00:00:00Z"
        
        objects_mock.get_or_create.return_value = (favorite_instance, True)

        response = self.client.post(f"/api/v1/favorites/{FAKE_PRODUCT_ID}")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user_id"], FAKE_USER_ID)
        self.assertEqual(response.data["product_id"], str(FAKE_PRODUCT_ID))
        objects_mock.get_or_create.assert_called_once_with(
            user_id=str(FAKE_USER_ID),
            product_id=FAKE_PRODUCT_ID,
        )

    @patch("storefront.models.Favorite.objects")
    @patch("storefront.services.b2b_get")
    def test_repeat_add_returns_200_not_duplicate(self, b2b_get_mock, objects_mock):
        """Повторное добавление → 200 OK, запись в БД не дублируется."""
        b2b_get_mock.return_value = FakeResponse(200, {"id": str(FAKE_PRODUCT_ID), "name": "Test Product", "skus": [], "images": []})
        
        favorite_instance = MagicMock()
        favorite_instance.id = str(uuid.uuid4())
        favorite_instance.user_id = FAKE_USER_ID
        favorite_instance.product_id = FAKE_PRODUCT_ID
        favorite_instance.added_at = "2024-01-01T00:00:00Z"
        
        objects_mock.get_or_create.return_value = (favorite_instance, False)

        response = self.client.post(f"/api/v1/favorites/{FAKE_PRODUCT_ID}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_id"], FAKE_USER_ID)
        self.assertEqual(response.data["product_id"], str(FAKE_PRODUCT_ID))
        objects_mock.get_or_create.assert_called_once_with(
            user_id=str(FAKE_USER_ID),
            product_id=FAKE_PRODUCT_ID,
        )


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class FavoriteProductListViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {make_jwt_token()}")

    @patch("storefront.models.Favorite.objects")
    @patch("storefront.services.b2b_post")
    def test_blocked_product_excluded_from_list(self, b2b_post_mock, objects_mock):
        """Заблокированный в B2B товар не попадает в ответ GET /favorites."""
        product_ids = [FAKE_PRODUCT_ID]
        
        favorites_qs = MagicMock()
        favorites_qs.values_list.return_value = product_ids
        
        objects_mock.filter.return_value.order_by.return_value = favorites_qs
        
        b2b_post_mock.return_value = FakeResponse(
            200,
            {
                "items": [],
                "total": 0,
            },
        )

        response = self.client.get("/api/v1/favorites")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_count"], 0)

    @patch("storefront.models.Favorite.objects")
    def test_user_id_from_query_is_ignored(self, objects_mock):
        """Если передан user_id в query — игнорируется, берётся из JWT."""
        another_user_id = uuid.UUID("87654321-1234-1234-1234-123456789999")
        
        favorites_qs = MagicMock()
        favorites_qs.values_list.return_value = []
        objects_mock.filter.return_value.order_by.return_value = favorites_qs

        response = self.client.get("/api/v1/favorites", {"user_id": str(another_user_id)})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        objects_mock.filter.assert_called_once_with(user_id=str(FAKE_USER_ID))

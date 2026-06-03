"""US-CAT-05: Категории и навигация"""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient


CATEGORIES_FLAT = [
    {"id": "123e4567-e89b-12d3-a456-426614174000", "parent_id": None, "name": "Electronics", "slug": "electronics"},
    {"id": "123e4567-e89b-12d3-a456-426614174001", "parent_id": "123e4567-e89b-12d3-a456-426614174000", "name": "Phones", "slug": "phones"},
    {"id": "123e4567-e89b-12d3-a456-426614174002", "parent_id": "123e4567-e89b-12d3-a456-426614174001", "name": "Smartphones", "slug": "smartphones"},
]

CATEGORIES_ORPHAN = [
    {"id": "123e4567-e89b-12d3-a456-426614174001", "parent_id": "123e4567-e89b-12d3-a456-426614174099", "name": "Phones", "slug": "phones"},
]

CATEGORIES_CYCLE = [
    {"id": "123e4567-e89b-12d3-a456-426614174000", "parent_id": "123e4567-e89b-12d3-a456-426614174002", "name": "Electronics", "slug": "electronics"},
    {"id": "123e4567-e89b-12d3-a456-426614174001", "parent_id": "123e4567-e89b-12d3-a456-426614174000", "name": "Phones", "slug": "phones"},
    {"id": "123e4567-e89b-12d3-a456-426614174002", "parent_id": "123e4567-e89b-12d3-a456-426614174001", "name": "Smartphones", "slug": "smartphones"},
]

PRODUCT_WITH_CATEGORY = {
    "id": "770e8400-e29b-41d4-a716-446655440002",
    "title": "iPhone 15 Pro Max",
    "category_id": "123e4567-e89b-12d3-a456-426614174002",
    "status": "MODERATED",
    "images": [],
    "skus": [],
}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


@override_settings(B2B_URL="http://b2b.test", SERVICE_API_KEY="test-service-key")
class CategoryViewTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("storefront.services.requests.get")
    def test_category_tree_returns_nested_structure(self, get_mock):
        """Дерево собирается из плоского списка."""
        get_mock.return_value = FakeResponse(200, CATEGORIES_FLAT)

        response = self.client.get("/api/v1/catalog/categories/tree")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "Electronics")
        self.assertEqual(len(response.data[0]["children"]), 1)
        self.assertEqual(response.data[0]["children"][0]["name"], "Phones")
        self.assertEqual(len(response.data[0]["children"][0]["children"]), 1)
        self.assertEqual(response.data[0]["children"][0]["children"][0]["name"], "Smartphones")

    @patch("storefront.services.requests.get")
    def test_breadcrumbs_return_path_from_root(self, get_mock):
        """Цепочка от корня до категории."""
        get_mock.return_value = FakeResponse(200, CATEGORIES_FLAT)

        response = self.client.get(
            "/api/v1/breadcrumbs",
            {"category_id": "123e4567-e89b-12d3-a456-426614174002"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data[0]["name"], "Electronics")
        self.assertEqual(response.data[1]["name"], "Phones")
        self.assertEqual(response.data[2]["name"], "Smartphones")

    @patch("storefront.services.requests.get")
    def test_ambiguous_params_returns_400(self, get_mock):
        """Оба параметра одновременно → 400."""
        get_mock.return_value = FakeResponse(200, CATEGORIES_FLAT)

        response = self.client.get(
            "/api/v1/breadcrumbs",
            {
                "category_id": "123e4567-e89b-12d3-a456-426614174002",
                "product_id": "770e8400-e29b-41d4-a716-446655440002",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "ambiguous_param")
        self.assertIn("only one of category_id or product_id", response.data["message"])

    @patch("storefront.services.requests.get")
    def test_orphan_node_returns_422(self, get_mock):
        """Сломанная иерархия → 422."""
        get_mock.return_value = FakeResponse(200, CATEGORIES_ORPHAN)

        response = self.client.get("/api/v1/catalog/categories/tree")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.data["error"], "orphan_node")
        self.assertIn("hierarchy is broken", response.data["message"])

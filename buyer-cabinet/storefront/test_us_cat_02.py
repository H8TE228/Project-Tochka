"""US-CAT-02: поиск B2C по каталогу."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


@override_settings(B2B_URL="http://b2b.test", SERVICE_API_KEY="test-service-key")
class SearchTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("storefront.services.requests.get")
    def test_search_returns_matching_products(self, get_mock):
        get_mock.return_value = FakeResponse(
            200,
            {
                "total": 1,
                "items": [
                    {
                        "id": "770e8400-e29b-41d4-a716-446655440002",
                        "title": "iPhone 15 Pro Max",
                        "images": [
                            {
                                "id": "880e8400-e29b-41d4-a716-446655440001",
                                "url": "https://cdn.neomarket.ru/images/iphone15.jpg",
                                "ordering": 0,
                            }
                        ],
                        "skus": [
                            {
                                "id": "660e8400-e29b-41d4-a716-446655440001",
                                "price": 12999000,
                                "discount": 500000,
                                "image": "/s3/iphone15.jpg",
                                "active_quantity": 7,
                            }
                        ],
                    }
                ],
            },
        )

        response = self.client.get(
            "/api/v1/catalog/products",
            {
                "q": "iPhone",
                "category_id": "123e4567-e89b-12d3-a456-426614174001",
                "filter[brand]": "Apple",
                "sort": "price_asc",
                "limit": "20",
                "offset": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["items"][0]["name"], "iPhone 15 Pro Max")
        self.assertEqual(response.data["items"][0]["min_price"], 12999000)

        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs["headers"], {"X-Service-Key": "test-service-key"})
        self.assertEqual(get_mock.call_args.args[0], "http://b2b.test/api/v1/public/products")
        self.assertIn(("q", "iPhone"), kwargs["params"])
        self.assertIn(("category_id", "123e4567-e89b-12d3-a456-426614174001"), kwargs["params"])
        self.assertIn(("filter[brand]", "Apple"), kwargs["params"])
        self.assertIn(("sort", "price_asc"), kwargs["params"])
        self.assertIn(("page", "1"), kwargs["params"])
        self.assertIn(("size", "20"), kwargs["params"])

    @patch("storefront.services.requests.get")
    def test_short_query_returns_400(self, get_mock):
        response = self.client.get("/api/v1/catalog/products", {"q": "ip"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")
        self.assertEqual(response.data["message"], "Search query must be at least 3 characters")
        get_mock.assert_not_called()

    @patch("storefront.services.requests.get")
    def test_special_chars_do_not_break_query(self, get_mock):
        get_mock.return_value = FakeResponse(200, {"total": 0, "items": []})

        response = self.client.get(
            "/api/v1/catalog/products",
            {"q": "iPhone%15_'", "sort": "new"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertIn(("q", "iPhone%15_'"), get_mock.call_args.kwargs["params"])

    @patch("storefront.services.requests.get")
    def test_empty_results_returns_200(self, get_mock):
        get_mock.return_value = FakeResponse(200, {"total": 0, "items": []})

        response = self.client.get("/api/v1/catalog/products", {"q": "coffee"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_count"], 0)

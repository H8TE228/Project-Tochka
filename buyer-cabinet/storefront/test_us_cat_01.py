"""US-CAT-01: каталог B2C с фильтрами, сортировкой и фасетами."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests import ConnectionError
from rest_framework.test import APIClient


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


@override_settings(B2B_URL="http://b2b.test", SERVICE_API_KEY="test-service-key")
class CatalogTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("storefront.services.requests.get")
    def test_catalog_returns_filtered_sorted_products(self, get_mock):
        get_mock.return_value = FakeResponse(
            200,
            [
                {
                    "id": "770e8400-e29b-41d4-a716-446655440002",
                    "title": "iPhone 15 Pro Max",
                    "images": [{"url": "https://cdn.neomarket.ru/images/iphone15.jpg"}],
                    "skus": [
                        {
                            "id": "660e8400-e29b-41d4-a716-446655440001",
                            "price": 12999000,
                            "discount": 0,
                            "image": "/s3/iphone15.jpg",
                            "active_quantity": 10,
                        }
                    ],
                },
                {
                    "id": "770e8400-e29b-41d4-a716-446655440003",
                    "title": "Samsung Galaxy S24",
                    "images": [],
                    "skus": [
                        {
                            "id": "660e8400-e29b-41d4-a716-446655440002",
                            "price": 8999000,
                            "discount": 0,
                            "image": "/s3/s24.jpg",
                            "active_quantity": 5,
                        }
                    ],
                },
            ],
        )

        response = self.client.get(
            "/api/v1/products",
            {
                "category_id": "123e4567-e89b-12d3-a456-426614174001",
                "filters[brand]": "Apple",
                "sort": "price_asc",
                "limit": "1",
                "offset": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 2)
        self.assertEqual(response.data["limit"], 1)
        self.assertEqual(response.data["offset"], 0)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["title"], "iPhone 15 Pro Max")
        self.assertEqual(response.data["items"][0]["price"], 12999000)
        self.assertTrue(response.data["items"][0]["in_stock"])

        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs["headers"], {"X-Service-Key": "test-service-key"})
        self.assertIn(("filters[brand]", "Apple"), kwargs["params"])
        self.assertIn(("sort", "price_asc"), kwargs["params"])

    @patch("storefront.services.requests.get")
    def test_facets_return_counts_per_filter_value(self, get_mock):
        payload = {
            "category_id": "123e4567-e89b-12d3-a456-426614174001",
            "facets": [
                {
                    "name": "brand",
                    "values": [
                        {"value": "Apple", "count": 124},
                        {"value": "Samsung", "count": 98},
                    ],
                }
            ],
        }
        get_mock.return_value = FakeResponse(200, payload)

        response = self.client.get(
            "/api/v1/catalog/facets",
            {
                "category_id": "123e4567-e89b-12d3-a456-426614174001",
                "filters[brand]": "Apple",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        self.assertIn(("filters[brand]", "Apple"), get_mock.call_args.kwargs["params"])

    @patch("storefront.services.requests.get")
    def test_invalid_sort_returns_400(self, get_mock):
        response = self.client.get("/api/v1/products", {"sort": "price_sideways"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")
        self.assertIn("rating, popularity, price_asc, price_desc, date_desc, discount_desc", response.data["message"])
        get_mock.assert_not_called()

    @patch("storefront.services.requests.get")
    def test_b2b_unavailable_returns_502(self, get_mock):
        get_mock.side_effect = ConnectionError("B2B is down")

        response = self.client.get("/api/v1/products", {"sort": "rating"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "UPSTREAM_UNAVAILABLE")

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
                            "discount": 0,
                            "image": "/s3/iphone15.jpg",
                            "active_quantity": 10,
                        }
                    ],
                },
                {
                    "id": "770e8400-e29b-41d4-a716-446655440003",
                    "title": "Samsung Galaxy S24",
                    "images": [
                        {
                            "id": "880e8400-e29b-41d4-a716-446655440002",
                            "url": "https://cdn.neomarket.ru/images/s24.jpg",
                            "ordering": 0,
                        }
                    ],
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
            "/api/v1/catalog/products",
            {
                "category_id": "123e4567-e89b-12d3-a456-426614174001",
                "filter[brand]": "Apple",
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
        self.assertEqual(response.data["items"][0]["name"], "iPhone 15 Pro Max")
        self.assertEqual(response.data["items"][0]["min_price"], 12999000)
        self.assertTrue(response.data["items"][0]["has_stock"])
        self.assertEqual(
            response.data["items"][0]["images"][0]["id"],
            "880e8400-e29b-41d4-a716-446655440001",
        )

        _, kwargs = get_mock.call_args
        self.assertEqual(kwargs["headers"], {"X-Service-Key": "test-service-key"})
        self.assertEqual(get_mock.call_args.args[0], "http://b2b.test/api/v1/public/products")
        self.assertIn(("category_id", "123e4567-e89b-12d3-a456-426614174001"), kwargs["params"])
        self.assertIn(("filters[brand]", "Apple"), kwargs["params"])
        self.assertIn(("sort", "price_asc"), kwargs["params"])
        self.assertIn(("page", "1"), kwargs["params"])
        self.assertIn(("size", "1"), kwargs["params"])

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
                "filter[brand]": "Apple",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        self.assertIn(("filter[brand]", "Apple"), get_mock.call_args.kwargs["params"])

    @patch("storefront.services.requests.get")
    def test_category_filters_are_proxied(self, get_mock):
        category_id = "123e4567-e89b-12d3-a456-426614174001"
        payload = {
            "items": [
                {
                    "slug": "brand",
                    "name": "Бренд",
                    "type": "list",
                    "value": ["Apple", "Samsung"],
                }
            ]
        }
        get_mock.return_value = FakeResponse(200, payload)

        response = self.client.get(f"/api/v1/categories/{category_id}/filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)
        self.assertEqual(
            get_mock.call_args.args[0],
            f"http://b2b.test/api/v1/categories/{category_id}/filters",
        )

    @patch("storefront.services.requests.get")
    def test_invalid_sort_returns_400(self, get_mock):
        response = self.client.get("/api/v1/catalog/products", {"sort": "price_sideways"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")
        self.assertIn("price_asc, price_desc, popularity, new", response.data["message"])
        get_mock.assert_not_called()

    @patch("storefront.services.requests.get")
    def test_b2b_unavailable_returns_502(self, get_mock):
        get_mock.side_effect = ConnectionError("B2B is down")

        response = self.client.get("/api/v1/catalog/products", {"sort": "popularity"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "UPSTREAM_UNAVAILABLE")

    @patch("storefront.services.requests.get")
    def test_public_sort_aliases_are_translated_for_b2b(self, get_mock):
        get_mock.return_value = FakeResponse(200, {"total": 0, "items": []})

        response = self.client.get("/api/v1/catalog/products", {"sort": "new"})

        self.assertEqual(response.status_code, 200)
        self.assertIn(("sort", "created_desc"), get_mock.call_args.kwargs["params"])

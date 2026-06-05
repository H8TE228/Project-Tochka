"""US-CAT-03: карточка товара B2C без внутренних полей продавца."""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests import ConnectionError
from rest_framework.test import APIClient


PRODUCT_ID = "770e8400-e29b-41d4-a716-446655440002"
PRODUCT_CARD_URL = f"/api/v1/catalog/products/{PRODUCT_ID}"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def product_payload():
    return {
        "id": PRODUCT_ID,
        "slug": "iphone-15-pro-max",
        "title": "iPhone 15 Pro Max",
        "description": "Apple flagship 2024",
        "status": "MODERATED",
        "deleted": False,
        "images": [
            {
                "id": "880e8400-e29b-41d4-a716-446655440001",
                "url": "https://cdn.neomarket.ru/images/iphone15-front.jpg",
                "ordering": 0,
            },
            {
                "id": "880e8400-e29b-41d4-a716-446655440002",
                "url": "https://cdn.neomarket.ru/images/iphone15-back.jpg",
                "ordering": 1,
            },
        ],
        "characteristics": [{"name": "Бренд", "value": "Apple"}],
        "skus": [
            {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "name": "256GB Black",
                "price": 12999000,
                "cost_price": 9000000,
                "reserved_quantity": 2,
                "discount": 0,
                "image": "/s3/iphone15-black-256.jpg",
                "active_quantity": 10,
                "characteristics": [{"name": "Цвет", "value": "Черный"}],
            },
            {
                "id": "660e8400-e29b-41d4-a716-446655440002",
                "name": "256GB White",
                "price": 12999000,
                "cost_price": 9100000,
                "reserved_quantity": 1,
                "discount": 500000,
                "image": "/s3/iphone15-white-256.jpg",
                "active_quantity": 0,
                "characteristics": [{"name": "Цвет", "value": "Белый"}],
            },
        ],
    }


@override_settings(B2B_URL="http://b2b.test", SERVICE_API_KEY="test-service-key")
class ProductCardTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("storefront.services.requests.get")
    def test_product_card_returns_full_data_with_skus(self, get_mock):
        get_mock.return_value = FakeResponse(200, product_payload())

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], PRODUCT_ID)
        self.assertEqual(response.data["slug"], "iphone-15-pro-max")
        self.assertEqual(response.data["name"], "iPhone 15 Pro Max")
        self.assertEqual(response.data["description"], "Apple flagship 2024")
        self.assertEqual(response.data["min_price"], 12999000)
        self.assertTrue(response.data["has_stock"])
        self.assertNotIn("title", response.data)
        self.assertEqual(
            response.data["images"][0]["id"],
            "880e8400-e29b-41d4-a716-446655440001",
        )
        self.assertEqual(response.data["images"][0]["ordering"], 0)
        self.assertEqual(response.data["characteristics"][0], {"name": "Бренд", "value": "Apple"})
        self.assertEqual(len(response.data["skus"]), 2)
        self.assertEqual(response.data["skus"][0]["price"], 12999000)
        self.assertEqual(response.data["skus"][0]["available_quantity"], 10)
        self.assertEqual(response.data["skus"][1]["discount"], 500000)
        self.assertEqual(response.data["skus"][1]["available_quantity"], 0)

        _, kwargs = get_mock.call_args
        self.assertEqual(
            get_mock.call_args.args[0],
            f"http://b2b.test/api/v1/public/products/{PRODUCT_ID}",
        )
        self.assertEqual(kwargs["headers"], {"X-Service-Key": "test-service-key"})

    @patch("storefront.services.requests.get")
    def test_cost_price_absent_in_response(self, get_mock):
        get_mock.return_value = FakeResponse(200, product_payload())

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cost_price", response.data["skus"][0])
        self.assertNotIn("reserved_quantity", response.data["skus"][0])
        self.assertNotIn("active_quantity", response.data["skus"][0])

    @patch("storefront.services.requests.get")
    def test_blocked_product_returns_404(self, get_mock):
        get_mock.return_value = FakeResponse(
            404,
            {"code": "NOT_FOUND", "message": "Product not found"},
        )

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "NOT_FOUND")

    @patch("storefront.services.requests.get")
    def test_sku_without_stock_is_shown_as_unavailable(self, get_mock):
        get_mock.return_value = FakeResponse(200, product_payload())

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["skus"][0]["in_stock"])
        self.assertFalse(response.data["skus"][1]["in_stock"])

    @patch("storefront.services.requests.get")
    def test_product_card_b2b_unavailable_returns_502(self, get_mock):
        get_mock.side_effect = ConnectionError("B2B is down")

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "UPSTREAM_UNAVAILABLE")

"""US-CAT-04: Похожие товары"""
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests import ConnectionError
from rest_framework.test import APIClient


PRODUCT_ID = "770e8400-e29b-41d4-a716-446655440000"
PRODUCT_CARD_URL = f"/api/v1/catalog/products/{PRODUCT_ID}/similar"
CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174001"
PARENT_CATEGORY_ID = "123e4567-e89b-12d3-a456-426614174011"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def product_payload(number=8) -> list[dict]:
    number = number % 20
    payload = []
    for i in range(number):
        payload.append(
            {
                "id": f"770e8400-e29b-41d4-a716-446655440{i+1:02d}0",
                "slug": f"iphone-{10+i:02d}-pro-max",
                "title": f"iPhone {i+1} Pro Max",
                "description": f"Apple flagship 202{i}",
                "status": "MODERATED",
                "deleted": False,
                "category_id": CATEGORY_ID,
                "images": [
                    {
                        "id": f"880e8400-e29b-41d4-a716-4466554400{i+1:02d}",
                        "url": f"https://cdn.neomarket.ru/images/iphone{10+i:02d}-front.jpg",
                        "ordering": 0,
                    },
                    {
                        "id": f"880e8400-e29b-41d4-a716-4466554500{i+1:02d}",
                        "url": f"https://cdn.neomarket.ru/images/iphone{10+i:02d}-back.jpg",
                        "ordering": 1,
                    },
                ]
            }
        )        
    return payload


@override_settings(B2B_URL="http://b2b.test", SERVICE_API_KEY="test-service-key")
class ProductCardTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("storefront.services.requests.get")
    def test_similar_returns_up_to_8_from_same_category(self, get_mock):
        get_mock.return_value = FakeResponse(200, product_payload(number=8))

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) <= 8)
        for i in range(len(response.data)):
            self.assertEqual(response.data[i]["status"], "MODERATED")
            self.assertIn(response.data[i]["category_id"], [CATEGORY_ID, PARENT_CATEGORY_ID])
            self.assertNotEqual(response.data[i]["id"], PRODUCT_ID)
        _, kwargs = get_mock.call_args
        self.assertEqual(
            get_mock.call_args.args[0],
            f"http://b2b.test/api/v1/public/products/{PRODUCT_ID}/similar",
        )
        self.assertEqual(kwargs["headers"], {"X-Service-Key": "test-service-key"})

    @patch("storefront.services.requests.get")
    def test_empty_category_returns_200_empty_list(self, get_mock):
        get_mock.return_value = FakeResponse(200, product_payload(number=0))

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    @patch("storefront.services.requests.get")
    def test_unknown_product_returns_404(self, get_mock):
        get_mock.return_value = FakeResponse(
            404,
            {"code": "NOT_FOUND", "message": "Product not found"},
        )

        response = self.client.get(PRODUCT_CARD_URL)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "NOT_FOUND")

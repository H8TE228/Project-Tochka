"""US-CART-05: подборки товаров на главной.

DoD-обязательные тесты (имена нельзя менять):
- collections_list_returns_metadata_without_products
- collection_products_enriched_from_b2b
- unavailable_products_in_unavailable_ids
- unknown_collection_returns_404
"""
import uuid
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from .models import Collection, CollectionProduct


FAKE_PRODUCT_ID_1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
FAKE_PRODUCT_ID_2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
FAKE_PRODUCT_ID_3 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


def _b2b_response(items: list) -> MagicMock:
    """Имитирует успешный ответ B2B с переданными товарами."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": items, "total_count": len(items)}
    return mock_resp


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class CollectionListTests(TestCase):
    """GET /api/v1/catalog/collections — публичный, plain array с products."""

    def setUp(self):
        self.client = APIClient()

    # -------------- happy: collections_list_returns_metadata_without_products --------------
    @patch("storefront.views.b2b_post")
    def test_collections_list_returns_metadata_without_products(self, mock_b2b_post):
        """
        Контракт: GET /api/v1/catalog/collections возвращает plain array.
        Каждая подборка содержит метаданные (title, priority) и поле products.
        products не должны содержать товары, недоступные в B2B (что и проверяем в unavailable_ids).
        """
        col = Collection.objects.create(
            title="Хиты продаж",
            description="Лучшие товары месяца",
            priority=10,
            is_active=True,
        )
        CollectionProduct.objects.create(collection=col, product_id=FAKE_PRODUCT_ID_1, ordering=0)
        CollectionProduct.objects.create(collection=col, product_id=FAKE_PRODUCT_ID_2, ordering=1)

        # B2B вернёт только первый товар; второй будет в unavailable_ids
        mock_b2b_post.return_value = _b2b_response([
            {"id": str(FAKE_PRODUCT_ID_1), "title": "Товар 1", "price": 10000},
        ])

        resp = self.client.get("/api/v1/catalog/collections")
        assert resp.status_code == status.HTTP_200_OK, resp.content

        data = resp.json()
        # plain array, не обёртка
        assert isinstance(data, list)
        assert len(data) == 1

        item = data[0]
        assert item["id"] == str(col.id)
        assert item["name"] == "Хиты продаж"
        # Поле products обязательно есть
        assert "products" in item
        # Недоступный товар в unavailable_ids, не в products
        assert str(FAKE_PRODUCT_ID_2) in item["unavailable_ids"]
        assert str(FAKE_PRODUCT_ID_1) not in item["unavailable_ids"]

    def test_inactive_collection_not_returned(self):
        """Неактивная подборка не попадает в список."""
        Collection.objects.create(title="Скрытая", is_active=False, priority=5)
        Collection.objects.create(title="Видимая", is_active=True, priority=5)

        resp = self.client.get("/api/v1/catalog/collections")
        assert resp.status_code == status.HTTP_200_OK
        titles = [i["name"] for i in resp.json()]
        assert "Видимая" in titles
        assert "Скрытая" not in titles

    def test_no_active_collections_returns_200_empty(self):
        """Нет активных подборок → 200 с пустым массивом, не 404."""
        Collection.objects.create(title="Off", is_active=False)

        resp = self.client.get("/api/v1/catalog/collections")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json() == []


@override_settings(
    B2B_URL="http://b2b.test",
    SERVICE_API_KEY="test-service-key",
    SECRET_KEY="test-secret-key-for-jwt-that-is-long-enough",
)
class CollectionProductsTests(TestCase):
    """GET /api/v1/collections/{id}/products — обогащение из B2B."""

    def setUp(self):
        self.client = APIClient()
        self.collection = Collection.objects.create(
            title="Новинки сезона",
            is_active=True,
            priority=1,
        )
        CollectionProduct.objects.create(
            collection=self.collection, product_id=FAKE_PRODUCT_ID_1, ordering=0
        )
        CollectionProduct.objects.create(
            collection=self.collection, product_id=FAKE_PRODUCT_ID_2, ordering=1
        )
        CollectionProduct.objects.create(
            collection=self.collection, product_id=FAKE_PRODUCT_ID_3, ordering=2
        )

    # -------------- happy: collection_products_enriched_from_b2b --------------
    @patch("storefront.views.b2b_post")
    def test_collection_products_enriched_from_b2b(self, mock_b2b_post):
        """
        Товары подборки обогащаются актуальными данными из B2B.
        Ответ содержит items с данными продуктов и пустой unavailable_ids.
        """
        b2b_items = [
            {"id": str(FAKE_PRODUCT_ID_1), "title": "Телефон A", "price": 50000},
            {"id": str(FAKE_PRODUCT_ID_2), "title": "Телефон B", "price": 60000},
            {"id": str(FAKE_PRODUCT_ID_3), "title": "Телефон C", "price": 70000},
        ]
        mock_b2b_post.return_value = _b2b_response(b2b_items)

        url = f"/api/v1/collections/{self.collection.id}/products"
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["collection_id"] == str(self.collection.id)
        assert data["collection_title"] == "Новинки сезона"
        assert len(data["items"]) == 3
        assert data["unavailable_ids"] == []

        # Данные пришли из B2B, а не из локальной БД
        returned_ids = {item["id"] for item in data["items"]}
        assert str(FAKE_PRODUCT_ID_1) in returned_ids
        assert str(FAKE_PRODUCT_ID_2) in returned_ids
        assert str(FAKE_PRODUCT_ID_3) in returned_ids

    # -------------- unhappy: unavailable_products_in_unavailable_ids --------------
    @patch("storefront.views.b2b_post")
    def test_unavailable_products_in_unavailable_ids(self, mock_b2b_post):
        """
        Товары, удалённые/заблокированные в B2B (не вернулись в ответе B2B),
        попадают в unavailable_ids, а не в items. Подборка не ломается.
        Если все товары недоступны — items: [], unavailable_ids: [...] — это валидный ответ.
        """
        # B2B вернул только первый товар; второй и третий — недоступны (удалены/заблокированы)
        b2b_items = [
            {"id": str(FAKE_PRODUCT_ID_1), "title": "Телефон A", "price": 50000},
        ]
        mock_b2b_post.return_value = _b2b_response(b2b_items)

        url = f"/api/v1/collections/{self.collection.id}/products"
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_200_OK, resp.content

        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(FAKE_PRODUCT_ID_1)

        unavailable = data["unavailable_ids"]
        assert str(FAKE_PRODUCT_ID_2) in unavailable
        assert str(FAKE_PRODUCT_ID_3) in unavailable
        assert str(FAKE_PRODUCT_ID_1) not in unavailable

    @patch("storefront.views.b2b_post")
    def test_all_products_unavailable_is_valid_response(self, mock_b2b_post):
        """
        Все товары удалены в B2B → items: [], unavailable_ids: [...].
        Это НЕ ошибка, а 200 OK с валидным телом.
        """
        mock_b2b_post.return_value = _b2b_response([])  # B2B вернул пусто

        url = f"/api/v1/collections/{self.collection.id}/products"
        resp = self.client.get(url)
        assert resp.status_code == status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["items"] == []
        assert len(data["unavailable_ids"]) == 3

    # -------------- unhappy: unknown_collection_returns_404 --------------
    def test_unknown_collection_returns_404(self):
        """
        Запрос товаров несуществующей подборки → 404.
        """
        fake_id = uuid.uuid4()
        resp = self.client.get(f"/api/v1/collections/{fake_id}/products")
        assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.content

    def test_empty_collection_returns_200_empty(self):
        """Подборка без товаров → 200 с пустыми items и unavailable_ids."""
        empty_col = Collection.objects.create(title="Пустая", is_active=True)

        resp = self.client.get(f"/api/v1/collections/{empty_col.id}/products")
        assert resp.status_code == status.HTTP_200_OK, resp.content

        data = resp.json()
        assert data["items"] == []
        assert data["unavailable_ids"] == []
        assert data["total_products"] == 0


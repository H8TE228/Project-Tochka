"""
Тесты для обработки moderation событий (B2B-9).

Канон: flows/b2b-flows.md#apply-moderation
OpenAPI: b2b/openapi.yaml — POST /api/v1/events/moderation
"""
import uuid
from unittest.mock import patch, MagicMock

import pytest
from rest_framework.test import APIClient

from products.models import Product, BlockingReason, ProcessedModerationEvent


pytestmark = pytest.mark.django_db


def _moderation_event_payload(
    product_id,
    event_type="MODERATED",
    hard_block=False,
    blocking_reason_id=None,
    field_reports=None,
    idempotency_key=None,
):
    """Базовая структура moderation event."""
    return {
        "product_id": str(product_id),
        "event_type": event_type,
        "hard_block": hard_block,
        "occurred_at": "2024-01-01T12:00:00Z",
        "blocking_reason_id": str(blocking_reason_id) if blocking_reason_id else None,
        "field_reports": field_reports,
        "idempotency_key": str(idempotency_key or uuid.uuid4()),
    }


class TestModerationEventClears:
    """MODERATED сценарий: одобрение товара."""

    def test_moderated_event_clears_blocking_data(
        self, service_api_client, product_factory, db
    ):
        """DoD: MODERATED → status=MODERATED, blocking_reason=None, field_reports=[]."""
        blocking_reason = BlockingReason.objects.create(title="违禁词")
        product = product_factory(
            status=Product.Status.BLOCKED,
            blocking_reason=blocking_reason,
            field_reports=[{"field": "title", "reason": "Prohibited word"}],
            moderator_comment="Review needed",
        )

        payload = _moderation_event_payload(
            product.id,
            event_type="MODERATED",
        )

        resp = service_api_client.post("/api/v1/moderation/events", payload, format="json")
        assert resp.status_code == 204

        product.refresh_from_db()
        assert product.status == Product.Status.MODERATED
        assert product.blocking_reason is None
        assert product.field_reports == []
        assert product.moderator_comment == ""

    def test_moderated_no_cascade_event_sent(self, service_api_client, product_factory, db):
        """DoD: MODERATED → НЕ отправляем PRODUCT_BLOCKED в B2C."""
        product = product_factory(status=Product.Status.ON_MODERATION)

        payload = _moderation_event_payload(product.id, event_type="MODERATED")

        with patch("products.services._post_event") as mock_post:
            resp = service_api_client.post(
                "/api/v1/moderation/events", payload, format="json"
            )
            assert resp.status_code == 204
            # При MODERATED НЕ должна быть отправлена PRODUCT_BLOCKED
            mock_post.assert_not_called()


class TestModerationEventBlocked:
    """BLOCKED сценарии: soft и hard блокировка."""

    def test_blocked_soft_saves_field_reports(
        self, service_api_client, product_factory, db
    ):
        """DoD: BLOCKED soft (hard_block=false) → status=BLOCKED, field_reports сохранены."""
        blocking_reason = BlockingReason.objects.create(title="Image quality")
        product = product_factory(status=Product.Status.ON_MODERATION)
        field_reports = [
            {"field": "image_1", "reason": "Too dark"},
            {"field": "image_2", "reason": "Blurry"},
        ]

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=False,
            blocking_reason_id=blocking_reason.id,
            field_reports=field_reports,
        )

        resp = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp.status_code == 204

        product.refresh_from_db()
        assert product.status == Product.Status.BLOCKED
        assert product.blocking_reason_id == blocking_reason.id
        assert product.field_reports == field_reports

    def test_blocked_hard_sets_terminal_status(
        self, service_api_client, product_factory, db
    ):
        """DoD: BLOCKED hard (hard_block=true) → status=HARD_BLOCKED (терминальный)."""
        blocking_reason = BlockingReason.objects.create(title="Counterfeit detected")
        product = product_factory(status=Product.Status.ON_MODERATION)

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=True,
            blocking_reason_id=blocking_reason.id,
        )

        resp = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp.status_code == 204

        product.refresh_from_db()
        assert product.status == Product.Status.HARD_BLOCKED
        assert product.blocking_reason_id == blocking_reason.id

    @pytest.mark.django_db(transaction=True)
    def test_blocked_hard_cascade_uses_new_b2c_contract(
        self, service_api_client, product_factory, sku_factory
    ):
        """DoD: каскад в B2C при HARD блокировке.

        Контракт B2C: POST /api/v1/b2b/events с
        {event_type: "PRODUCT_HARD_BLOCKED", idempotency_key, occurred_at, payload: {product_id}}.
        """
        product = product_factory(status=Product.Status.ON_MODERATION)
        sku_factory(product=product)
        sku_factory(product=product)

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=True,
        )

        with patch("products.services._post_event") as mock_post:
            resp = service_api_client.post(
                "/api/v1/moderation/events", payload, format="json"
            )

        assert resp.status_code == 204
        assert mock_post.call_count == 1
        url, body, _service_key = mock_post.call_args.args

        # 1) Правильный URL
        assert url.endswith("/api/v1/b2b/events"), f"wrong B2C path: {url}"
        # 2) Правильная структура события
        assert body["event_type"] == "PRODUCT_HARD_BLOCKED"
        assert "idempotency_key" in body
        assert "occurred_at" in body
        assert body["payload"] == {"product_id": str(product.id)}
        # 3) Старых полей быть не должно
        assert "event" not in body         # старое плоское поле
        assert "sku_ids" not in body       # больше не нужен
        assert "product_id" not in body    # должно быть только в payload, не в корне
        assert "date" not in body          # переименовано в occurred_at

    @pytest.mark.django_db(transaction=True)
    def test_blocked_soft_cascade_uses_product_blocked_event_type(
        self, service_api_client, product_factory
    ):
        """DoD: при soft-блокировке event_type = PRODUCT_BLOCKED (не PRODUCT_HARD_BLOCKED)."""
        blocking_reason = BlockingReason.objects.create(title="Image quality")
        product = product_factory(status=Product.Status.ON_MODERATION)

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=False,
            blocking_reason_id=blocking_reason.id,
        )

        with patch("products.services._post_event") as mock_post:
            resp = service_api_client.post(
                "/api/v1/moderation/events", payload, format="json"
            )

        assert resp.status_code == 204
        assert mock_post.call_count == 1
        url, body, _ = mock_post.call_args.args
        assert url.endswith("/api/v1/b2b/events")
        assert body["event_type"] == "PRODUCT_BLOCKED"
        assert body["payload"] == {"product_id": str(product.id)}


class TestModerationEventIdempotency:
    """Идемпотентность: (service_id, idempotency_key) → без побочных эффектов."""

    def test_duplicate_event_same_idempotency_key_no_side_effects(
        self, service_api_client, product_factory, db
    ):
        """DoD: повтор события → 204, но статус не меняется, нет дублирования записей."""
        blocking_reason = BlockingReason.objects.create(title="Quality issue")
        product = product_factory(status=Product.Status.ON_MODERATION)
        idempotency_key = uuid.uuid4()

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=False,
            blocking_reason_id=blocking_reason.id,
            idempotency_key=idempotency_key,
        )

        # Первый запрос
        resp1 = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp1.status_code == 204

        product.refresh_from_db()
        first_updated_at = product.updated_at
        first_status = product.status

        # Второй запрос (идентичный)
        resp2 = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp2.status_code == 204

        product.refresh_from_db()
        # Статус и время не изменилась
        assert product.status == first_status
        assert product.updated_at == first_updated_at

        # Только одна запись в ProcessedModerationEvent
        processed_count = ProcessedModerationEvent.objects.filter(
            idempotency_key=idempotency_key
        ).count()
        assert processed_count == 1

    def test_idempotency_key_scoped_to_service_id(self, product_factory, db):
        """DoD: (service_id='svc-a', key='k1') ≠ (service_id='svc-b', key='k1')."""
        from django.conf import settings
        settings.SERVICE_API_KEY = "test-service-key"
        
        product = product_factory(status=Product.Status.ON_MODERATION)
        idempotency_key = uuid.uuid4()
        service_key = "test-service-key"

        # Клиент 1 (service-a)
        client_a = APIClient()
        client_a.credentials(
            HTTP_X_SERVICE_KEY=service_key, HTTP_X_SERVICE_ID="service-a"
        )

        # Клиент 2 (service-b)
        client_b = APIClient()
        client_b.credentials(
            HTTP_X_SERVICE_KEY=service_key, HTTP_X_SERVICE_ID="service-b"
        )

        payload = _moderation_event_payload(
            product.id, event_type="MODERATED", idempotency_key=idempotency_key
        )

        # Первый запрос от service-a
        resp_a = client_a.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp_a.status_code == 204

        product.refresh_from_db()
        assert product.status == Product.Status.MODERATED

        # Второй запрос от service-b с ДРУГИМ event_type (ДОЛЖЕН обработаться повторно)
        payload_b = _moderation_event_payload(
            product.id, event_type="BLOCKED", hard_block=True, idempotency_key=idempotency_key
        )

        resp_b = client_b.post(
            "/api/v1/moderation/events", payload_b, format="json"
        )
        # Ожидаем, что запрос обработается (204), т.к. service_id другой
        assert resp_b.status_code == 204

        product.refresh_from_db()
        # Должно быть HARD_BLOCKED, т.к. событие от service-b обработано отдельно
        assert product.status == Product.Status.HARD_BLOCKED


class TestHardBlockedProductRejectsEdits:
    """HARD_BLOCKED товар: PUT/DELETE → 403."""

    def test_hard_blocked_product_rejects_seller_edits_put(
        self, api_client, product_factory, db
    ):
        """DoD: HARD_BLOCKED → PUT → 403 FORBIDDEN."""
        product = product_factory(status=Product.Status.HARD_BLOCKED)

        payload = {
            "title": "Modified Title",
            "description": "Modified Description",
            "category_id": str(product.category.id),
            "images": [{"url": "/s3/new.jpg", "ordering": 0}],
        }

        resp = api_client.put(
            f"/api/v1/products/{product.id}", payload, format="json"
        )
        assert resp.status_code == 403
        assert resp.data["code"] == "FORBIDDEN"
        assert "hard-blocked" in resp.data["message"].lower()

    def test_hard_blocked_product_rejects_seller_edits_delete(
        self, api_client, product_factory, db
    ):
        """DoD: HARD_BLOCKED → DELETE → 403 FORBIDDEN."""
        product = product_factory(status=Product.Status.HARD_BLOCKED)

        resp = api_client.delete(f"/api/v1/products/{product.id}")
        assert resp.status_code == 403
        assert resp.data["code"] == "FORBIDDEN"
        assert "hard-blocked" in resp.data["message"].lower()

    def test_hard_blocked_product_rejects_add_sku(
        self, api_client, product_factory, db
    ):
        """DoD: HARD_BLOCKED → POST sku → 403 FORBIDDEN."""
        product = product_factory(status=Product.Status.HARD_BLOCKED)

        payload = {
            "product_id": str(product.id),
            "name": "Size XL",
            "price": 50000,
            "cost_price": 30000,
            "image": "/s3/sku.jpg",
        }

        resp = api_client.post("/api/v1/skus", payload, format="json")
        assert resp.status_code == 403
        assert resp.data["code"] == "FORBIDDEN"
        assert "hard-blocked" in resp.data["message"].lower()


class TestModerationEventErrorHandling:
    """Обработка ошибок при moderation event."""

    def test_missing_x_service_id_returns_400(self, db):
        """DoD: Missing X-Service-Id → 400."""
        from django.conf import settings
        settings.SERVICE_API_KEY = "test-service-key"
        
        client = APIClient()
        client.credentials(HTTP_X_SERVICE_KEY="test-service-key")

        payload = {
            "product_id": str(uuid.uuid4()),
            "event_type": "MODERATED",
            "hard_block": False,
            "occurred_at": "2024-01-01T12:00:00Z",
            "idempotency_key": str(uuid.uuid4()),
        }

        resp = client.post("/api/v1/moderation/events", payload, format="json")
        assert resp.status_code == 400
        assert "X-Service-Id" in resp.data["message"]

    def test_missing_service_key_returns_401(self, db):
        """DoD: Missing X-Service-Key → 401."""
        client = APIClient()

        payload = {
            "product_id": str(uuid.uuid4()),
            "event_type": "MODERATED",
            "hard_block": False,
            "occurred_at": "2024-01-01T12:00:00Z",
            "idempotency_key": str(uuid.uuid4()),
        }

        resp = client.post("/api/v1/moderation/events", payload, format="json")
        assert resp.status_code == 401

    def test_invalid_product_id_returns_404(self, service_api_client, db):
        """DoD: Продукт не существует → 404."""
        payload = _moderation_event_payload(
            uuid.uuid4(),  # несуществующий UUID
            event_type="MODERATED",
        )

        resp = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp.status_code == 404

    def test_invalid_blocking_reason_id_returns_400(self, service_api_client, product_factory, db):
        """DoD: Invalid blocking_reason_id → 400."""
        product = product_factory()

        payload = _moderation_event_payload(
            product.id,
            event_type="BLOCKED",
            hard_block=False,
            blocking_reason_id=uuid.uuid4(),  # несуществующий ID
        )

        resp = service_api_client.post(
            "/api/v1/moderation/events", payload, format="json"
        )
        assert resp.status_code == 400


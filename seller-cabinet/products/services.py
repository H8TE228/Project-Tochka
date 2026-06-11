"""
Сервисы поверх ORM. State-machine + публикация событий по канон-flow b2b-flows.md.
"""
import logging
import uuid
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.db import transaction

from .models import Product, SKU, BlockingReason

log = logging.getLogger(__name__)
EVENT_TIMEOUT_SEC = 3


def _iso_now() -> str:
    """ISO 8601 с миллисекундами и Z — точно как в канон-flow."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _post_event(url: str, payload: dict, service_key: str) -> None:
    """Синхронная отправка с X-Service-Key. Сетевые ошибки глушим в лог:
    идемпотентность на стороне получателя (через idempotency_key) делает повтор безопасным;
    для критичной устойчивости в M3 заменим на outbox."""
    try:
        requests.post(
            url,
            json=payload,
            headers={"X-Service-Key": service_key},
            timeout=EVENT_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        log.warning("event delivery failed url=%s payload=%s err=%s", url, payload, exc)


def _build_product_event(event: str, product: Product) -> dict:
    """Тело события B2B → Moderation (канон-flow B2B-2, B2B-3, B2B-4)."""
    return {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product.id),
        "seller_id": str(product.seller.auth_user_id),
        "event": event,
        "date": _iso_now(),
    }


def publish_to_moderation(event: str, product: Product) -> None:
    payload = _build_product_event(event, product)
    url = f"{settings.MOD_URL}/api/v1/events/product"
    key = settings.B2B_TO_MOD_KEY
    transaction.on_commit(lambda: _post_event(url, payload, key))


def publish_product_deleted_to_b2c(product: Product, sku_ids: list[str]) -> None:
    """Канон-flow B2B-4: PRODUCT_DELETED содержит sku_ids."""
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "event": "PRODUCT_DELETED",
        "product_id": str(product.id),
        "sku_ids": [str(s) for s in sku_ids],
        "date": _iso_now(),
    }
    url = f"{settings.B2C_URL}/api/v1/events/product"
    key = settings.B2B_TO_B2C_KEY
    transaction.on_commit(lambda: _post_event(url, payload, key))


def publish_sku_out_of_stock_to_b2c(sku: SKU) -> None:
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "event": "SKU_OUT_OF_STOCK",
        "sku_id": str(sku.id),
        "product_id": str(sku.product_id),
        "date": _iso_now(),
    }
    url = f"{settings.B2C_URL}/api/v1/events/product"
    key = settings.B2B_TO_B2C_KEY
    transaction.on_commit(lambda: _post_event(url, payload, key))


def publish_product_blocked_to_b2c(product: Product, hard_block: bool = False) -> None:
    """
    Канон-flow B2B-5: уведомить B2C о блокировке товара.

    Контракт B2C (spec b2c/openapi.yaml — POST /api/v1/b2b/events):
        body: {event_type, idempotency_key, occurred_at, payload: {product_id}}
        - event_type = "PRODUCT_HARD_BLOCKED" при terminal-блокировке
        - event_type = "PRODUCT_BLOCKED" при soft-блокировке
    sku_ids не передаём — `payload.product_id` достаточен, B2C сам подтянет SKU.
    """
    event_type = "PRODUCT_HARD_BLOCKED" if hard_block else "PRODUCT_BLOCKED"
    payload = {
        "event_type": event_type,
        "idempotency_key": str(uuid.uuid4()),
        "occurred_at": _iso_now(),
        "payload": {"product_id": str(product.id)},
    }
    url = f"{settings.B2C_URL}/api/v1/b2b/events"
    key = settings.B2B_TO_B2C_KEY
    transaction.on_commit(lambda: _post_event(url, payload, key))


def resolve_blocking_reason(reason_text: str | None) -> BlockingReason | None:
    if not reason_text:
        return None
    reason, _ = BlockingReason.objects.get_or_create(title=reason_text.strip()[:500])
    return reason


# ---- State machine ----

def transition_on_first_sku(product: Product) -> bool:
    """US-B2B-02: первый SKU отправляет товар на модерацию."""
    if product.status == Product.Status.CREATED:
        product.status = Product.Status.ON_MODERATION
        product.save(update_fields=["status", "updated_at"])
        publish_to_moderation("CREATED", product)
        return True
    return False


def transition_on_edit(product: Product) -> bool:
    """US-B2B-03: правка MODERATED/BLOCKED -> ON_MODERATION + EDITED."""
    if product.status in (Product.Status.MODERATED, Product.Status.BLOCKED):
        product.status = Product.Status.ON_MODERATION
        product.save(update_fields=["status", "updated_at"])
        publish_to_moderation("EDITED", product)
        return True
    return False


def publish_moderation_approved_to_b2b(product_id: str) -> None:
    """
    US-MOD-03: Moderation → B2B — одобрение товара (канон-flow MOD-3).

    Отправляем событие MODERATED в B2B. Используем transaction.on_commit,
    чтобы событие ушло только после успешного коммита транзакции.
    Повторная доставка безопасна: B2B-сторона (ModerationEventApplyView)
    идемпотентна по (service_id, idempotency_key).

    ADR (краткое): выбран синхронный POST через on_commit (упрощённый outbox).
    Надёжнее прямого вызова в обработчике (статус в БД уже сохранён до отправки),
    проще полноценного outbox с фоновым воркером. При недоступности B2B событие
    теряется, но повторный approve модератором пересоздаст его — приемлемо для MVP.
    """
    payload = {
        "product_id": product_id,
        "event_type": "MODERATED",
        "hard_block": False,
        "occurred_at": _iso_now(),
        "idempotency_key": str(uuid.uuid4()),
        "field_reports": None,
        "blocking_reason_id": None,
    }
    url = f"{settings.B2B_URL}/api/v1/moderation/events"
    key = settings.MOD_TO_B2B_KEY
    transaction.on_commit(lambda: _post_event(url, payload, key))
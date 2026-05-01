"""
Сервисы поверх ORM. State-machine + публикация событий по канон-flow b2b-flows.md.
"""
import logging
import uuid
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.db import transaction

from .models import Product

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
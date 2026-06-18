"""
US-ORD-05: финальное списание резерва при доставке (fulfill в B2B).

При переходе заказа в DELIVERED вызывается b2b_fulfill.
При ошибке заказ остаётся DELIVERED, fulfill ретраится асинхронно.
"""
import logging
import threading
import uuid

from django.db import transaction

from .models import Order
from .services import UpstreamUnavailable, b2b_fulfill

log = logging.getLogger(__name__)

_retry_lock = threading.Lock()
_pending_retries: set[str] = set()
MAX_RETRY_DELAY_SEC = 60.0


def _build_fulfill_items(order: Order) -> list[dict]:
    return [
        {"sku_id": str(item.sku_id), "quantity": item.quantity}
        for item in order.items.all()
    ]


def fulfill_order(order: Order) -> bool:
    """
    Синхронный вызов fulfill в B2B.
    Возвращает True при успехе (2xx), False при ошибке (ретрай будет запланирован вызывающим).
    """
    items = _build_fulfill_items(order)
    if not items:
        log.warning("fulfill skipped: order %s has no items", order.id)
        return True

    try:
        response = b2b_fulfill(str(order.id), items)
    except UpstreamUnavailable as exc:
        log.warning(
            "fulfill upstream unavailable order_id=%s err=%s",
            order.id,
            exc,
        )
        return False

    if response.status_code >= 500:
        log.warning(
            "fulfill B2B error order_id=%s status=%s",
            order.id,
            response.status_code,
        )
        return False

    if response.status_code >= 400:
        log.error(
            "fulfill rejected order_id=%s status=%s body=%s",
            order.id,
            response.status_code,
            response.text,
        )
        return False

    log.info("fulfill succeeded order_id=%s", order.id)
    return True


def enqueue_fulfill_retry(order_id: str, delay_sec: float = 1.0) -> None:
    """Поставить асинхронный ретрай fulfill (MVP: threading.Timer)."""
    order_key = str(order_id)
    with _retry_lock:
        if order_key in _pending_retries:
            return
        _pending_retries.add(order_key)

    def _run_retry():
        try:
            order = Order.objects.prefetch_related("items").get(pk=order_key)
            if order.status != Order.STATUS_DELIVERED:
                return
            if fulfill_order(order):
                return
            enqueue_fulfill_retry(order_key, delay_sec=min(delay_sec * 2, MAX_RETRY_DELAY_SEC))
        except Order.DoesNotExist:
            log.warning("fulfill retry: order %s not found", order_key)
        except Exception as exc:
            log.warning("fulfill retry failed order_id=%s err=%s", order_key, exc)
            enqueue_fulfill_retry(order_key, delay_sec=min(delay_sec * 2, MAX_RETRY_DELAY_SEC))
        finally:
            with _retry_lock:
                _pending_retries.discard(order_key)

    timer = threading.Timer(delay_sec, _run_retry)
    timer.daemon = True
    timer.start()


def fulfill_order_on_delivery(order_id: uuid.UUID) -> None:
    """Точка входа из signal: fulfill + ретрай при падении."""
    order = Order.objects.prefetch_related("items").get(pk=order_id)
    if order.status != Order.STATUS_DELIVERED:
        return
    if fulfill_order(order):
        return
    enqueue_fulfill_retry(str(order_id))

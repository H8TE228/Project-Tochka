"""Django signals для storefront."""

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .fulfillment import fulfill_order_on_delivery
from .models import Order


@receiver(pre_save, sender=Order)
def cache_order_previous_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._previous_status = (
                Order.objects.filter(pk=instance.pk)
                .values_list("status", flat=True)
                .first()
            )
        except Exception:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Order)
def trigger_fulfill_on_delivered(sender, instance, created, **kwargs):
    """US-ORD-05: переход в DELIVERED → fulfill в B2B (после commit транзакции)."""
    previous = getattr(instance, "_previous_status", None)
    if instance.status != Order.STATUS_DELIVERED:
        return
    if previous == Order.STATUS_DELIVERED:
        return

    order_id = instance.pk
    transaction.on_commit(lambda: fulfill_order_on_delivery(order_id))

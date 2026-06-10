import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    pass


class Favorite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_id = models.UUIDField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "product_id"], name="unique_user_product")
        ]


# ============================================================
# US-CART-02: подписки на изменения товара
# ============================================================
class Subscription(models.Model):
    """
    Подписка пользователя на события по товару.

    notify_on хранится как JSON-список строк из NOTIFY_ON_CHOICES.
    Идемпотентность создания обеспечена UniqueConstraint(user, product_id):
    повторный POST по тому же товару → 409.
    """

    NOTIFY_BACK_IN_STOCK = "back_in_stock"
    NOTIFY_PRICE_DROPPED = "price_dropped"
    NOTIFY_ON_CHOICES = (NOTIFY_BACK_IN_STOCK, NOTIFY_PRICE_DROPPED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField()
    product_id = models.UUIDField()
    notify_on = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "product_id"], name="unique_subscription_user_product"
            ),
        ]


# ============================================================
# US-CART-03: корзина покупателя
# ============================================================
class Cart(models.Model):
    """
    Корзина — гость (session_id) или авторизованный (user).
    Ровно одно из (user, session_id) не пусто. Контролируется на уровне ORM.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(null=True, blank=True, db_index=True)
    session_id = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id"], name="unique_cart_per_user",
                condition=models.Q(user_id__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["session_id"], name="unique_cart_per_session",
                condition=models.Q(session_id__isnull=False),
            ),
        ]


class CartItem(models.Model):
    """Позиция в корзине — sku_id + quantity. Цена не хранится (берётся из B2B)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    sku_id = models.UUIDField()
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["cart", "sku_id"], name="unique_cart_sku")
        ]


# ============================================================
# US-CART-04: баннеры на главной
# ============================================================
class Banner(models.Model):
    """
    Маркетинговый баннер для главной страницы. Создаётся через Django Admin.

    Видимость:
      - is_active = True
      - starts_at IS NULL OR starts_at <= now()
      - ends_at IS NULL OR ends_at >= now()
    Сортировка — по priority DESC.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    image_url = models.CharField(max_length=2000)
    target_url = models.CharField(max_length=2000)
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class BannerEvent(models.Model):
    """
    CTR-аналитика. Каждое клик/показ — отдельная строка.
    Для MVP — реляционная запись; для прода планируем буфер в Redis с агрегацией.
    """

    EVENT_VIEW = "view"
    EVENT_CLICK = "click"
    EVENT_CHOICES = [(EVENT_VIEW, "View"), (EVENT_CLICK, "Click")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    banner = models.ForeignKey(Banner, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=16, choices=EVENT_CHOICES)
    user_id = models.UUIDField(null=True, blank=True)
    session_id = models.CharField(max_length=128, null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
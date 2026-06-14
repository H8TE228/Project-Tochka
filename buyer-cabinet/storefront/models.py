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


# ============================================================
# US-CART-05: подборки товаров на главной
# ============================================================
class Collection(models.Model):
    """
    Тематическая подборка товаров («Хиты продаж», «Новинки сезона»).
    Создаётся через Django Admin. Хранит только метаданные и ссылки на product_id.
    Актуальные данные товаров запрашиваются из B2B при каждом GET.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    cover_image_url = models.CharField(max_length=500, blank=True, default="")
    target_url = models.CharField(max_length=500, blank=True, default="")
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "-created_at"]


class CollectionProduct(models.Model):
    """
    Связка подборки с товаром. B2C хранит только UUID товара — никаких копий данных.
    Если товар удалён/заблокирован в B2B, он попадает в unavailable_ids при GET.
    """

    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="collection_products"
    )
    product_id = models.UUIDField()
    ordering = models.IntegerField(default=0)

    class Meta:
        unique_together = [("collection", "product_id")]
        ordering = ["ordering"]


# ============================================================
# US-ORD-01: оформление заказа (checkout)
# ============================================================
class Order(models.Model):
    """
    Заказ покупателя. Создаётся через POST /api/v1/orders.

    Идемпотентность: уникальный индекс на idempotency_key — повторный POST с тем же
    ключом возвращает существующий заказ (200), не создаёт дублей.

    Статусная машина:
      PAID → ASSEMBLING → DELIVERING → DELIVERED
      PAID/CREATED → CANCELLED (или CANCEL_PENDING если unreserve не ответил)
    """

    STATUS_CREATED = "CREATED"
    STATUS_PAID = "PAID"
    STATUS_ASSEMBLING = "ASSEMBLING"
    STATUS_DELIVERING = "DELIVERING"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CANCEL_PENDING = "CANCEL_PENDING"

    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_ASSEMBLING, "Assembling"),
        (STATUS_DELIVERING, "Delivering"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_CANCEL_PENDING, "Cancel Pending"),
    ]

    CANCELLABLE_STATUSES = {STATUS_CREATED, STATUS_PAID}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PAID)
    total_amount = models.PositiveBigIntegerField(default=0)
    delivery_address = models.TextField(blank=True, default="")
    idempotency_key = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class OrderItem(models.Model):
    """
    Позиция заказа — исторический снимок товара на момент покупки.
    unit_price, product_title, sku_name фиксируются при создании и не меняются.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    sku_id = models.UUIDField()
    product_id = models.UUIDField()
    product_title = models.CharField(max_length=500)
    sku_name = models.CharField(max_length=500, blank=True, default="")
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveBigIntegerField()
    line_total = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["id"]
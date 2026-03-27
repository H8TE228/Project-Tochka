from django.db import models

from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


class ProductStatus(models.TextChoices):
    """Статусы товара"""
    CREATED = 'CREATED', 'Created'
    ON_MODERATION = 'ON_MODERATION', 'On Moderation'
    MODERATED = 'MODERATED', 'Moderated'
    BLOCKED = 'BLOCKED', 'Blocked'


class CartUnavailableReason(models.TextChoices):
    """Причины недоступности товара в корзине"""
    OUT_OF_STOCK = 'OUT_OF_STOCK', 'Out of stock'
    PRODUCT_BLOCKED = 'PRODUCT_BLOCKED', 'Product blocked'
    PRODUCT_DELISTED = 'PRODUCT_DELISTED', 'Product delisted'
    SKU_DISABLED = 'SKU_DISABLED', 'SKU disabled'


class SubscriptionEventCode(models.TextChoices):
    """Типы событий подписки"""
    IN_STOCK = 'IN_STOCK', 'In stock'
    PRICE_DOWN = 'PRICE_DOWN', 'Price down'


class BannerEventType(models.TextChoices):
    """Типы событий баннеров"""
    IMPRESSION = 'impression', 'Impression'
    CLICK = 'click', 'Click'


class OrderStatus(models.TextChoices):
    """Статусы заказа"""
    CREATED = 'CREATED', 'Created'
    PAID = 'PAID', 'Paid'
    SHIPPED = 'SHIPPED', 'Shipped'
    DELIVERED = 'DELIVERED', 'Delivered'
    CANCELLED = 'CANCELLED', 'Cancelled'


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="core_user_set",
        related_query_name="core_user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="core_user_set",
        related_query_name="core_user",
    )

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email or self.username


class Seller(models.Model):
    """Продавец"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sellers'

    def __str__(self):
        return self.name


class Category(models.Model):
    """Категория товаров"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Product(models.Model):
    """Товар"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='products')
    slug = models.CharField(max_length=255)
    title = models.CharField(max_length=500)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=ProductStatus.choices, default=ProductStatus.CREATED)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        unique_together = ['seller', 'slug']

    def __str__(self):
        return self.title


class SKU(models.Model):
    """SKU (Stock Keeping Unit) - вариант товара"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='skus')
    name = models.CharField(max_length=500)
    price_cents = models.IntegerField()
    active_quantity = models.IntegerField()
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'skus'
        verbose_name = 'SKU'
        verbose_name_plural = 'SKUs'

    def __str__(self):
        return f"{self.product.title} - {self.name}"


class ProductImage(models.Model):
    """Изображения товара"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    url = models.CharField(max_length=2000)
    ordering = models.IntegerField(default=0)

    class Meta:
        db_table = 'product_images'
        ordering = ['ordering']

    def __str__(self):
        return f"Image for {self.product.title}"


class SKUImage(models.Model):
    """Изображения SKU"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name='images')
    url = models.CharField(max_length=2000)
    ordering = models.IntegerField(default=0)

    class Meta:
        db_table = 'sku_images'
        ordering = ['ordering']


class ProductCharacteristic(models.Model):
    """Характеристики товара"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='characteristics')
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=2000)

    class Meta:
        db_table = 'product_characteristics'


class SKUCharacteristic(models.Model):
    """Характеристики SKU"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name='characteristics')
    name = models.CharField(max_length=200)
    value = models.CharField(max_length=2000)

    class Meta:
        db_table = 'sku_characteristics'


class FavoriteItem(models.Model):
    """Избранные товары"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorite_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='favorited_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'favorite_items'
        unique_together = ['user', 'product']


class Cart(models.Model):
    """Корзина"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='carts')
    session_id = models.UUIDField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='RUB')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'carts'


class CartItem(models.Model):
    """Элемент корзины"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name='cart_items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='cart_items')
    product_title = models.CharField(max_length=500)
    sku_name = models.CharField(max_length=500)
    image_url = models.CharField(max_length=2000, null=True, blank=True)
    unit_price_cents = models.IntegerField()
    quantity = models.IntegerField(default=1)
    available_stock = models.IntegerField()
    line_total_cents = models.IntegerField()
    available = models.BooleanField(default=True)
    unavailable_reason = models.CharField(max_length=50, null=True, blank=True)
    unavailable_reason_enum = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = 'cart_items'


class Subscription(models.Model):
    """Подписка на товар"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subscriptions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='subscriptions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subscriptions'
        unique_together = ['user', 'product']


class SubscriptionEventType(models.Model):
    """Типы событий подписки"""
    code = models.CharField(max_length=20, primary_key=True, choices=SubscriptionEventCode.choices)
    label = models.CharField(max_length=200)

    class Meta:
        db_table = 'subscription_event_types'


class SubscriptionEvent(models.Model):
    """Событие подписки"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='events')
    event_type = models.ForeignKey(SubscriptionEventType, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'subscription_events'
        unique_together = ['subscription', 'event_type']


class Banner(models.Model):
    """Баннер"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    image_url = models.CharField(max_length=2000)
    link = models.CharField(max_length=2000)
    priority = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'banners'
        ordering = ['-priority']


class BannerEvent(models.Model):
    """Событие баннера"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    banner = models.ForeignKey(Banner, on_delete=models.CASCADE, related_name='events')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='banner_events')
    event_type = models.CharField(max_length=20, choices=BannerEventType.choices)
    timestamp = models.DateTimeField()

    class Meta:
        db_table = 'banner_events'


class Collection(models.Model):
    """Коллекция товаров"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)
    cover_image_url = models.CharField(max_length=2000)
    target_url = models.CharField(max_length=2000)
    priority = models.IntegerField(default=0)
    start_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'collections'
        ordering = ['-priority']


class CollectionProduct(models.Model):
    """Связь коллекции с товаром"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='products')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='collections')

    class Meta:
        db_table = 'collection_products'
        unique_together = ['collection', 'product']


class Order(models.Model):
    """Заказ"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.CREATED)
    total_amount_cents = models.IntegerField()
    currency = models.CharField(max_length=3)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'orders'


class OrderItem(models.Model):
    """Элемент заказа"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_price_cents = models.IntegerField()
    line_total_cents = models.IntegerField()

    class Meta:
        db_table = 'order_items'


class OrderStatusEvent(models.Model):
    """История статусов заказа"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_events')
    from_status = models.CharField(max_length=20, choices=OrderStatus.choices, null=True, blank=True)
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_status_events'


class Invoice(models.Model):
    """Инвойс (для B2B)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(Seller, on_delete=models.CASCADE, related_name='invoices')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'invoices'


class InvoiceLine(models.Model):
    """Строка инвойса"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT)
    quantity = models.IntegerField()

    class Meta:
        db_table = 'invoice_lines'


class ModerationQueueItem(models.Model):
    """Очередь модерации"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='moderation_queue')
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=ProductStatus.choices)

    class Meta:
        db_table = 'moderation_queue_items'


class ProductSnapshot(models.Model):
    """Снимок товара для модерации"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='snapshots')
    created_at = models.DateTimeField(auto_now_add=True)
    snapshot_kind = models.CharField(max_length=16)  # BEFORE|AFTER
    snapshot_json = models.JSONField()

    class Meta:
        db_table = 'product_snapshots'


class ModerationDecision(models.Model):
    """Решение модератора"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='moderation_decisions')
    moderator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    decision = models.CharField(max_length=16)  # APPROVE|DECLINE
    reason_text = models.TextField(null=True, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.ForeignKey(ProductSnapshot, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'moderation_decisions'

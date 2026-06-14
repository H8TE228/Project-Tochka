from rest_framework import serializers
from .models import Favorite


class FavoritesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Favorite
        fields = ['id', 'user_id', 'product_id', 'added_at',]
        read_only_fields = ['id', 'user_id', 'added_at',]

# ============================================================
# US-CART-02: подписки
# ============================================================
from .models import Subscription, Cart, CartItem, Banner, BannerEvent


class SubscriptionWriteSerializer(serializers.Serializer):
    """POST /api/v1/subscribe — создание подписки на товар."""
    product_id = serializers.UUIDField()
    notify_on = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=10,
    )

    def validate_notify_on(self, value):
        bad = [v for v in value if v not in Subscription.NOTIFY_ON_CHOICES]
        if bad:
            raise serializers.ValidationError(
                f"Unknown event types: {bad}. Allowed: {list(Subscription.NOTIFY_ON_CHOICES)}"
            )
        # уникальные значения, порядок не важен
        return list(dict.fromkeys(value))


class SubscriptionReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ("id", "product_id", "notify_on", "created_at")


# ============================================================
# US-CART-03: корзина
# ============================================================
class CartItemWriteSerializer(serializers.Serializer):
    """POST /api/v1/cart/items — добавить SKU в корзину."""
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemQuantityUpdateSerializer(serializers.Serializer):
    """PATCH /api/v1/cart/items/{sku_id} — изменить количество."""
    quantity = serializers.IntegerField(min_value=1)


# ============================================================
# US-CART-04: баннеры
# ============================================================
class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = (
            "id", "title", "image_url", "target_url",
            "priority", "is_active", "starts_at", "ends_at",
        )


class BannerEventWriteSerializer(serializers.Serializer):
    """POST /api/v1/banner-events — записать клик/показ."""
    banner_id = serializers.UUIDField()
    event_type = serializers.ChoiceField(
        choices=[BannerEvent.EVENT_VIEW, BannerEvent.EVENT_CLICK]
    )


# ============================================================
# US-CART-05: подборки товаров
# ============================================================
from .models import Collection


class CollectionSerializer(serializers.ModelSerializer):
    """Метаданные подборки — без товаров."""

    class Meta:
        model = Collection
        fields = (
            "id", "title", "description", "cover_image_url",
            "target_url", "priority", "is_active", "start_date", "created_at",
        )


# ============================================================
# US-ORD-01: оформление заказа (checkout)
# ============================================================
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id", "sku_id", "product_id", "name",
            "quantity", "unit_price", "line_total",
        )

    def get_name(self, obj):
        if obj.sku_name:
            return f"{obj.product_title} — {obj.sku_name}"
        return obj.product_title


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    items_count = serializers.SerializerMethodField()
    buyer_id = serializers.UUIDField(source="user_id", read_only=True)
    subtotal = serializers.IntegerField(source="total_amount", read_only=True)
    total = serializers.IntegerField(source="total_amount", read_only=True)
    address = serializers.CharField(source="delivery_address", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "buyer_id", "status", "items", "items_count",
            "subtotal", "total", "address", "created_at", "updated_at",
        )

    def get_items_count(self, obj):
        # use prefetched items if available, else count
        if hasattr(obj, "_prefetched_objects_cache") and "items" in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache["items"])
        return obj.items.count()


class OrderListSerializer(serializers.ModelSerializer):
    """Краткое представление заказа для списка — без позиций."""
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "status", "items_count",
            "total_amount", "created_at", "updated_at",
        )

    def get_items_count(self, obj):
        if hasattr(obj, "_prefetched_objects_cache") and "items" in obj._prefetched_objects_cache:
            return len(obj._prefetched_objects_cache["items"])
        return obj.items.count()


class CheckoutItemSerializer(serializers.Serializer):
    """Одна позиция в запросе POST /api/v1/orders."""
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CheckoutRequestSerializer(serializers.Serializer):
    """Тело запроса POST /api/v1/orders."""
    address_id = serializers.UUIDField()
    payment_method_id = serializers.UUIDField()
    items = serializers.ListField(
        child=CheckoutItemSerializer(),
        min_length=1,
        required=False,
        allow_null=True,
        default=None,
    )
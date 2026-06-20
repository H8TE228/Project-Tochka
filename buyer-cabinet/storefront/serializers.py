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
    """POST /api/v1/favorites/{product_id}/subscribe — создание подписки на товар."""
    events = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        max_length=10,
    )

    def validate_events(self, value):
        bad = [v for v in value if v not in Subscription.NOTIFY_ON_CHOICES]
        if bad:
            raise serializers.ValidationError(
                f"Unknown event types: {bad}. Allowed: {list(Subscription.NOTIFY_ON_CHOICES)}"
            )
        # уникальные значения, порядок не важен
        return list(dict.fromkeys(value))


class SubscriptionReadSerializer(serializers.ModelSerializer):
    events = serializers.JSONField(source="notify_on")

    class Meta:
        model = Subscription
        fields = ("id", "product_id", "events", "created_at")


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


CART_ITEM_RESPONSE_FIELDS = frozenset({
    "sku_id", "quantity", "is_available", "unavailable_reason",
    "unit_price", "line_total", "available_quantity",
    "name", "image", "product_id",
})

CART_RESPONSE_FIELDS = frozenset({
    "id", "items", "items_count", "subtotal", "is_valid",
})


# ============================================================
# US-CART-04: баннеры
# ============================================================
class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = (
            "id", "title", "image_url", "link",
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
    address = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = (
            "id", "buyer_id", "status", "items", "items_count",
            "subtotal", "total", "address", "created_at", "updated_at",
        )

    def get_address(self, obj):
        return {
            "id": obj.delivery_address,
            "created_at": None,
            "country": None,
            "city": None,
            "street": None,
            "building": None,
        }

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
    """Одна позиция в запросе POST /api/v1/orders.

    Соответствует b2c/openapi.yaml:1261 — required: [sku_id, quantity, unit_price].
    unit_price — цена на момент сборки корзины на клиенте; сервер всё равно
    сверит её с актуальной из B2B перед reserve.
    """
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.IntegerField(min_value=0)


class CheckoutRequestSerializer(serializers.Serializer):
    """Тело запроса POST /api/v1/orders (b2c/openapi.yaml:1243 OrderCreateRequest)."""
    address_id = serializers.UUIDField()
    payment_method_id = serializers.UUIDField()
    # items_snapshot — имя поля по спецификации b2c/openapi.yaml:1250.
    # Опционален: если не передан — позиции берутся из корзины пользователя.
    items_snapshot = serializers.ListField(
        child=CheckoutItemSerializer(),
        min_length=1,
        required=False,
        allow_null=True,
        default=None,
    )


# ============================================================
# US-ORD-04: product events from B2B
# ============================================================
class B2CProductEventSerializer(serializers.Serializer):
    """POST /api/v1/events/product — события B2B → B2C (канон-flow b2c-12-handle-events)."""

    EVENT_PRODUCT_BLOCKED = "PRODUCT_BLOCKED"
    EVENT_PRODUCT_DELETED = "PRODUCT_DELETED"
    EVENT_SKU_OUT_OF_STOCK = "SKU_OUT_OF_STOCK"
    EVENT_OUT_OF_STOCK = "OUT_OF_STOCK"

    ALLOWED_EVENTS = (
        EVENT_PRODUCT_BLOCKED,
        EVENT_PRODUCT_DELETED,
        EVENT_SKU_OUT_OF_STOCK,
        EVENT_OUT_OF_STOCK,
    )

    idempotency_key = serializers.UUIDField()
    event = serializers.ChoiceField(choices=ALLOWED_EVENTS)
    product_id = serializers.UUIDField(required=False, allow_null=True)
    sku_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=False,
    )
    sku_id = serializers.UUIDField(required=False, allow_null=True)
    date = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        event = attrs["event"]
        sku_ids = attrs.get("sku_ids") or []
        sku_id = attrs.get("sku_id")
        product_id = attrs.get("product_id")

        if event in (self.EVENT_PRODUCT_BLOCKED, self.EVENT_PRODUCT_DELETED):
            if not sku_ids and not product_id:
                raise serializers.ValidationError(
                    "sku_ids or product_id is required for this event"
                )
        elif event in (self.EVENT_SKU_OUT_OF_STOCK, self.EVENT_OUT_OF_STOCK):
            if not sku_id and not sku_ids:
                raise serializers.ValidationError(
                    "sku_id is required for out-of-stock events"
                )
        return attrs

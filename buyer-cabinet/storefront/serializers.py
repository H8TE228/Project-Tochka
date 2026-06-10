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
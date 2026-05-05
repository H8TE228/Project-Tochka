from rest_framework import serializers
from .models import (
    Category,
    Product,
    ProductImage,
    ProductCharacteristic,
    SKU,
    SKUImage,
    SKUCharacteristic,
    Invoice,
    InvoiceLine,
    BlockingReason,
)


# ---------- shared mini-serializers ----------

class CategoryRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Category name cannot be empty.")
        qs = Category.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Category with this name already exists.")
        return value


class ImageSerializer(serializers.Serializer):
    """Картинка товара (массив у Product)."""
    url = serializers.CharField(max_length=2000)
    ordering = serializers.IntegerField(default=0)


class CharacteristicValueSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    value = serializers.CharField(max_length=2000)


class BlockingReasonReadSerializer(serializers.ModelSerializer):
    """Канон-flow B2B-5: blocking_reason = {id, title, comment}."""
    comment = serializers.SerializerMethodField()

    class Meta:
        model = BlockingReason
        fields = ("id", "title", "comment")

    def get_comment(self, obj):
        product = self.context.get("product")
        return product.moderator_comment if product else ""


# ---------- SKU ----------

class SKUReadSerializer(serializers.ModelSerializer):
    """Seller cabinet ответ — включает cost_price и reserved_quantity (канон-flow B2B-5)."""
    characteristics = CharacteristicValueSerializer(many=True)

    class Meta:
        model = SKU
        fields = (
            "id", "name", "price", "cost_price", "discount", "image",
            "active_quantity", "reserved_quantity", "characteristics",
        )


class SKUBaseWriteSerializer(serializers.Serializer):
    """Общая база для POST /skus и PUT /skus/{id} (канон-flow B2B-2, B2B-3)."""
    name = serializers.CharField(max_length=255, min_length=1)
    price = serializers.IntegerField(min_value=1)         # > 0 по канону
    cost_price = serializers.IntegerField(min_value=1)    # > 0 по канону
    discount = serializers.IntegerField(min_value=0, default=0)
    image = serializers.CharField(max_length=2000, min_length=1)  # missing_image_returns_400
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)

    def _save_characteristics(self, sku, data):
        SKUCharacteristic.objects.bulk_create([
            SKUCharacteristic(sku=sku, **c) for c in data
        ])

    def update(self, instance, validated_data):
        chars = validated_data.pop("characteristics", None)
        # US-B2B-03: реальные остатки и резервы через PUT не меняются
        validated_data.pop("active_quantity", None)
        validated_data.pop("reserved_quantity", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if chars is not None:
            instance.characteristics.all().delete()
            self._save_characteristics(instance, chars)
        return instance


class SKUWriteSerializer(SKUBaseWriteSerializer):
    """POST /skus — канон-flow B2B-2."""
    product_id = serializers.UUIDField()

    def create(self, validated_data):
        chars = validated_data.pop("characteristics", [])
        product_id = validated_data.pop("product_id")
        sku = SKU.objects.create(product_id=product_id, **validated_data)
        self._save_characteristics(sku, chars)
        return sku


class SKUUpdateSerializer(SKUBaseWriteSerializer):
    """PUT /skus/{id} — без product_id."""
    pass


# ---------- Product ----------

class ProductReadSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer()
    images = ImageSerializer(many=True)
    characteristics = CharacteristicValueSerializer(many=True)
    skus = SKUReadSerializer(many=True)
    blocked = serializers.BooleanField(read_only=True)
    blocking_reason = serializers.SerializerMethodField()
    field_reports = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "title", "description", "status",
            "deleted", "blocked", "category",
            "images", "characteristics", "skus",
            "blocking_reason", "field_reports",
        )

    def get_blocking_reason(self, obj):
        if obj.status == Product.Status.BLOCKED and obj.blocking_reason:
            return BlockingReasonReadSerializer(
                obj.blocking_reason, context={"product": obj}
            ).data
        return None

    def get_field_reports(self, obj):
        if obj.status == Product.Status.BLOCKED:
            return obj.field_reports or []
        return []


class ProductWriteSerializer(serializers.Serializer):
    """POST /products и PUT /products/{id} (канон-flow B2B-1, B2B-3)."""
    title = serializers.CharField(max_length=255, min_length=1)
    description = serializers.CharField(max_length=5000, min_length=1)
    category_id = serializers.UUIDField()
    images = ImageSerializer(many=True, min_length=1)  # missing_images_returns_400
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)
    slug = serializers.SlugField(max_length=255, required=False)

    def validate_category_id(self, value):
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError("Category not found")
        return value

    def _save_images(self, product, images_data):
        ProductImage.objects.bulk_create([
            ProductImage(product=product, **img) for img in images_data
        ])

    def _save_characteristics(self, product, characteristics_data):
        ProductCharacteristic.objects.bulk_create([
            ProductCharacteristic(product=product, **ch) for ch in characteristics_data
        ])

    def create(self, validated_data):
        import uuid as _uuid
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        seller = self.context["seller"]
        category_id = validated_data.pop("category_id")

        # slug опциональный — генерируем уникальный fallback
        if not validated_data.get("slug"):
            validated_data["slug"] = f"p-{_uuid.uuid4().hex[:12]}"

        product = Product.objects.create(
            seller=seller, category_id=category_id, **validated_data
        )
        self._save_images(product, images_data)
        self._save_characteristics(product, characteristics_data)
        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)

        if "category_id" in validated_data:
            instance.category_id = validated_data.pop("category_id")

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if images_data is not None:
            instance.images.all().delete()
            self._save_images(instance, images_data)
        if characteristics_data is not None:
            instance.characteristics.all().delete()
            self._save_characteristics(instance, characteristics_data)
        return instance


# ---------- Invoice (без изменений по логике, оставлено как было) ----------

class InvoiceLineWriteSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_sku_id(self, value):
        if not SKU.objects.filter(id=value).exists():
            raise serializers.ValidationError("SKU not found.")
        return value


class InvoiceWriteSerializer(serializers.Serializer):
    items = InvoiceLineWriteSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value

    def create(self, validated_data):
        items_data = validated_data["items"]
        seller = self.context["seller"]
        invoice = Invoice.objects.create(seller=seller)
        InvoiceLine.objects.bulk_create([
            InvoiceLine(invoice=invoice, sku_id=item["sku_id"], quantity=item["quantity"])
            for item in items_data
        ])
        return invoice


class InvoiceLineReadSerializer(serializers.ModelSerializer):
    sku_id = serializers.UUIDField(source="sku.id")
    sku_name = serializers.CharField(source="sku.name")
    accepted_quantity = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceLine
        fields = ("sku_id", "sku_name", "quantity", "accepted_quantity")

    def get_accepted_quantity(self, obj):
        return None


class InvoiceReadSerializer(serializers.ModelSerializer):
    items = InvoiceLineReadSerializer(many=True, source="lines")
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ("id", "status", "created_at", "items")

    def get_status(self, obj):
        return "PENDING" if obj.accepted_at is None else "ACCEPTED"


class InvoiceAcceptSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()

    def validate_invoice_id(self, value):
        if not Invoice.objects.filter(id=value, accepted_at__isnull=True).exists():
            raise serializers.ValidationError("Invoice not found or already accepted.")
        return value
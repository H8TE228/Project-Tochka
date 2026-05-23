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


class ImageInSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=2000)
    ordering = serializers.IntegerField(default=0)


class ProductImageOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "url", "ordering")


class SKUImageOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ("id", "url", "ordering")


class CharacteristicInSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    value = serializers.CharField(max_length=2000)


class ProductCharacteristicOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCharacteristic
        fields = ("id", "name", "value")


class SKUCharacteristicOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUCharacteristic
        fields = ("id", "name", "value")


class BlockingReasonReadSerializer(serializers.ModelSerializer):
    comment = serializers.SerializerMethodField()

    class Meta:
        model = BlockingReason
        fields = ("id", "title", "comment")

    def get_comment(self, obj):
        product = self.context.get("product")
        return product.moderator_comment if product else ""


class SKUReadSerializer(serializers.ModelSerializer):
    """openapi: SKUResponse (seller view)."""
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    images = SKUImageOutSerializer(many=True, read_only=True)
    characteristics = SKUCharacteristicOutSerializer(many=True, read_only=True)
    stock_quantity = serializers.SerializerMethodField()
    article = serializers.SerializerMethodField()

    class Meta:
        model = SKU
        fields = (
            "id", "product_id", "name",
            "price", "discount", "cost_price",
            "stock_quantity", "active_quantity", "reserved_quantity",
            "article", "image",
            "images", "characteristics",
            "created_at", "updated_at",
        )

    def get_stock_quantity(self, obj):
        return obj.active_quantity + obj.reserved_quantity

    def get_article(self, obj):
        return None


class SKUCatalogSerializer(serializers.ModelSerializer):
    """openapi: SKUPublicResponse (B2C каталог)."""
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    images = SKUImageOutSerializer(many=True, read_only=True)
    characteristics = SKUCharacteristicOutSerializer(many=True, read_only=True)
    stock_quantity = serializers.SerializerMethodField()
    article = serializers.SerializerMethodField()

    class Meta:
        model = SKU
        fields = (
            "id", "product_id", "name",
            "price", "discount",
            "stock_quantity", "active_quantity",
            "article", "image",
            "images", "characteristics",
        )

    def get_stock_quantity(self, obj):
        return obj.active_quantity + obj.reserved_quantity

    def get_article(self, obj):
        return None


class SKUBaseWriteSerializer(serializers.Serializer):
    """База для POST/PATCH SKU. Принимает image (старый формат) или images (массив)."""
    name = serializers.CharField(max_length=255, min_length=1)
    price = serializers.IntegerField(min_value=0)
    cost_price = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    discount = serializers.IntegerField(min_value=0, default=0)
    article = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    image = serializers.CharField(max_length=2000, required=False, allow_null=True, allow_blank=True)
    images = ImageInSerializer(many=True, required=False)

    characteristics = CharacteristicInSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        has_single = bool(attrs.get("image"))
        has_array = bool(attrs.get("images"))
        if not has_single and not has_array:
            raise serializers.ValidationError({
                "image": "At least one image is required (use 'image' string or 'images' array)."
            })
        return attrs

    def _images_to_save(self, attrs):
        images = attrs.get("images") or []
        single = attrs.get("image")
        if single and not images:
            images = [{"url": single, "ordering": 0}]
        return images

    def _save_characteristics(self, sku, data):
        SKUCharacteristic.objects.bulk_create([
            SKUCharacteristic(sku=sku, **c) for c in data
        ])

    def _save_images(self, sku, data):
        SKUImage.objects.bulk_create([
            SKUImage(sku=sku, **img) for img in data
        ])

    def update(self, instance, validated_data):
        chars = validated_data.pop("characteristics", None)
        images_attr = validated_data.pop("images", None)
        single_attr = validated_data.pop("image", None)

        validated_data.pop("active_quantity", None)
        validated_data.pop("reserved_quantity", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)

        if single_attr is not None:
            instance.image = single_attr

        instance.save()

        if chars is not None:
            instance.characteristics.all().delete()
            self._save_characteristics(instance, chars)

        normalized = self._images_to_save({"image": single_attr, "images": images_attr})
        if normalized:
            instance.images.all().delete()
            self._save_images(instance, normalized)

        return instance


class SKUWriteSerializer(SKUBaseWriteSerializer):
    """POST /skus — openapi: SKUCreate."""
    product_id = serializers.UUIDField()

    def create(self, validated_data):
        chars = validated_data.pop("characteristics", [])
        product_id = validated_data.pop("product_id")
        images_attr = validated_data.pop("images", None)
        single_attr = validated_data.pop("image", None)

        if single_attr:
            validated_data["image"] = single_attr
        elif images_attr:
            validated_data["image"] = images_attr[0]["url"]

        validated_data.setdefault("cost_price", 0)

        sku = SKU.objects.create(product_id=product_id, **validated_data)
        self._save_characteristics(sku, chars)
        self._save_images(sku, self._images_to_save({"image": single_attr, "images": images_attr}))
        return sku


class SKUUpdateSerializer(SKUBaseWriteSerializer):
    """PATCH /skus/{id} — openapi: SKUUpdate. Все поля опциональны."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False

    def validate(self, attrs):
        return attrs


class ProductReadSerializer(serializers.ModelSerializer):
    """openapi: ProductResponse — seller view."""
    seller_id = serializers.UUIDField(source="seller.auth_user_id", read_only=True)
    category_id = serializers.UUIDField(source="category.id", read_only=True)
    blocking_reason_id = serializers.SerializerMethodField()

    images = ProductImageOutSerializer(many=True, read_only=True)
    characteristics = ProductCharacteristicOutSerializer(many=True, read_only=True)
    skus = SKUReadSerializer(many=True, read_only=True)

    blocked = serializers.BooleanField(read_only=True)
    blocking_reason = serializers.SerializerMethodField()
    field_reports = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id", "seller_id", "category_id",
            "title", "slug", "description",
            "status", "deleted",
            "blocking_reason_id", "moderator_comment",
            "images", "characteristics", "skus",
            "created_at", "updated_at",
            "blocked", "blocking_reason", "field_reports",
        )

    def get_blocking_reason_id(self, obj):
        return obj.blocking_reason_id

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


class ProductCatalogSerializer(serializers.ModelSerializer):
    """openapi: ProductPublicResponse (B2C каталог, без cost_price у SKU)."""
    seller_id = serializers.UUIDField(source="seller.auth_user_id", read_only=True)
    category_id = serializers.UUIDField(source="category.id", read_only=True)
    name = serializers.CharField(source="title", read_only=True)
    images = ProductImageOutSerializer(many=True, read_only=True)
    characteristics = ProductCharacteristicOutSerializer(many=True, read_only=True)
    skus = SKUCatalogSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = (
            "id", "seller_id", "category_id",
            "name", "slug", "description",
            "status",
            "images", "characteristics", "skus",
            "created_at", "updated_at",
        )


class ReserveItemSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ReserveCommandSerializer(serializers.Serializer):
    items = ReserveItemSerializer(many=True, min_length=1)
    idempotency_key = serializers.UUIDField()


class FulfillCommandSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ModerationEventSerializer(serializers.Serializer):
    class Status(serializers.ChoiceField):
        def __init__(self, **kwargs):
            super().__init__(choices=["MODERATED", "BLOCKED"], **kwargs)

    sku_id = serializers.UUIDField()
    status = Status()
    hard_block = serializers.BooleanField()
    field_reports = serializers.JSONField(required=False, allow_null=True)
    blocking_reason = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    idempotency_key = serializers.UUIDField()


class ProductWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255, min_length=1)
    description = serializers.CharField(max_length=5000, min_length=1)
    category_id = serializers.UUIDField()
    images = ImageInSerializer(many=True, min_length=1)
    characteristics = CharacteristicInSerializer(many=True, required=False, default=list)
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
        if not validated_data.get("slug"):
            validated_data["slug"] = f"p-{_uuid.uuid4().hex[:12]}"
        product = Product.objects.create(seller=seller, category_id=category_id, **validated_data)
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

    class Meta:
        model = InvoiceLine
        fields = ("id", "sku_id", "sku_name", "quantity", "accepted_quantity")


class InvoiceReadSerializer(serializers.ModelSerializer):
    items = InvoiceLineReadSerializer(many=True, source="lines")
    seller_id = serializers.UUIDField(source="seller.auth_user_id")

    class Meta:
        model = Invoice
        fields = ("id", "seller_id", "status", "created_at", "updated_at", "items")


class InvoiceAcceptLineSerializer(serializers.Serializer):
    line_id = serializers.UUIDField()
    accepted_quantity = serializers.IntegerField(min_value=0)


class InvoiceAcceptSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    items = InvoiceAcceptLineSerializer(many=True, min_length=1)

    def validate_invoice_id(self, value):
        if not Invoice.objects.filter(id=value, status=Invoice.Status.CREATED).exists():
            raise serializers.ValidationError("Invoice not found or already processed.")
        return value
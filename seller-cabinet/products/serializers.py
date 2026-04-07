from rest_framework import serializers
from .models import (
    Category, Seller, Product, ProductImage, ProductCharacteristic,
    SKU, SKUImage, SKUCharacteristic,
    Invoice, InvoiceLine, CategorySerializer,
)

# ---------------------------------------------------------------------------
# Shared field serializers (match spec schema names)
# ---------------------------------------------------------------------------

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
    url = serializers.CharField(max_length=2000)
    ordering = serializers.IntegerField(default=0)


class CharacteristicValueSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    value = serializers.CharField(max_length=2000)


# ---------------------------------------------------------------------------
# SKU read serializer (used inside Product response)
# ---------------------------------------------------------------------------

class SKUImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ("url", "ordering")


class SKUReadSerializer(serializers.ModelSerializer):
    activeQuantity = serializers.IntegerField(source="active_quantity")
    characteristics = CharacteristicValueSerializer(many=True)
    images = SKUImageSerializer(many=True)

    class Meta:
        model = SKU
        fields = ("id", "name", "price_cents", "activeQuantity", "is_enabled", "characteristics", "images")


# ---------------------------------------------------------------------------
# Product read serializer (GET /api/v1/products/{id})
# ---------------------------------------------------------------------------

class ProductReadSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer()
    images = ImageSerializer(many=True)
    characteristics = CharacteristicValueSerializer(many=True)
    skus = SKUReadSerializer(many=True)

    class Meta:
        model = Product
        fields = ("id", "title", "slug", "description", "status", "category", "images", "characteristics", "skus")


# ---------------------------------------------------------------------------
# Product write serializer (POST / PUT /api/v1/products)
# ---------------------------------------------------------------------------

class ProductWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500)
    slug = serializers.SlugField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    category_id = serializers.UUIDField()
    images = ImageSerializer(many=True, required=False, default=list)
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)

    def validate_category_id(self, value):
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError("Category not found.")
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
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        seller = self.context["seller"]

        product = Product.objects.create(seller=seller, **validated_data)
        self._save_images(product, images_data)
        self._save_characteristics(product, characteristics_data)
        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)

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


# ---------------------------------------------------------------------------
# SKU write serializer (POST /api/v1/skus)
# ---------------------------------------------------------------------------

class SKUWriteSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    name = serializers.CharField(max_length=500)
    price_cents = serializers.IntegerField(min_value=0)
    active_quantity = serializers.IntegerField(min_value=0, default=0)
    is_enabled = serializers.BooleanField(default=True)
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)
    images = ImageSerializer(many=True, required=False, default=list)

    def validate_product_id(self, value):
        seller = self.context.get("seller")
        qs = Product.objects.filter(id=value)
        if not qs.exists():
            raise serializers.ValidationError("Product not found.")
        if seller and not qs.filter(seller=seller).exists():
            raise serializers.ValidationError("You do not own this product.")
        return value

    def create(self, validated_data):
        characteristics_data = validated_data.pop("characteristics", [])
        images_data = validated_data.pop("images", [])
        sku = SKU.objects.create(**validated_data)
        SKUCharacteristic.objects.bulk_create([
            SKUCharacteristic(sku=sku, **ch) for ch in characteristics_data
        ])
        SKUImage.objects.bulk_create([
            SKUImage(sku=sku, **img) for img in images_data
        ])
        return sku


# ---------------------------------------------------------------------------
# Invoice serializers (POST /api/v1/invoices, POST /api/v1/invoices/accept)
# ---------------------------------------------------------------------------

class InvoiceLineWriteSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)

    def validate_sku_id(self, value):
        if not SKU.objects.filter(id=value).exists():
            raise serializers.ValidationError("SKU not found.")
        return value


class InvoiceWriteSerializer(serializers.Serializer):
    lines = InvoiceLineWriteSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Invoice must have at least one line.")
        return value

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        seller = self.context["seller"]
        invoice = Invoice.objects.create(seller=seller)
        InvoiceLine.objects.bulk_create([
            InvoiceLine(invoice=invoice, sku_id=line["sku_id"], quantity=line["quantity"])
            for line in lines_data
        ])
        return invoice


class InvoiceLineReadSerializer(serializers.ModelSerializer):
    sku_id = serializers.UUIDField(source="sku.id")
    sku_name = serializers.CharField(source="sku.name")

    class Meta:
        model = InvoiceLine
        fields = ("id", "sku_id", "sku_name", "quantity")


class InvoiceReadSerializer(serializers.ModelSerializer):
    lines = InvoiceLineReadSerializer(many=True)

    class Meta:
        model = Invoice
        fields = ("id", "created_at", "accepted_at", "lines")


class InvoiceAcceptSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()

    def validate_invoice_id(self, value):
        if not Invoice.objects.filter(id=value, accepted_at__isnull=True).exists():
            raise serializers.ValidationError("Invoice not found or already accepted.")
        return value


# ---------------------------------------------------------------------------
# Shared field serializers (match spec schema names)
# ---------------------------------------------------------------------------

class CategoryRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "name")


class ImageSerializer(serializers.Serializer):
    url = serializers.CharField(max_length=512)
    ordering = serializers.IntegerField(default=0)


class CharacteristicValueSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=256)
    value = serializers.CharField(max_length=256)


# ---------------------------------------------------------------------------
# SKU read serializer (used inside Product response)
# ---------------------------------------------------------------------------

class SKUReadSerializer(serializers.ModelSerializer):
    # Spec uses camelCase "activeQuantity"
    activeQuantity = serializers.IntegerField(source="active_quantity")
    characteristics = CharacteristicValueSerializer(many=True)

    class Meta:
        model = SKU
        fields = ("id", "name", "price", "activeQuantity", "characteristics")


# ---------------------------------------------------------------------------
# Product read serializer (GET /api/v1/products/{id})
# ---------------------------------------------------------------------------

class ProductReadSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer()
    images = ImageSerializer(many=True)
    characteristics = CharacteristicValueSerializer(many=True)
    skus = SKUReadSerializer(many=True)

    class Meta:
        model = Product
        fields = ("id", "title", "description", "status", "category", "images", "characteristics", "skus")


# ---------------------------------------------------------------------------
# Product write serializer (POST / PUT /api/v1/products)
# ---------------------------------------------------------------------------

class ProductWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=512)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    category_id = serializers.IntegerField()
    images = ImageSerializer(many=True, required=False, default=list)
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)

    def validate_category_id(self, value):
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError("Category not found.")
        return value

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        seller_id = self.context["seller_id"]

        product = Product.objects.create(seller_id=seller_id, **validated_data)
        Image.objects.bulk_create([
            Image(product=product, **img) for img in images_data
        ])
        ProductCharacteristic.objects.bulk_create([
            ProductCharacteristic(product=product, **ch) for ch in characteristics_data
        ])
        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if images_data is not None:
            instance.images.all().delete()
            Image.objects.bulk_create([
                Image(product=instance, **img) for img in images_data
            ])

        if characteristics_data is not None:
            instance.characteristics.all().delete()
            ProductCharacteristic.objects.bulk_create([
                ProductCharacteristic(product=instance, **ch) for ch in characteristics_data
            ])

        return instance


# ---------------------------------------------------------------------------
# SKU write serializer (POST /api/v1/skus)
# ---------------------------------------------------------------------------

class SKUWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField(max_length=256)
    price = serializers.IntegerField(min_value=0)
    active_quantity = serializers.IntegerField(min_value=0, default=0)
    characteristics = CharacteristicValueSerializer(many=True, required=False, default=list)

    def validate_product_id(self, value):
        seller_id = self.context.get("seller_id")
        qs = Product.objects.filter(id=value)
        if not qs.exists():
            raise serializers.ValidationError("Product not found.")
        if seller_id and not qs.filter(seller_id=seller_id).exists():
            raise serializers.ValidationError("You do not own this product.")
        return value

    def create(self, validated_data):
        characteristics_data = validated_data.pop("characteristics", [])
        sku = SKU.objects.create(**validated_data)
        SKUCharacteristic.objects.bulk_create([
            SKUCharacteristic(sku=sku, **ch) for ch in characteristics_data
        ])
        return sku
# ---------------------------------------------------------------------------
# (PUT /api/v1/skus/<uuid>)
# ---------------------------------------------------------------------------
class SKUBaseWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=500)
    price_cents = serializers.IntegerField(min_value=0)
    active_quantity = serializers.IntegerField(min_value=0)
    is_enabled = serializers.BooleanField()
    characteristics = CharacteristicValueSerializer(many=True, required=False)
    images = ImageSerializer(many=True, required=False)

    def _save_characteristics(self, sku, data):
        SKUCharacteristic.objects.bulk_create([
            SKUCharacteristic(sku=sku, **ch) for ch in data
        ])

    def _save_images(self, sku, data):
        SKUImage.objects.bulk_create([
            SKUImage(sku=sku, **img) for img in data
        ])

        def update(self, instance, validated_data):
        characteristics_data = validated_data.pop("characteristics", None)
        images_data = validated_data.pop("images", None)

        # обновляем простые поля
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # характеристики
        if characteristics_data is not None:
            instance.characteristics.all().delete()
            self._save_characteristics(instance, characteristics_data)

        # изображения
        if images_data is not None:
            instance.images.all().delete()
            self._save_images(instance, images_data)

        return instance
    
class SKUUpdateSerializer(SKUBaseWriteSerializer):
    pass

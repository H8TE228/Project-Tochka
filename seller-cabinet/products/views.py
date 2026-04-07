import uuid
from datetime import timezone

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from seller_cabinet.permissions import IsSeller
from .models import Product, SKU, Seller, Invoice, Category
from .serializers import (
    ProductReadSerializer,
    ProductWriteSerializer,
    SKUWriteSerializer,
    SKUReadSerializer,
    InvoiceWriteSerializer,
    InvoiceReadSerializer,
    InvoiceAcceptSerializer,
    SKUUpdateSerializer,
)


def get_or_create_seller(user) -> Seller:
    """Resolve Seller from JWT user. Creates a stub record on first access."""
    auth_uuid = uuid.UUID(str(user.id)) if not isinstance(user.id, uuid.UUID) else user.id
    seller, _ = Seller.objects.get_or_create(
        auth_user_id=auth_uuid,
        defaults={"name": getattr(user, "email", str(auth_uuid))},
    )
    return seller


class ProductCreateView(APIView):
    """POST /api/v1/products — create a new product."""

    permission_classes = [IsSeller]

    def post(self, request):
        seller = get_or_create_seller(request.user)
        serializer = ProductWriteSerializer(
            data=request.data,
            context={"seller": seller},
        )
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(
            ProductReadSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )
    def get(self, request):
        seller = get_or_create_seller(request.user)
        products = Product.objects.filter(seller=seller).select_related("category").prefetch_related(
            "images",
            "characteristics",
            "skus__characteristics",
            "skus__images",
            )
        return Response(ProductReadSerializer(products, many=True).data)


class ProductDetailView(APIView):
    """
    GET  /api/v1/products/{id} — get product with all SKUs.
    PUT  /api/v1/products/{id} — update product (owner only).
    """

    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsSeller()]
        return []

    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        return Response(ProductReadSerializer(product).data)

    def put(self, request, product_id):
        seller = get_or_create_seller(request.user)
        product = get_object_or_404(Product, pk=product_id, seller=seller)
        serializer = ProductWriteSerializer(
            product,
            data=request.data,
            context={"seller": seller},
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(ProductReadSerializer(updated).data)


class SKUCreateView(APIView):
    """POST /api/v1/skus — create a new SKU for an existing product."""

    permission_classes = [IsSeller]

    def post(self, request):
        seller = get_or_create_seller(request.user)
        serializer = SKUWriteSerializer(
            data=request.data,
            context={"seller": seller},
        )
        serializer.is_valid(raise_exception=True)
        sku = serializer.save()
        return Response(
            SKUReadSerializer(sku).data,
            status=status.HTTP_201_CREATED,
        )


class InvoiceCreateView(APIView):
    """POST /api/v1/invoices — create an invoice (seller submits stock arrival)."""

    permission_classes = [IsSeller]

    def post(self, request):
        seller = get_or_create_seller(request.user)
        serializer = InvoiceWriteSerializer(
            data=request.data,
            context={"seller": seller},
        )
        serializer.is_valid(raise_exception=True)
        invoice = serializer.save()
        return Response(
            InvoiceReadSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )


class InvoiceAcceptView(APIView):
    """POST /api/v1/invoices/accept — accept invoice and update SKU quantities."""

    permission_classes = [IsSeller]

    def post(self, request):
        serializer = InvoiceAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invoice = get_object_or_404(
            Invoice, pk=serializer.validated_data["invoice_id"], accepted_at__isnull=True
        )

        # Update active_quantity for each SKU in the invoice
        for line in invoice.lines.select_related("sku"):
            line.sku.active_quantity += line.quantity
            line.sku.save(update_fields=["active_quantity"])

        from django.utils import timezone as tz
        invoice.accepted_at = tz.now()
        invoice.save(update_fields=["accepted_at"])

        return Response(InvoiceReadSerializer(invoice).data)

class SKUDetailView(APIView):
    permission_classes = [IsSeller]

    def put(self, request, sku_id):
        seller = get_or_create_seller(request.user)

        sku = get_object_or_404(
            SKU.objects.select_related("product"),
            pk=sku_id,
            product__seller=seller
        )

        serializer = SKUUpdateSerializer(sku, data=request.data)
        serializer.is_valid(raise_exception=True)
        sku = serializer.save()

        return Response(SKUReadSerializer(sku).data, status=200)
    
class CategoryListCreateView(APIView):
    """
    GET  /api/v1/categories — list categories
    POST /api/v1/categories — create category
    """

    permission_classes = [IsSeller]

    def get(self, request):
        categories = Category.objects.all().order_by("name")
        return Response(CategorySerializer(categories, many=True).data)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)

class CategoryDetailView(APIView):
    """
    GET    /api/v1/categories/{id} — get category
    PUT    /api/v1/categories/{id} — update category
    DELETE /api/v1/categories/{id} — delete category
    """

    permission_classes = [IsSeller]

    def get(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        return Response(CategorySerializer(category).data)

    def put(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        serializer = CategorySerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(CategorySerializer(updated).data)

    def delete(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)

        if Product.objects.filter(category=category).exists():
            return Response(
                {"detail": "Cannot delete category that is used by products."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
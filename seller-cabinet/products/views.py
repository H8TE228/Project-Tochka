import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.db.models import Count, IntegerField, Min, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from seller_cabinet.exceptions import AlreadyDeleted, HardBlockedForbidden, NotOwner
from seller_cabinet.authentication import (
    JWTAuthentication,
    PublicCatalogAuthentication,
    RequireServiceKeyAuthentication,
)
from seller_cabinet.permissions import IsSeller, IsServiceAuthenticated

from .models import (
    Product,
    SKU,
    Seller,
    Invoice,
    Category,
    BlockingReason,
    InventoryReservation,
    ProcessedRequest,
    ProcessedModerationEvent,
)
from .serializers import (
    ProductReadSerializer,
    ProductIdsBatchSerializer,
    product_public_paginated_response,
    ProductSellerListSerializer,
    ProductWriteSerializer,
    SKUWriteSerializer,
    SKUUpdateSerializer,
    SKUReadSerializer,
    ReserveRequestSerializer,
    UnreserveRequestSerializer,
    InventoryOrderRequestSerializer,
    ModerationEventSerializer,
    InvoiceWriteSerializer,
    InvoiceReadSerializer,
    InvoiceAcceptSerializer,
    CategorySerializer,
)
from .services import (
    transition_on_first_sku,
    transition_on_edit,
    publish_to_moderation,
    publish_product_deleted_to_b2c,
    publish_sku_out_of_stock_to_b2c,
    publish_product_blocked_to_b2c,
)


def _auth_uuid_from_user(user) -> uuid.UUID:
    """user_id из JWT → UUID для Seller.auth_user_id."""
    raw_id = user.id
    if isinstance(raw_id, uuid.UUID):
        return raw_id
    if isinstance(raw_id, int):
        return uuid.UUID(int=raw_id)
    return uuid.UUID(str(raw_id))


def get_or_create_seller(user) -> Seller:
    """Resolve Seller from JWT user. Поддерживает int (BigAutoField auth) и UUID (тесты)."""
    auth_uuid = _auth_uuid_from_user(user)
    seller, _ = Seller.objects.get_or_create(
        auth_user_id=auth_uuid,
        defaults={"name": getattr(user, "email", str(auth_uuid))},
    )
    return seller


def resolve_seller_for_jwt(user) -> Seller:
    """
    Продавец из JWT: при наличии seller_id в claims — только если Seller.id совпадает
    и привязан к тому же auth_user_id (защита от подмены).
    """
    auth_uuid = _auth_uuid_from_user(user)
    claim_sid = getattr(user, "seller_id", None)
    if claim_sid is not None:
        sid = claim_sid if isinstance(claim_sid, uuid.UUID) else uuid.UUID(str(claim_sid))
        return get_object_or_404(Seller, id=sid, auth_user_id=auth_uuid)
    seller, _ = Seller.objects.get_or_create(
        auth_user_id=auth_uuid,
        defaults={"name": getattr(user, "email", str(auth_uuid))},
    )
    return seller


def _parse_list_limit_offset(request) -> tuple[int, int]:
    try:
        limit = int(request.query_params.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    try:
        offset = int(request.query_params.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return limit, offset


def _parse_include_deleted(request) -> bool | None:
    raw = request.query_params.get("include_deleted")
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in ("true", "1"):
        return True
    if normalized in ("false", "0"):
        return False
    return None


def _apply_seller_list_status_filter(qs, status_raw: str):
    """Фильтр ?status= по ProductStatus enum."""
    s = (status_raw or "").strip().upper()
    if not s:
        return qs
    valid_statuses = {choice.value for choice in Product.Status}
    if s not in valid_statuses:
        return None
    return qs.filter(status=s)


def _filter_products_by_title_search(qs, search: str):
    """Подстрока в title без учёта регистра (в т.ч. кириллица на SQLite)."""
    needle = search.casefold()
    matching_ids = [
        p.pk for p in qs.only("pk", "title") if needle in p.title.casefold()
    ]
    return qs.filter(pk__in=matching_ids)


def _parse_catalog_page_size(request) -> tuple[int, int]:
    try:
        page = int(request.query_params.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        size = int(request.query_params.get("size", 20))
    except (TypeError, ValueError):
        size = 20
    page = max(1, page)
    size = max(1, min(size, 100))
    return page, size


_CATALOG_SORT_FIELDS = {
    "created_at": "created_at",
    "-created_at": "-created_at",
    "price": "min_price",
    "-price": "-min_price",
    "title": "title",
    "-title": "-title",
}


def _parse_catalog_sort(request) -> str:
    sort = (request.query_params.get("sort") or "").strip()
    return _CATALOG_SORT_FIELDS.get(sort, "-created_at")


def _public_catalog_queryset(request):
    """Видимые в B2C товары; seller/images/characteristics/skus — одним запросом."""
    visible_skus = SKU.objects.filter(
        active_quantity__gt=0,
    ).prefetch_related("images", "characteristics")
    qs = (
        Product.objects.filter(
            deleted=False,
            status=Product.Status.MODERATED,
            skus__active_quantity__gt=0,
        )
        .exclude(status=Product.Status.HARD_BLOCKED)
        .select_related("seller", "category")
        .prefetch_related(
            "images",
            "characteristics",
            Prefetch("skus", queryset=visible_skus),
        )
        .distinct()
    )

    category_id = request.query_params.get("category_id")
    if category_id:
        qs = qs.filter(category_id=category_id)

    sort_field = _parse_catalog_sort(request)
    if "min_price" in sort_field:
        qs = qs.annotate(
            min_price=Min("skus__price", filter=Q(skus__active_quantity__gt=0))
        )

    return qs.order_by(sort_field)


def _public_catalog_response(request, queryset) -> Response:
    page, size = _parse_catalog_page_size(request)
    total_count = queryset.count()
    offset = (page - 1) * size
    items = list(queryset[offset : offset + size])
    return Response(
        product_public_paginated_response(
            items, total_count=total_count, offset=offset, limit=size
        )
    )


def _seller_product_list_response(request, seller: Seller) -> Response:
    """GET /api/v1/products — список товаров продавца (openapi ProductPaginatedResponse)."""
    include_deleted = _parse_include_deleted(request)
    if include_deleted is None:
        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": "include_deleted must be true or false",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = Product.objects.filter(seller=seller)
    if not include_deleted:
        qs = qs.filter(deleted=False)

    qs = qs.annotate(
        skus_count=Count("skus", filter=Q(skus__deleted=False), distinct=True),
        total_active_quantity=Coalesce(
            Sum("skus__active_quantity", filter=Q(skus__deleted=False)),
            Value(0),
            output_field=IntegerField(),
        ),
    ).order_by("-created_at")

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = _filter_products_by_title_search(qs, search)

    status_raw = request.query_params.get("status", "")
    filtered = _apply_seller_list_status_filter(qs, status_raw)
    if filtered is None and status_raw.strip():
        valid_statuses = ", ".join(choice.value for choice in Product.Status)
        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": f"status must be one of: {valid_statuses}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if filtered is not None:
        qs = filtered

    total_count = qs.count()
    limit, offset = _parse_list_limit_offset(request)
    page = qs[offset : offset + limit]

    return Response(
        {
            "items": ProductSellerListSerializer(page, many=True).data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    )


# ---------- Products ----------

class PublicProductCatalogView(APIView):
    """
    GET/POST /api/v1/public/products — B2C-каталог (US-B2B-07).
    POST с product_ids в теле — выборка по id товара.
    """

    authentication_classes = [PublicCatalogAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def get(self, request):
        return _public_catalog_response(request, _public_catalog_queryset(request))

    def post(self, request):
        serializer = ProductIdsBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queryset = _public_catalog_queryset(request)
        product_ids = serializer.validated_data.get("product_ids") or []
        if product_ids:
            queryset = queryset.filter(id__in=product_ids)
        return _public_catalog_response(request, queryset)


class ProductsView(APIView):
    """GET — seller list (JWT); POST — create product (JWT) или batch catalog (X-Service-Key)."""

    def get_authenticators(self):
        if self.request.method == "GET":
            return [JWTAuthentication()]
        if self.request.method == "POST" and self.request.headers.get("X-Service-Key"):
            return [PublicCatalogAuthentication()]
        return [JWTAuthentication()]

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsSeller()]
        if self.request.method == "POST" and self.request.headers.get("X-Service-Key"):
            return [IsServiceAuthenticated()]
        return [IsSeller()]

    def get(self, request):
        seller = resolve_seller_for_jwt(request.user)
        return _seller_product_list_response(request, seller)

    def post(self, request):
        if request.headers.get("X-Service-Key"):
            return PublicProductCatalogView.post(self, request)
        seller = get_or_create_seller(request.user)
        serializer = ProductWriteSerializer(data=request.data, context={"seller": seller})
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductReadSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    """GET/PUT /api/v1/products/{id} — US-B2B-03 (канон-flow B2B-3, B2B-5)."""

    def get_permissions(self):
        if self.request.method in ("PUT", "DELETE"):
            return [IsSeller()]
        return [IsSeller()]  # GET тоже требует JWT в seller cabinet

    def get(self, request, product_id):
        # Канон-flow B2B-5: чужой товар → 404 (не раскрываем)
        seller = get_or_create_seller(request.user)
        product = get_object_or_404(
            Product.objects.filter(deleted=False)
            .select_related("category", "blocking_reason")
            .prefetch_related(
                "images",
                "characteristics",
                Prefetch(
                    "skus",
                    queryset=SKU.objects.filter(deleted=False).prefetch_related(
                        "characteristics"
                    ),
                ),
            ),
            pk=product_id,
        )
        if product.seller_id != seller.id:
            raise Http404()
        return Response(ProductReadSerializer(product).data)

    def delete(self, request, product_id):
        seller = get_or_create_seller(request.user)
        product = get_object_or_404(Product, pk=product_id)

        if product.seller_id != seller.id:
            raise NotOwner(detail={
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            })

        if product.deleted:
            raise AlreadyDeleted(detail={
                "code": "INVALID_REQUEST",
                "message": "Product already deleted",
            })

        if product.status == Product.Status.HARD_BLOCKED:
            raise HardBlockedForbidden(detail={
                "code": "FORBIDDEN",
                "message": "Cannot delete hard-blocked product",
            })

        with transaction.atomic():
            sku_ids = list(product.skus.values_list("id", flat=True))
            product.deleted = True
            product.save(update_fields=["deleted", "updated_at"])
            publish_to_moderation("DELETED", product)
            publish_product_deleted_to_b2c(product, sku_ids)

        return Response({"ok": True})

    def put(self, request, product_id):
        seller = get_or_create_seller(request.user)
        # 404 если товар не существует или удалён
        product = get_object_or_404(Product, pk=product_id, deleted=False)

        # 403 NOT_OWNER если чужой (DoD US-B2B-03: edit_others_product_returns_403)
        if product.seller_id != seller.id:
            raise NotOwner(detail={
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            })

        # 403 FORBIDDEN если HARD_BLOCKED
        if product.status == Product.Status.HARD_BLOCKED:
            raise HardBlockedForbidden(detail={
                "code": "FORBIDDEN",
                "message": "Cannot edit hard-blocked product",
            })

        serializer = ProductWriteSerializer(
            product, data=request.data, context={"seller": seller}
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            updated = serializer.save()
            transition_on_edit(updated)

        return Response(ProductReadSerializer(updated).data)


# ---------- SKU ----------

class SKUCreateView(APIView):
    """POST /api/v1/skus — US-B2B-02 (канон-flow B2B-2)."""
    permission_classes = [IsSeller]

    def post(self, request):
        seller = get_or_create_seller(request.user)

        # Сначала валидация полей (image обязательный → missing_image_returns_400)
        serializer = SKUWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 404 если товар не найден (канон B2B-2)
        product = get_object_or_404(Product, pk=serializer.validated_data["product_id"])

        # 403 NOT_OWNER если чужой (IDOR)
        if product.seller_id != seller.id:
            raise NotOwner(detail={
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            })

        # 403 если HARD_BLOCKED (DoD US-B2B-02: add_sku_to_hard_blocked_returns_403)
        if product.status == Product.Status.HARD_BLOCKED:
            raise HardBlockedForbidden(detail={
                "code": "FORBIDDEN",
                "message": "Cannot add SKU to hard-blocked product",
            })

        with transaction.atomic():
            is_first_sku = not product.skus.filter(deleted=False).exists()
            sku = serializer.save()
            if is_first_sku:
                transition_on_first_sku(product)

        return Response(SKUReadSerializer(sku).data, status=status.HTTP_201_CREATED)


class SKUDetailView(APIView):
    """PUT/DELETE /api/v1/skus/{id} — US-B2B-03; soft delete SKU."""
    permission_classes = [IsSeller]

    def put(self, request, sku_id):
        seller = get_or_create_seller(request.user)
        sku = get_object_or_404(
            SKU.objects.select_related("product"),
            pk=sku_id,
            deleted=False,
            product__deleted=False,
        )

        if sku.product.seller_id != seller.id:
            raise NotOwner(detail={
                "code": "NOT_OWNER",
                "message": "SKU does not belong to the authenticated seller",
            })

        if sku.product.status == Product.Status.HARD_BLOCKED:
            raise HardBlockedForbidden(detail={
                "code": "FORBIDDEN",
                "message": "Cannot edit SKU of hard-blocked product",
            })

        serializer = SKUUpdateSerializer(sku, data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            sku = serializer.save()
            transition_on_edit(sku.product)

        return Response(SKUReadSerializer(sku).data)

    def delete(self, request, sku_id):
        seller = get_or_create_seller(request.user)
        sku = (
            SKU.objects.filter(pk=sku_id, deleted=False, product__deleted=False)
            .select_related("product")
            .first()
        )
        if sku is None:
            return Response(
                {"code": "NOT_FOUND", "message": "SKU not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if sku.product.seller_id != seller.id:
            raise NotOwner(detail={
                "code": "NOT_OWNER",
                "message": "SKU does not belong to the authenticated seller",
            })

        if sku.product.status == Product.Status.HARD_BLOCKED:
            return Response(
                {"code": "FORBIDDEN", "message": "Cannot delete SKU of HARD_BLOCKED product"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if sku.reserved_quantity != 0:
            return Response(
                {
                    "code": "CONFLICT",
                    "message": "Cannot delete SKU with active reserves",
                },
                status=status.HTTP_409_CONFLICT,
            )

        product = sku.product
        prior_status = product.status
        had_active = sku.active_quantity > 0

        with transaction.atomic():
            sku.deleted = True
            sku.save(update_fields=["deleted", "updated_at"])
            product.save(update_fields=["updated_at"])

            remaining = product.skus.filter(deleted=False).exists()
            if not remaining and prior_status == Product.Status.ON_MODERATION:
                product.status = Product.Status.CREATED
                product.save(update_fields=["status", "updated_at"])
                publish_to_moderation("DELETED", product)
            if had_active and prior_status == Product.Status.MODERATED:
                publish_sku_out_of_stock_to_b2c(sku)

        return Response(status=status.HTTP_204_NO_CONTENT)

class InvoiceCreateView(APIView):
    permission_classes = [IsSeller]

    def post(self, request):
        seller = get_or_create_seller(request.user)
        serializer = InvoiceWriteSerializer(data=request.data, context={"seller": seller})
        serializer.is_valid(raise_exception=True)

        # Business validation: ownership + MODERATED status (канон B2B-6)
        for item in serializer.validated_data["items"]:
            sku = SKU.objects.select_related("product").get(id=item["sku_id"])
            if sku.product.seller_id != seller.id:
                raise NotOwner(detail={
                    "code": "NOT_OWNER",
                    "message": "One or more SKUs do not belong to the authenticated seller",
                })
            if sku.product.status != Product.Status.MODERATED:
                return Response(
                    {"code": "INVALID_REQUEST", "message": "Invoice can only be created for MODERATED products"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        invoice = serializer.save()
        return Response(InvoiceReadSerializer(invoice).data, status=status.HTTP_201_CREATED)


class InvoiceAcceptView(APIView):
    permission_classes = [IsSeller]

    def post(self, request):
        serializer = InvoiceAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invoice = get_object_or_404(
            Invoice, pk=serializer.validated_data["invoice_id"], accepted_at__isnull=True
        )

        for line in invoice.lines.select_related("sku"):
            line.sku.active_quantity += line.quantity
            line.sku.save(update_fields=["active_quantity"])

        from django.utils import timezone as tz
        invoice.accepted_at = tz.now()
        invoice.save(update_fields=["accepted_at"])

        return Response(InvoiceReadSerializer(invoice).data)


# ---------- Categories ----------

class CategoryListCreateView(APIView):
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
    permission_classes = [IsSeller]

    def get(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        return Response(CategorySerializer(category).data)

    def put(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        serializer = CategorySerializer(category, data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(CategorySerializer(serializer.save()).data)

    def delete(self, request, category_id):
        category = get_object_or_404(Category, pk=category_id)
        if Product.objects.filter(category=category).exists():
            return Response(
                {"code": "INVALID_REQUEST", "message": "Cannot delete category that is used by products."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


RESERVE_IDEMPOTENCY_TTL = timedelta(hours=1)


def _reserve_response(order_id, reserved_at) -> dict:
    """openapi: ReserveResponse."""
    return {
        "order_id": str(order_id),
        "status": "RESERVED",
        "reserved_at": reserved_at,
    }


def _inventory_order_response(order_id, processed_at, *, status_value: str) -> dict:
    """openapi: InventoryOrderResponse."""
    return {
        "order_id": str(order_id),
        "status": status_value,
        "processed_at": processed_at.isoformat(),
    }


class ReserveView(APIView):
    """POST /api/v1/inventory/reserve — резерв; идемпотентность по idempotency_key (TTL 1 ч)."""

    authentication_classes = [RequireServiceKeyAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def post(self, request):
        serializer = ReserveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        idempotency_key = serializer.validated_data["idempotency_key"]
        items = serializer.validated_data["items"]

        existing = ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.RESERVE,
            idempotency_key=idempotency_key,
        ).first()
        if existing:
            if existing.created_at >= timezone.now() - RESERVE_IDEMPOTENCY_TTL:
                return Response(
                    _reserve_response(order_id, existing.created_at),
                    status=status.HTTP_200_OK,
                )
            existing.delete()

        with transaction.atomic():
            sku_ids = [item["sku_id"] for item in items]
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_related("product").select_for_update().filter(
                    id__in=sku_ids
                )
            }
            if len(skus) != len(sku_ids):
                return Response(
                    {"code": "INVALID_REQUEST", "message": "One or more SKUs not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in items:
                sku = skus[item["sku_id"]]
                if sku.active_quantity < item["quantity"]:
                    return Response(
                        {"code": "INSUFFICIENT_STOCK", "message": "Insufficient active quantity"},
                        status=status.HTTP_409_CONFLICT,
                    )

            out_of_stock_skus = []
            reserved_at = timezone.now()
            for item in items:
                sku = skus[item["sku_id"]]
                quantity = item["quantity"]
                sku.active_quantity -= quantity
                sku.reserved_quantity += quantity
                sku.save(update_fields=["active_quantity", "reserved_quantity", "updated_at"])
                InventoryReservation.objects.create(
                    order_id=order_id,
                    sku_id=item["sku_id"],
                    quantity=quantity,
                    reserved_at=reserved_at,
                )
                if sku.active_quantity == 0:
                    out_of_stock_skus.append(sku)

            ProcessedRequest.objects.create(
                action=ProcessedRequest.Action.RESERVE,
                idempotency_key=idempotency_key,
            )

            for sku in out_of_stock_skus:
                publish_sku_out_of_stock_to_b2c(sku)

        return Response(
            _reserve_response(order_id, reserved_at),
            status=status.HTTP_200_OK,
        )


class FulfillView(APIView):
    """
    POST /api/v1/inventory/fulfill — доставка заказа: уменьшить reserved_quantity,
    active_quantity не трогать. Идемпотентность по order_id.
    """
    authentication_classes = [RequireServiceKeyAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def post(self, request):
        serializer = InventoryOrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        items = serializer.validated_data["items"]

        existing = ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.FULFILL, idempotency_key=order_id
        ).first()
        if existing:
            return Response(
                _inventory_order_response(
                    order_id, existing.created_at, status_value="FULFILLED"
                ),
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            sku_ids = [item["sku_id"] for item in items]
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_for_update().filter(
                    id__in=sku_ids, deleted=False
                )
            }
            if len(skus) != len(set(sku_ids)):
                return Response(
                    {"code": "INVALID_REQUEST", "message": "One or more SKUs not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in items:
                sku = skus[item["sku_id"]]
                if sku.reserved_quantity < item["quantity"]:
                    return Response(
                        {
                            "code": "INVALID_REQUEST",
                            "message": "Cannot fulfill more than reserved",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            for item in items:
                sku = skus[item["sku_id"]]
                sku.reserved_quantity -= item["quantity"]
                sku.save(update_fields=["reserved_quantity", "updated_at"])

            processed = ProcessedRequest.objects.create(
                action=ProcessedRequest.Action.FULFILL,
                idempotency_key=order_id,
            )

        return Response(
            _inventory_order_response(
                order_id, processed.created_at, status_value="FULFILLED"
            ),
            status=status.HTTP_200_OK,
        )


class UnreserveView(APIView):
    """POST /api/v1/inventory/unreserve — снятие резерва по order_id+sku из хранимой записи."""

    authentication_classes = [RequireServiceKeyAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def post(self, request):
        serializer = UnreserveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        items = serializer.validated_data["items"]

        with transaction.atomic():
            sku_ids = [item["sku_id"] for item in items]
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_for_update().filter(id__in=sku_ids)
            }
            if len(skus) != len(sku_ids):
                return Response(
                    {"code": "INVALID_REQUEST", "message": "One or more SKUs not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in items:
                sku_id = item["sku_id"]
                foreign = (
                    InventoryReservation.objects.select_for_update()
                    .filter(sku_id=sku_id)
                    .exclude(order_id=order_id)
                    .first()
                )
                if foreign is not None:
                    return Response(
                        {
                            "code": "FORBIDDEN",
                            "message": "Cannot unreserve reservation belonging to another order",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

            reservations = {
                r.sku_id: r
                for r in InventoryReservation.objects.select_for_update().filter(
                    order_id=order_id,
                    sku_id__in=sku_ids,
                )
            }

            for item in items:
                sku_id = item["sku_id"]
                quantity = item["quantity"]
                reservation = reservations.get(sku_id)
                if reservation is None:
                    return Response(
                        {
                            "code": "INVALID_REQUEST",
                            "message": "No reservation found for SKU in this order",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if quantity > reservation.quantity:
                    return Response(
                        {
                            "code": "INVALID_REQUEST",
                            "message": "Cannot unreserve more than reserved quantity",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            processed_at = timezone.now()
            for item in items:
                sku_id = item["sku_id"]
                quantity = item["quantity"]
                reservation = reservations[sku_id]
                sku = skus[sku_id]
                sku.active_quantity += quantity
                sku.reserved_quantity -= quantity
                sku.save(update_fields=["active_quantity", "reserved_quantity", "updated_at"])
                if quantity == reservation.quantity:
                    reservation.delete()
                else:
                    reservation.quantity -= quantity
                    reservation.save(update_fields=["quantity"])

        return Response(
            _inventory_order_response(
                order_id, processed_at, status_value="UNRESERVED"
            ),
            status=status.HTTP_200_OK,
        )


class ModerationEventApplyView(APIView):
    authentication_classes = [RequireServiceKeyAuthentication]
    permission_classes = [IsServiceAuthenticated]

    def post(self, request):
        service_id = request.headers.get("X-Service-Id")
        if not service_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "Missing X-Service-Id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ModerationEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            if ProcessedModerationEvent.objects.filter(
                service_id=service_id,
                idempotency_key=data["idempotency_key"],
            ).exists():
                return Response(status=status.HTTP_204_NO_CONTENT)

            product = get_object_or_404(
                Product.objects.select_for_update(),
                pk=data["product_id"],
            )
            if data["event_type"] == "MODERATED":
                product.status = Product.Status.MODERATED
                product.blocking_reason = None
                product.moderator_comment = ""
                product.field_reports = []
            else:
                product.status = (
                    Product.Status.HARD_BLOCKED if data["hard_block"] else Product.Status.BLOCKED
                )
                blocking_reason_id = data.get("blocking_reason_id")
                product.blocking_reason = (
                    BlockingReason.objects.filter(pk=blocking_reason_id).first()
                    if blocking_reason_id
                    else None
                )
                product.moderator_comment = ""
                product.field_reports = data.get("field_reports") or []
                publish_product_blocked_to_b2c(product)

            product.save(
                update_fields=[
                    "status",
                    "blocking_reason",
                    "moderator_comment",
                    "field_reports",
                    "updated_at",
                ]
            )
            ProcessedModerationEvent.objects.create(
                service_id=service_id,
                idempotency_key=data["idempotency_key"],
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
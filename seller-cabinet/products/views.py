import uuid

from django.db import transaction
from django.db.models import Count, IntegerField, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from seller_cabinet.exceptions import AlreadyDeleted, HardBlockedForbidden, NotOwner
from seller_cabinet.permissions import IsSeller, HasValidServiceKey

from .models import Product, SKU, Seller, Invoice, Category, ProcessedRequest, ProcessedModerationEvent
from .serializers import (
    ProductReadSerializer,
    ProductCatalogSerializer,
    ProductSellerListSerializer,
    ProductWriteSerializer,
    SKUWriteSerializer,
    SKUUpdateSerializer,
    SKUReadSerializer,
    ReserveCommandSerializer,
    FulfillCommandSerializer,
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
    resolve_blocking_reason,
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


def _apply_seller_list_status_filter(qs, status_raw: str):
    """Фильтр ?status=ACTIVE|BLOCKED|DELETED."""
    s = (status_raw or "").strip().upper()
    if not s:
        return qs
    if s == "DELETED":
        return qs.filter(deleted=True)
    if s == "BLOCKED":
        return qs.filter(
            deleted=False,
            status__in=(Product.Status.BLOCKED, Product.Status.HARD_BLOCKED),
        )
    if s == "ACTIVE":
        return qs.filter(deleted=False).exclude(
            status__in=(Product.Status.BLOCKED, Product.Status.HARD_BLOCKED),
        )
    return None  # invalid


# ---------- Products ----------

class ProductCreateView(APIView):
    """POST /api/v1/products — US-B2B-01 (канон-flow B2B-1)."""
    permission_classes = [IsSeller]

    def get_permissions(self):
        # ADR: keep backward compatibility for seller-cabinet GET /products,
        # while enabling canonical B2C catalog access on the same endpoint via X-Service-Key.
        if self.request.method == "GET" and self.request.headers.get("X-Service-Key"):
            return [HasValidServiceKey()]
        return super().get_permissions()

    def post(self, request):
        seller = get_or_create_seller(request.user)
        serializer = ProductWriteSerializer(data=request.data, context={"seller": seller})
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductReadSerializer(product).data, status=status.HTTP_201_CREATED)

    def get(self, request):
        if request.headers.get("X-Service-Key"):
            ids_raw = request.query_params.get("ids")
            ids = [x.strip() for x in ids_raw.split(",")] if ids_raw else []
            queryset = Product.objects.filter(
                deleted=False,
                status=Product.Status.MODERATED,
                skus__active_quantity__gt=0,
                skus__deleted=False,
            ).exclude(status=Product.Status.HARD_BLOCKED).distinct()
            if ids:
                queryset = queryset.filter(skus__id__in=ids)
            queryset = queryset.select_related("category").prefetch_related(
                "skus",
            )
            visible_products = []
            for product in queryset:
                visible_skus = [
                    sku for sku in product.skus.all()
                    if not sku.deleted
                    and (not ids or str(sku.id) in ids)
                    and sku.active_quantity > 0
                ]
                if not visible_skus:
                    continue
                product.visible_skus = visible_skus
                visible_products.append(product)

            data = ProductCatalogSerializer(visible_products, many=True).data
            for item, product in zip(data, visible_products):
                item["skus"] = [
                    sku for sku in item["skus"]
                    if any(str(vs.id) == sku["id"] for vs in product.visible_skus)
                ]
            return Response(data)

        # Seller-cabinet: только свои товары; ?seller_id= игнорируется (IDOR).
        seller = resolve_seller_for_jwt(request.user)
        qs = (
            Product.objects.filter(seller=seller)
            .annotate(
                skus_count=Count("skus", filter=Q(skus__deleted=False), distinct=True),
                total_active_quantity=Coalesce(
                    Sum("skus__active_quantity", filter=Q(skus__deleted=False)),
                    Value(0),
                    output_field=IntegerField(),
                ),
            )
            .order_by("-created_at")
        )

        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(title__icontains=search)

        status_raw = request.query_params.get("status", "")
        filtered = _apply_seller_list_status_filter(qs, status_raw)
        if filtered is None and status_raw.strip():
            return Response(
                {
                    "code": "INVALID_REQUEST",
                    "message": "status must be one of: ACTIVE, BLOCKED, DELETED",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if filtered is not None:
            qs = filtered

        total = qs.count()
        limit, offset = _parse_list_limit_offset(request)
        page = qs[offset : offset + limit]

        return Response(
            {
                "items": ProductSellerListSerializer(page, many=True).data,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )


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
    """PUT /api/v1/skus/{id} — US-B2B-03; DELETE /api/v1/skus/{id} — soft delete SKU."""
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
        """DELETE /api/v1/skus/{id} — soft delete SKU (канон-flow delete-sku)."""
        seller = get_or_create_seller(request.user)
        sku = SKU.objects.filter(pk=sku_id, deleted=False).select_related("product").first()
        if sku is None:
            return Response({"error": "SKU not found"}, status=status.HTTP_404_NOT_FOUND)
        if sku.product.seller_id != seller.id:
            return Response({"error": "SKU not found"}, status=status.HTTP_404_NOT_FOUND)
        if sku.product.status == Product.Status.HARD_BLOCKED:
            return Response(
                {"error": "Cannot delete SKU of HARD_BLOCKED product"},
                status=status.HTTP_403_FORBIDDEN,
            )
        if sku.reserved_quantity != 0:
            return Response(
                {
                    "error": "Cannot delete SKU with active reserves",
                    "reserved_quantity": sku.reserved_quantity,
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

        return Response(
            {"ok": True, "message": "SKU deleted successfully"},
            status=status.HTTP_200_OK,
        )

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


class ReserveView(APIView):
    permission_classes = [HasValidServiceKey]

    def post(self, request):
        serializer = ReserveCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data["items"]
        idem_key = serializer.validated_data["idempotency_key"]

        if ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.RESERVE, idempotency_key=idem_key
        ).exists():
            return Response({"ok": True}, status=status.HTTP_200_OK)

        with transaction.atomic():
            sku_ids = [item["sku_id"] for item in items]
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_related("product").select_for_update().filter(
                    id__in=sku_ids, deleted=False
                )
            }
            if len(skus) != len(sku_ids):
                return Response({"code": "INVALID_REQUEST", "message": "One or more SKUs not found"}, status=400)

            for item in items:
                sku = skus[item["sku_id"]]
                if sku.active_quantity < item["quantity"]:
                    return Response(
                        {"code": "INSUFFICIENT_STOCK", "message": "Insufficient active quantity"},
                        status=status.HTTP_409_CONFLICT,
                    )

            out_of_stock_skus = []
            for item in items:
                sku = skus[item["sku_id"]]
                sku.active_quantity -= item["quantity"]
                sku.reserved_quantity += item["quantity"]
                sku.save(update_fields=["active_quantity", "reserved_quantity", "updated_at"])
                if sku.active_quantity == 0:
                    out_of_stock_skus.append(sku)

            ProcessedRequest.objects.create(
                action=ProcessedRequest.Action.RESERVE,
                idempotency_key=idem_key,
            )
            for sku in out_of_stock_skus:
                publish_sku_out_of_stock_to_b2c(sku)

        return Response({"ok": True}, status=status.HTTP_200_OK)


class FulfillView(APIView):
    """
    POST /api/v1/fulfill — доставка заказа: уменьшить reserved_quantity, active_quantity не трогать.
    Идемпотентность по order_id.
    """
    permission_classes = [HasValidServiceKey]

    def post(self, request):
        serializer = FulfillCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_id = serializer.validated_data["order_id"]
        sku_id = serializer.validated_data["sku_id"]
        quantity = serializer.validated_data["quantity"]

        if ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.FULFILL, idempotency_key=order_id
        ).exists():
            return Response({"ok": True}, status=status.HTTP_200_OK)

        with transaction.atomic():
            try:
                sku = SKU.objects.select_for_update().get(pk=sku_id, deleted=False)
            except SKU.DoesNotExist:
                return Response(
                    {"code": "INVALID_REQUEST", "message": "SKU not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if sku.reserved_quantity < quantity:
                return Response(
                    {
                        "code": "INVALID_REQUEST",
                        "message": "Cannot fulfill more than reserved",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sku.reserved_quantity -= quantity
            sku.save(update_fields=["reserved_quantity", "updated_at"])

            ProcessedRequest.objects.create(
                action=ProcessedRequest.Action.FULFILL,
                idempotency_key=order_id,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class UnreserveView(APIView):
    permission_classes = [HasValidServiceKey]

    def post(self, request):
        serializer = ReserveCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data["items"]
        idem_key = serializer.validated_data["idempotency_key"]

        if ProcessedRequest.objects.filter(
            action=ProcessedRequest.Action.UNRESERVE, idempotency_key=idem_key
        ).exists():
            return Response({"ok": True}, status=status.HTTP_200_OK)

        with transaction.atomic():
            sku_ids = [item["sku_id"] for item in items]
            skus = {
                sku.id: sku
                for sku in SKU.objects.select_for_update().filter(id__in=sku_ids, deleted=False)
            }
            if len(skus) != len(sku_ids):
                return Response({"code": "INVALID_REQUEST", "message": "One or more SKUs not found"}, status=400)

            for item in items:
                sku = skus[item["sku_id"]]
                if sku.reserved_quantity < item["quantity"]:
                    return Response(
                        {"code": "INVALID_REQUEST", "message": "Cannot unreserve more than reserved"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            for item in items:
                sku = skus[item["sku_id"]]
                sku.active_quantity += item["quantity"]
                sku.reserved_quantity -= item["quantity"]
                sku.save(update_fields=["active_quantity", "reserved_quantity", "updated_at"])

            ProcessedRequest.objects.create(
                action=ProcessedRequest.Action.UNRESERVE,
                idempotency_key=idem_key,
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class ModerationEventApplyView(APIView):
    permission_classes = [HasValidServiceKey]

    def post(self, request):
        serializer = ModerationEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            sku = get_object_or_404(
                SKU.objects.select_related("product").select_for_update(), id=data["sku_id"]
            )
            if ProcessedModerationEvent.objects.filter(
                sku=sku, idempotency_key=data["idempotency_key"]
            ).exists():
                return Response({"ok": True}, status=status.HTTP_200_OK)

            product = sku.product
            if data["status"] == "MODERATED":
                product.status = Product.Status.MODERATED
                product.blocking_reason = None
                product.moderator_comment = ""
                product.field_reports = []
            else:
                product.status = (
                    Product.Status.HARD_BLOCKED if data["hard_block"] else Product.Status.BLOCKED
                )
                product.blocking_reason = resolve_blocking_reason(data.get("blocking_reason"))
                product.moderator_comment = data.get("blocking_reason") or ""
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
                sku=sku,
                idempotency_key=data["idempotency_key"],
            )

        return Response({"ok": True}, status=status.HTTP_200_OK)
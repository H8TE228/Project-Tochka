from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.forms.fields import BooleanField
from django.core.exceptions import ValidationError as DjangoValidationError

from buyer_cabinet.authentication import JWTAuthentication

from .serializers import FavoritesSerializer
from .models import Favorite

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
    get_category_tree,
    get_category_path,
    b2b_get,
    b2b_get_product,
    b2b_get_products,
    b2b_post,
    b2b_reserve,
    b2b_unreserve,
    catalog_response,
    normalize_pagination,
    product_card_response,
    public_products_params,
    query_params_as_pairs,
    validate_search,
    validate_sort,
    stock_quantity,
    sku_price,
    product_name,
)
import uuid
from django.db import models
from django.utils import timezone

from django.db import transaction
from .models import (
    Subscription, Cart, CartItem, Banner, BannerEvent,
    Collection, Order, OrderItem,
)
from .serializers import (
    SubscriptionWriteSerializer, SubscriptionReadSerializer,
    CartItemWriteSerializer, CartItemQuantityUpdateSerializer,
    BannerSerializer, BannerEventWriteSerializer,
    CollectionSerializer,
    OrderSerializer, OrderListSerializer, CheckoutRequestSerializer,
)

class HealthCheckView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"service": "buyer-cabinet", "status": "ok"})


class ProductCatalogView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        search = request.query_params.get("q")

        try:
            validate_sort(request.query_params.get("sort"))
            validate_search(search)
        except ValueError as exc:
            return Response(
                {"code": "INVALID_REQUEST", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = normalize_pagination(
            request.query_params.get("limit"),
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )
        offset = normalize_pagination(request.query_params.get("offset"), default=0, minimum=0)

        try:
            upstream_response = b2b_get(
                "/api/v1/public/products",
                public_products_params(request.query_params, limit=limit, offset=offset),
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if upstream_response.status_code >= 400:
            return Response(upstream_response.json(), status=upstream_response.status_code)

        return Response(catalog_response(upstream_response.json(), limit=limit, offset=offset))


class CatalogFacetsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            upstream_response = b2b_get("/api/v1/catalog/facets", query_params_as_pairs(request.query_params))
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(upstream_response.json(), status=upstream_response.status_code)


class CategoryFiltersView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, category_id):
        try:
            upstream_response = b2b_get(
                f"/api/v1/categories/{category_id}/filters",
                query_params_as_pairs(request.query_params),
            )
        except UpstreamUnavailable:
            return Response(
                {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": "Category filters temporarily unavailable",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": "Category filters temporarily unavailable",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(upstream_response.json(), status=upstream_response.status_code)


class ProductCardView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, product_id):
        try:
            upstream_response = b2b_get(
                f"/api/v1/public/products/{product_id}",
                query_params_as_pairs(request.query_params),
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Product temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Product temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if upstream_response.status_code >= 400:
            return Response(upstream_response.json(), status=upstream_response.status_code)

        return Response(product_card_response(upstream_response.json()))


class SimilarProductsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, product_id):
        
        limit = normalize_pagination(
            request.query_params.get("limit"),
            default=10,
            minimum=1,
            maximum=20,
        )
        offset = normalize_pagination(request.query_params.get("offset"), default=0, minimum=0)

        try:
            upstream_response = b2b_get(
                f"/api/v1/public/products/{product_id}/similar",
                public_products_params(request.query_params, limit=limit, offset=offset),
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(upstream_response.json(), status=upstream_response.status_code)
    

class CategoryView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            upstream_response = b2b_get(
                "/api/v1/categories",
                query_params_as_pairs(request.query_params)
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(upstream_response.json(), status=upstream_response.status_code)
    

class CategoryTreeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            upstream_response = b2b_get(
                "/api/v1/categories",
                query_params_as_pairs(request.query_params)
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        try:
            tree = get_category_tree(upstream_response.json())
        except ValueError:
            return Response(
                {"error": "orphan_node", "message": "category hierarchy is broken"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except (KeyError, IndexError, TypeError):
            return Response(
                {"code": "INVALID_UPSTREAM_RESPONSE", "message": "Category data validation failed"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(tree, status=upstream_response.status_code)


class CategoryDetailView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, category_id):
        try:
            upstream_response = b2b_get(
                f"/api/v1/categories/{category_id}",
                query_params_as_pairs(request.query_params),
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 400:
            return Response(upstream_response.json(), status=upstream_response.status_code)
        
        response_json = upstream_response.json()

        raw_val = request.query_params.get("include_product_count")
        try:
            include_product_count = BooleanField().to_python(raw_val)
        except DjangoValidationError:
            return Response(
                {"detail": "Некорректное boolean значение."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if include_product_count:
            products = b2b_get_products(params=[("category_id", str(category_id))])
            product_count = products.get("total")
            if not product_count:
                return Response(
                    {"code": "INVALID_UPSTREAM_RESPONSE", "message": "Product data validation failed: total is required"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            response_json["product_count"] = product_count

        return Response(response_json, status=upstream_response.status_code)


class CategoryBreadcrumbsView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            upstream_response = b2b_get("/api/v1/categories", [],)
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        
        category_id = request.query_params.get("category_id")
        product_id = request.query_params.get("product_id")

        if category_id and product_id:
            return Response(
                {"error": "ambiguous_param", "message": "only one of category_id or product_id must be provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not category_id and not product_id:
            return Response(
                {"error": "missing_param", "message": "category_id or product_id must be provided"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if product_id:
            product = b2b_get_product(product_id=product_id)
            category_id = product.get("category_id")
        if not category_id:
            return Response(
                {"code": "INVALID_UPSTREAM_RESPONSE", "message": "Product data validation failed: category_id is required"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        path = get_category_path(categories=upstream_response.json(), category_id=category_id)

        return Response(path, status=status.HTTP_200_OK)


class FavoriteProductView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, product_id):
        b2b_get_product(product_id=product_id) # проверка существования товара
        favorite, created = Favorite.objects.get_or_create(
            user_id = request.user.id,
            product_id = product_id
        )
        serializer = FavoritesSerializer(favorite)
        if created:
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    # во flow используется post, а в openapi используется put
    # лишний запрос будет убран когда и во flow и в swagger будет одинаковый запрос 
    def put(self, request, product_id):
        return self.post(request=request, product_id=product_id)

    def delete(self, request, product_id):
        Favorite.objects.filter(user_id=request.user.id, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FavoriteProductListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = normalize_pagination(
            request.query_params.get("limit"),
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )
        offset = normalize_pagination(request.query_params.get("offset"), default=0, minimum=0)
        favorites = Favorite.objects.filter(user_id=request.user.id).order_by("-added_at")[offset:offset+limit]
        product_ids = list(favorites.values_list("product_id", flat=True))
        if not product_ids:
            return Response({
                "items": [],
                "total_count": 0,
                "limit": limit,
                "offset": offset,
            })
        json_data = {"product_ids": product_ids}

        try:
            upstream_response = b2b_post(
                "/api/v1/public/products",
                params=[],
                json_data=json_data,
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "Catalog temporarily unavailable"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if upstream_response.status_code >= 400:
            return Response(upstream_response.json(), status=upstream_response.status_code)

        return Response(catalog_response(upstream_response.json(), limit=limit, offset=offset))
    


# ============================================================
# US-CART-02: подписки на изменения товара
# ============================================================
def _b2b_check_product_exists(product_id):
    """Проверка существования товара в B2B; кидает 404 если нет."""
    from rest_framework.exceptions import NotFound as DRFNotFound
    try:
        b2b_get_product(str(product_id))
    except Exception:
        # b2b_get_product кидает NotFound из storefront.exceptions; пересаживаем в DRF.
        raise DRFNotFound("Product not found")
 
 
class SubscriptionListCreateView(APIView):
    """POST /api/v1/subscribe — создать подписку. GET — список своих."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        qs = Subscription.objects.filter(user_id=request.user.id).order_by("-created_at")
        return Response({"items": SubscriptionReadSerializer(qs, many=True).data})
 
    def post(self, request):
        serializer = SubscriptionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product_id = serializer.validated_data["product_id"]
        notify_on = serializer.validated_data["notify_on"]
 
        # 404 если товара нет в B2B
        _b2b_check_product_exists(product_id)
 
        # 409 если уже подписан
        if Subscription.objects.filter(user_id=request.user.id, product_id=product_id).exists():
            return Response(
                {"code": "CONFLICT", "message": "Already subscribed to this product"},
                status=status.HTTP_409_CONFLICT,
            )
 
        sub = Subscription.objects.create(
            user_id=request.user.id, product_id=product_id, notify_on=notify_on,
        )
        return Response(
            SubscriptionReadSerializer(sub).data, status=status.HTTP_201_CREATED
        )
 
 
class SubscriptionDetailView(APIView):
    """DELETE /api/v1/subscribe/{subscription_id} — отписаться."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
 
    def delete(self, request, subscription_id):
        try:
            sub = Subscription.objects.get(id=subscription_id, user_id=request.user.id)
        except Subscription.DoesNotExist:
            return Response(
                {"code": "NOT_FOUND", "message": "Subscription not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        sub.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
 
 
# ============================================================
# US-CART-03: корзина
# ============================================================
class _SkuLookup:
    """Утилиты для обогащения корзины из B2B."""
 
    @staticmethod
    def collect_sku_data(sku_ids):
        """
        Возвращает: dict {sku_id_str: {"sku": {...}, "product": {...}}}.
        Для MVP — простой проход по public-каталогу B2B и фильтрация по нужным sku_ids.
        В будущем заменим на batch-endpoint /skus в B2B.
        """
        result = {}
        try:
            data = b2b_get_products([("limit", "1000"), ("offset", "0")])
        except Exception:
            return result
        items = data.get("items", []) if isinstance(data, dict) else []
        for product in items:
            for sku in product.get("skus", []) or []:
                if str(sku.get("id")) in sku_ids:
                    result[str(sku["id"])] = {"sku": sku, "product": product}
        return result
 
 
def _get_or_create_user_cart(user) -> "Cart":
    cart, _ = Cart.objects.get_or_create(user_id=user.id)
    return cart
 
 
def _get_or_create_session_cart(session_id: str) -> "Cart":
    cart, _ = Cart.objects.get_or_create(session_id=session_id)
    return cart
 
 
def _resolve_cart_for_request(request):
    """Возвращает корзину пользователя (auth) либо гостя (X-Session-Id)."""
    if request.user and request.user.is_authenticated:
        return _get_or_create_user_cart(request.user)
    session_id = request.headers.get("X-Session-Id")
    if session_id:
        return _get_or_create_session_cart(session_id)
    return None
 
 
def _enrich_cart_items(cart) -> dict:
    """Собирает payload корзины с обогащением из B2B и пометкой недоступных позиций."""
    items_qs = list(cart.items.all())
    sku_ids = {str(i.sku_id) for i in items_qs}
    sku_data = _SkuLookup.collect_sku_data(sku_ids) if sku_ids else {}

    enriched = []
    subtotal = 0
    all_available = True
    for item in items_qs:
        sid = str(item.sku_id)
        bundle = sku_data.get(sid)
        if bundle is None:
            all_available = False
            enriched.append({
                "sku_id": sid,
                "quantity": item.quantity,
                "is_available": False,
                "unavailable_reason": "sku_not_found",
                "unit_price": None,
                "line_total": None,
                "available_quantity": 0,
                "name": None,
                "image": None,
            })
            continue
        sku = bundle["sku"]
        product = bundle["product"]
        available_qty = int(sku.get("active_quantity") or 0)
        unit_price = int(sku.get("price") or 0)
        unavailable_reason = None
        if available_qty <= 0:
            unavailable_reason = "out_of_stock"
        elif available_qty < item.quantity:
            unavailable_reason = "insufficient_stock"
        is_available = unavailable_reason is None
        if not is_available:
            all_available = False

        line_total = unit_price * item.quantity if is_available else 0
        enriched.append({
            "sku_id": sid,
            "quantity": item.quantity,
            "is_available": is_available,
            "unavailable_reason": unavailable_reason,
            "unit_price": unit_price,
            "line_total": line_total,
            "available_quantity": available_qty,
            "name": sku.get("name") or product.get("title") or "",
            "image": sku.get("image") or "",
            "product_id": str(product.get("id")) if product.get("id") else None,
        })
        if is_available:
            subtotal += line_total

    items_count = sum(i["quantity"] for i in enriched)
    return {
        "id": str(cart.id),
        "items": enriched,
        "items_count": items_count,
        "subtotal": subtotal,
        "is_valid": all_available and bool(enriched),
    }
 
 
class CartView(APIView):
    """GET /api/v1/cart — содержимое корзины с обогащением из B2B."""
    authentication_classes = [JWTAuthentication]
    permission_classes = []  # доступ гостю по X-Session-Id или аутентифицированному
 
    def get(self, request):
        cart = _resolve_cart_for_request(request)
        if cart is None:
            return Response({"id": None, "items": [], "total_amount": 0})
        return Response(_enrich_cart_items(cart))
 
 
class CartItemListCreateView(APIView):
    """POST /api/v1/cart/items — добавить SKU в корзину."""
    authentication_classes = [JWTAuthentication]
    permission_classes = []
 
    def post(self, request):
        cart = _resolve_cart_for_request(request)
        if cart is None:
            return Response(
                {"code": "INVALID_REQUEST", "message": "Provide X-Session-Id header or authenticate"},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        serializer = CartItemWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sku_id = serializer.validated_data["sku_id"]
        quantity = serializer.validated_data["quantity"]
 
        item, created = CartItem.objects.get_or_create(
            cart=cart, sku_id=sku_id, defaults={"quantity": quantity},
        )
        if not created:
            # Повторное добавление того же SKU → увеличить quantity
            item.quantity = item.quantity + quantity
            item.save(update_fields=["quantity", "updated_at"])
 
        return Response(
            _enrich_cart_items(cart),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
 
 
class CartItemDetailView(APIView):
    """PATCH/DELETE /api/v1/cart/items/{sku_id}."""
    authentication_classes = [JWTAuthentication]
    permission_classes = []
 
    def _find_item(self, request, sku_id):
        cart = _resolve_cart_for_request(request)
        if cart is None:
            return None, None
        try:
            return cart, cart.items.get(sku_id=sku_id)
        except CartItem.DoesNotExist:
            return cart, None
 
    def patch(self, request, sku_id):
        cart, item = self._find_item(request, sku_id)
        if cart is None or item is None:
            return Response(
                {"code": "NOT_FOUND", "message": "Cart item not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CartItemQuantityUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item.quantity = serializer.validated_data["quantity"]
        item.save(update_fields=["quantity", "updated_at"])
        return Response(_enrich_cart_items(cart))
 
    def delete(self, request, sku_id):
        cart, item = self._find_item(request, sku_id)
        if cart is None or item is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
 
 
class CartMergeView(APIView):
    """
    POST /api/v1/cart/merge — слияние гостевой корзины с пользовательской при логине.
    Гость — по X-Session-Id из заголовка; пользователь — из JWT.
    При конфликте sku берётся MAX(guest, auth), потом гостевая удаляется.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
 
    def post(self, request):
        session_id = request.headers.get("X-Session-Id")
        if not session_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "X-Session-Id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        try:
            guest_cart = Cart.objects.get(session_id=session_id)
        except Cart.DoesNotExist:
            user_cart = _get_or_create_user_cart(request.user)
            return Response(_enrich_cart_items(user_cart))
 
        user_cart = _get_or_create_user_cart(request.user)
 
        for g_item in guest_cart.items.all():
            existing = user_cart.items.filter(sku_id=g_item.sku_id).first()
            if existing is None:
                CartItem.objects.create(
                    cart=user_cart, sku_id=g_item.sku_id, quantity=g_item.quantity,
                )
            else:
                # MAX(guest, auth)
                existing.quantity = max(existing.quantity, g_item.quantity)
                existing.save(update_fields=["quantity", "updated_at"])
 
        # Удаляем гостевую (включая её items по CASCADE)
        guest_cart.delete()
 
        return Response(_enrich_cart_items(user_cart))
 
 
# ============================================================
# US-CART-04: баннеры
# ============================================================
class HomeBannersView(APIView):
    """GET /api/v1/home/banners — активные баннеры по расписанию (публичный)."""
    authentication_classes = []
    permission_classes = []
 
    def get(self, request):
        now = timezone.now()
        qs = Banner.objects.filter(is_active=True)
        qs = qs.filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
        qs = qs.filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
        qs = qs.order_by("-priority", "-created_at")
        return Response({"items": BannerSerializer(qs, many=True).data})
 
 
class BannerEventsView(APIView):
    """POST /api/v1/banner-events — запись клика/показа (CTR-аналитика)."""
    authentication_classes = [JWTAuthentication]
    permission_classes = []
 
    def post(self, request):
        serializer = BannerEventWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        banner_id = serializer.validated_data["banner_id"]
        event_type = serializer.validated_data["event_type"]
 
        try:
            banner = Banner.objects.get(id=banner_id)
        except Banner.DoesNotExist:
            return Response(
                {"code": "INVALID_REQUEST", "message": "Banner not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        # user_id из JWT, никогда из тела запроса
        user_id = None
        if request.user and request.user.is_authenticated:
            uid = getattr(request.user, "id", None)
            if isinstance(uid, uuid.UUID):
                user_id = uid
        session_id = request.headers.get("X-Session-Id")
 
        BannerEvent.objects.create(
            banner=banner,
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================
# US-CART-05: подборки товаров на главной
# ============================================================
class CollectionListView(APIView):
    """GET /api/v1/catalog/collections — список активных подборок с товарами (публичный).

    Контракт: возвращает plain array объектов Collection.
    Каждая Collection содержит поле products с обогащёнными данными из B2B.
    Недоступные в B2B товары исключаются — их UUID в unavailable_ids.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        today = timezone.now().date()
        qs = list(
            Collection.objects.filter(
                is_active=True
            ).filter(
                models.Q(start_date__isnull=True) | models.Q(start_date__lte=today)
            ).prefetch_related("collection_products")
            .order_by("-priority", "-created_at")
        )

        if not qs:
            return Response([])

        # Собираем все product_ids по всем подборкам для одного batch-запроса к B2B
        all_product_ids = list({
            str(cp.product_id)
            for col in qs
            for cp in col.collection_products.all()
        })

        b2b_by_id = {}
        if all_product_ids:
            try:
                upstream = b2b_post(
                    "/api/v1/public/products",
                    params=[],
                    json_data={"product_ids": all_product_ids},
                )
                if upstream.status_code < 400:
                    b2b_items = upstream.json().get("items", [])
                    b2b_by_id = {str(p.get("id")): p for p in b2b_items}
            except UpstreamUnavailable:
                # При недоступности B2B возвращаем подборки с пустыми products
                pass

        result = []
        for col in qs:
            ordered_ids = [
                str(cp.product_id)
                for cp in sorted(col.collection_products.all(), key=lambda x: x.ordering)
            ]
            products = [b2b_by_id[pid] for pid in ordered_ids if pid in b2b_by_id]
            unavailable_ids = [pid for pid in ordered_ids if pid not in b2b_by_id]
            result.append({
                "id": str(col.id),
                "title": col.title,
                "description": col.description,
                "cover_image_url": col.cover_image_url,
                "target_url": col.target_url,
                "priority": col.priority,
                "products": products,
                "unavailable_ids": unavailable_ids,
            })

        return Response(result)


class CollectionProductsView(APIView):
    """GET /api/v1/collections/{collection_id}/products — товары подборки с batch-обогащением из B2B."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, collection_id):
        try:
            collection = Collection.objects.get(id=collection_id, is_active=True)
        except Collection.DoesNotExist:
            return Response(
                {"code": "NOT_FOUND", "message": "Collection not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        product_ids = list(
            collection.collection_products.order_by("ordering").values_list(
                "product_id", flat=True
            )
        )

        if not product_ids:
            return Response({
                "collection_id": str(collection.id),
                "collection_title": collection.title,
                "items": [],
                "unavailable_ids": [],
                "total_products": 0,
            })

        # Batch-обогащение из B2B; B2B возвращает только доступные товары
        try:
            upstream_response = b2b_post(
                "/api/v1/public/products",
                params=[],
                json_data={"product_ids": [str(pid) for pid in product_ids]},
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "B2B temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if upstream_response.status_code >= 500:
            return Response(
                {"code": "UPSTREAM_UNAVAILABLE", "message": "B2B temporarily unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if upstream_response.status_code >= 400:
            return Response(upstream_response.json(), status=upstream_response.status_code)

        b2b_data = upstream_response.json()
        b2b_items = b2b_data.get("items", []) if isinstance(b2b_data, dict) else []

        # Товары, не вернувшиеся из B2B — недоступны (удалены/заблокированы)
        available_ids = {str(p.get("id")) for p in b2b_items}
        unavailable_ids = [str(pid) for pid in product_ids if str(pid) not in available_ids]

        limit = normalize_pagination(
            request.query_params.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT
        )
        offset = normalize_pagination(
            request.query_params.get("offset"), default=0, minimum=0
        )

        return Response({
            "collection_id": str(collection.id),
            "collection_title": collection.title,
            "items": b2b_items[offset: offset + limit],
            "unavailable_ids": unavailable_ids,
            "total_products": len(product_ids),
        })


# ============================================================
# US-ORD-01: оформление заказа (checkout)
# ============================================================

def _build_sku_index(b2b_products: list[dict]) -> dict:
    """
    Строит индекс {sku_id_str: {"sku": {...}, "product": {...}}} из ответа B2B.
    B2B возвращает список продуктов, каждый со списком skus.
    """
    index = {}
    for product in b2b_products:
        for sku in product.get("skus", []) or []:
            sku_id = str(sku.get("id", ""))
            if sku_id:
                index[sku_id] = {"sku": sku, "product": product}
    return index


def _order_to_response(order: Order) -> dict:
    """Сериализует заказ в API-ответ."""
    return OrderSerializer(order).data


class OrderListCreateView(APIView):
    """
    POST /api/v1/orders — checkout (создание заказа).
    GET /api/v1/orders — список заказов пользователя.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = normalize_pagination(
            request.query_params.get("limit"), default=DEFAULT_LIMIT, minimum=1, maximum=MAX_LIMIT
        )
        offset = normalize_pagination(request.query_params.get("offset"), default=0, minimum=0)
        status_filter = request.query_params.get("status")

        qs = Order.objects.filter(user_id=request.user.id).prefetch_related("items")
        if status_filter:
            qs = qs.filter(status=status_filter)

        total_count = qs.count()
        orders = list(qs[offset: offset + limit])
        return Response({
            "items": OrderListSerializer(orders, many=True).data,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        })

    def post(self, request):
        raw_key = request.META.get("HTTP_IDEMPOTENCY_KEY", "")
        if not raw_key:
            return Response(
                {"code": "MISSING_HEADER", "message": "Idempotency-Key header is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            idempotency_key = uuid.UUID(raw_key)
        except (ValueError, AttributeError):
            return Response(
                {"code": "INVALID_HEADER", "message": "Idempotency-Key must be a valid UUID"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ser = CheckoutRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        items = data["items"]
        delivery_address = str(data["address_id"])

        # 0. Idempotency check — вернуть существующий заказ без повторного резервирования
        try:
            existing = Order.objects.prefetch_related("items").get(
                user_id=request.user.id, idempotency_key=idempotency_key
            )
            return Response(OrderSerializer(existing).data, status=status.HTTP_200_OK)
        except Order.DoesNotExist:
            pass

        # 1. Получить актуальные данные из B2B для проверки наличия
        product_ids_for_request = []
        # B2B поддерживает GET /api/v1/public/products?ids=... — используем b2b_get
        # Собираем уникальные sku_ids; на самом деле нам нужны product_ids, но
        # для MVP вызываем b2b_get_products чтобы получить все skus и найти нужные.
        try:
            b2b_resp = b2b_get_products([("limit", "1000"), ("offset", "0")])
        except Exception:
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "Сервис товаров временно недоступен, попробуйте позже"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        b2b_items_list = b2b_resp.get("items", []) if isinstance(b2b_resp, dict) else []
        sku_index = _build_sku_index(b2b_items_list)

        # 2. Валидация наличия каждого SKU
        failed_items = []
        for item in items:
            sku_id_str = str(item["sku_id"])
            bundle = sku_index.get(sku_id_str)
            if bundle is None:
                failed_items.append({"sku_id": sku_id_str, "reason": "SKU_NOT_FOUND"})
                continue
            product = bundle["product"]
            sku = bundle["sku"]
            prod_status = product.get("status", "")
            if prod_status == "BLOCKED":
                failed_items.append({"sku_id": sku_id_str, "reason": "PRODUCT_BLOCKED"})
                continue
            if product.get("deleted") or prod_status == "DELETED":
                failed_items.append({"sku_id": sku_id_str, "reason": "PRODUCT_DELETED"})
                continue
            available_qty = stock_quantity(sku)
            requested_qty = item["quantity"]
            if available_qty <= 0:
                failed_items.append({
                    "sku_id": sku_id_str,
                    "reason": "OUT_OF_STOCK",
                    "requested": requested_qty,
                    "available": 0,
                })
            elif available_qty < requested_qty:
                failed_items.append({
                    "sku_id": sku_id_str,
                    "reason": "INSUFFICIENT_STOCK",
                    "requested": requested_qty,
                    "available": available_qty,
                })

        if failed_items:
            return Response(
                {
                    "code": "RESERVE_FAILED",
                    "message": "Не удалось зарезервировать товары",
                    "failed_items": failed_items,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # 3. Резервирование (all-or-nothing) в B2B
        reserve_items = [
            {"sku_id": str(item["sku_id"]), "quantity": item["quantity"]}
            for item in items
        ]
        try:
            reserve_resp = b2b_reserve(
                idempotency_key=str(idempotency_key),
                items=reserve_items,
            )
        except UpstreamUnavailable:
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "Сервис товаров временно недоступен, попробуйте позже"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if reserve_resp.status_code >= 500:
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "Сервис товаров временно недоступен, попробуйте позже"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if reserve_resp.status_code == 409:
            reserve_data = reserve_resp.json()
            return Response(
                {
                    "code": "RESERVE_FAILED",
                    "message": "Не удалось зарезервировать товары",
                    "failed_items": reserve_data.get("failed_items", []),
                },
                status=status.HTTP_409_CONFLICT,
            )

        if reserve_resp.status_code >= 400:
            return Response(
                {"code": "RESERVE_FAILED", "message": "Резервирование отклонено B2B"},
                status=status.HTTP_409_CONFLICT,
            )

        # 4. Создать Order и OrderItems атомарно с фиксацией цен
        with transaction.atomic():
            total_amount = sum(
                sku_price(sku_index[str(item["sku_id"])]["sku"]) * item["quantity"]
                for item in items
            )
            order = Order.objects.create(
                user_id=request.user.id,
                status=Order.STATUS_PAID,
                total_amount=total_amount,
                delivery_address=delivery_address,
                idempotency_key=idempotency_key,
            )
            for item in items:
                sku_id_str = str(item["sku_id"])
                bundle = sku_index[sku_id_str]
                sku = bundle["sku"]
                product = bundle["product"]
                unit_price = sku_price(sku)
                qty = item["quantity"]
                OrderItem.objects.create(
                    order=order,
                    sku_id=sku_id_str,
                    product_id=str(product.get("id", "")),
                    product_title=product_name(product),
                    sku_name=sku.get("name", ""),
                    quantity=qty,
                    unit_price=unit_price,
                    line_total=unit_price * qty,
                )

        order.refresh_from_db()
        return Response(
            OrderSerializer(Order.objects.prefetch_related("items").get(pk=order.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(APIView):
    """GET /api/v1/orders/{order_id} — детали заказа."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.prefetch_related("items").get(
                id=order_id, user_id=request.user.id
            )
        except Order.DoesNotExist:
            return Response(
                {"code": "ORDER_NOT_FOUND", "message": "Заказ не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrderSerializer(order).data)


class OrderCancelView(APIView):
    """POST /api/v1/orders/{order_id}/cancel — отмена заказа."""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.prefetch_related("items").get(
                id=order_id, user_id=request.user.id
            )
        except Order.DoesNotExist:
            return Response(
                {"code": "ORDER_NOT_FOUND", "message": "Заказ не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if order.status not in Order.CANCELLABLE_STATUSES:
            return Response(
                {
                    "code": "CANCEL_NOT_ALLOWED",
                    "message": f"Отмена невозможна: заказ в статусе {order.status}",
                    "current_status": order.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Вызов unreserve в B2B
        unreserve_items = [
            {"sku_id": str(item.sku_id), "quantity": item.quantity}
            for item in order.items.all()
        ]
        try:
            unreserve_resp = b2b_unreserve(
                order_id=str(order.id),
                items=unreserve_items,
            )
            if unreserve_resp.status_code < 500:
                order.status = Order.STATUS_CANCELLED
            else:
                order.status = Order.STATUS_CANCEL_PENDING
        except UpstreamUnavailable:
            order.status = Order.STATUS_CANCEL_PENDING

        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order).data)
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
    catalog_response,
    normalize_pagination,
    product_card_response,
    public_products_params,
    query_params_as_pairs,
    validate_search,
    validate_sort,
)
import uuid
from django.db import models
from django.utils import timezone

from .models import (
    Subscription, Cart, CartItem, Banner, BannerEvent,
)
from .serializers import (
    SubscriptionWriteSerializer, SubscriptionReadSerializer,
    CartItemWriteSerializer, CartItemQuantityUpdateSerializer,
    BannerSerializer, BannerEventWriteSerializer,
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
    total_amount = 0
    for item in items_qs:
        sid = str(item.sku_id)
        bundle = sku_data.get(sid)
        if bundle is None:
            enriched.append({
                "sku_id": sid,
                "quantity": item.quantity,
                "available": False,
                "unavailable_reason": "sku_not_found",
                "price": None,
                "name": None,
                "image": None,
            })
            continue
        sku = bundle["sku"]
        product = bundle["product"]
        available_qty = int(sku.get("active_quantity") or 0)
        price = int(sku.get("price") or 0)
        unavailable_reason = None
        if available_qty <= 0:
            unavailable_reason = "out_of_stock"
        elif available_qty < item.quantity:
            unavailable_reason = "insufficient_stock"
        is_available = unavailable_reason is None
 
        enriched.append({
            "sku_id": sid,
            "quantity": item.quantity,
            "available": is_available,
            "unavailable_reason": unavailable_reason,
            "price": price,
            "name": sku.get("name") or product.get("title") or "",
            "image": sku.get("image") or "",
            "product_id": str(product.get("id")) if product.get("id") else None,
        })
        if is_available:
            total_amount += price * item.quantity
 
    return {
        "id": str(cart.id),
        "items": enriched,
        "total_amount": total_amount,
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
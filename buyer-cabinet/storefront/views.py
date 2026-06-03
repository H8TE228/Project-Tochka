from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from django.forms.fields import BooleanField
from django.core.exceptions import ValidationError as DjangoValidationError

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
    get_category_tree,
    get_category_path,
    b2b_get,
    b2b_get_product,
    b2b_get_products,
    catalog_response,
    normalize_pagination,
    product_card_response,
    public_products_params,
    query_params_as_pairs,
    validate_search,
    validate_sort,
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
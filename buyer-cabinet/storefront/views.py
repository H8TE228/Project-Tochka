from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from .services import (
    MAX_LIMIT,
    DEFAULT_LIMIT,
    UpstreamUnavailable,
    b2b_get,
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
        try:
            validate_sort(request.query_params.get("sort"))
            validate_search(request.query_params.get("search"))
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
                "/api/public/products",
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


class ProductCardView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, product_id):
        try:
            upstream_response = b2b_get(
                f"/api/public/products/{product_id}",
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

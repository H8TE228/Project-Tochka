from django.urls import path

from .views import (
    CatalogFacetsView,
    CategoryFiltersView,
    HealthCheckView,
    ProductCardView,
    ProductCatalogView,
)


urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health"),
    path("catalog/products", ProductCatalogView.as_view(), name="catalog-products"),
    path("catalog/facets", CatalogFacetsView.as_view(), name="catalog-facets"),
    path(
        "categories/<uuid:category_id>/filters",
        CategoryFiltersView.as_view(),
        name="category-filters",
    ),
    path("products/<uuid:product_id>", ProductCardView.as_view(), name="product-card"),
]

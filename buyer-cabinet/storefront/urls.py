from django.urls import path

from .views import (
    CatalogFacetsView,
    CategoryFiltersView,
    HealthCheckView,
    ProductCardView,
    ProductCatalogView,
    SimilarProductsView,
    CategoryView,
    CategoryTreeView,
    CategoryDetailView,
    CategoryBreadcrumbsView,
    FavoriteProductView,
    FavoriteProductListView,
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
    path("catalog/categories", CategoryView.as_view(), name="categories"),
    path("catalog/categories/tree", CategoryTreeView.as_view(), name="category-tree"),
    path("catalog/categories/<uuid:category_id>", CategoryDetailView.as_view(), name="category-detail"),
    path("breadcrumbs", CategoryBreadcrumbsView.as_view(), name="category-breadcrumbs"),
    path("catalog/products/<uuid:product_id>", ProductCardView.as_view(), name="product-card"),
    path("catalog/products/<uuid:product_id>/similar", SimilarProductsView.as_view(), name="similar-products"),
    path("favorites/<uuid:product_id>", FavoriteProductView.as_view(), name="favorite-product"),
    path("favorites", FavoriteProductListView.as_view(), name="list-favorite-products"),
]

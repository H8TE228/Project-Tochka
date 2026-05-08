from django.urls import path

from .views import CatalogFacetsView, HealthCheckView, ProductCardView, ProductCatalogView


urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health"),
    path("products", ProductCatalogView.as_view(), name="products"),
    path("products/<uuid:product_id>", ProductCardView.as_view(), name="product-card"),
    path("catalog/facets", CatalogFacetsView.as_view(), name="catalog-facets"),
]

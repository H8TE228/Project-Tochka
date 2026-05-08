from django.urls import path

from .views import CatalogFacetsView, HealthCheckView, ProductCatalogView


urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health"),
    path("products", ProductCatalogView.as_view(), name="products"),
    path("catalog/facets", CatalogFacetsView.as_view(), name="catalog-facets"),
]

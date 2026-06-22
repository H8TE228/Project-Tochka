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
    # US-CART-02
    ProductSubscriptionView,
    # US-CART-03
    CartView,
    CartItemListCreateView,
    CartItemDetailView,
    CartMergeView,
    # US-CART-04
    HomeBannersView,
    BannerEventsView,
    # US-CART-05
    CollectionListView,
    CollectionProductsView,
    # US-ORD-01
    OrderListCreateView,
    OrderDetailView,
    OrderCancelView,
    # US-ORD-04
    ProductEventView,
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
    path("favorites/<uuid:product_id>/subscribe", ProductSubscriptionView.as_view(), name="product-subscription"),
    path("favorites/<uuid:product_id>", FavoriteProductView.as_view(), name="favorite-product"),
    path("favorites", FavoriteProductListView.as_view(), name="list-favorite-products"),

    # US-CART-03: корзина
    path("cart", CartView.as_view(), name="cart"),
    path("cart/items", CartItemListCreateView.as_view(), name="cart-items"),
    path("cart/items/<uuid:sku_id>", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("cart/merge", CartMergeView.as_view(), name="cart-merge"),

    # US-CART-04: баннеры
    path("catalog/banners", HomeBannersView.as_view(), name="catalog-banners"),
    path("banner-events", BannerEventsView.as_view(), name="banner-events"),

    # US-CART-05: подборки товаров
    path("catalog/collections", CollectionListView.as_view(), name="catalog-collections"),
    path("collections/<uuid:collection_id>/products", CollectionProductsView.as_view(), name="collection-products"),

    # US-ORD-01: заказы
    path("orders", OrderListCreateView.as_view(), name="orders"),
    path("orders/<uuid:order_id>", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<uuid:order_id>/cancel", OrderCancelView.as_view(), name="order-cancel"),

    # US-ORD-04: product events from B2B
    path("b2b/events", ProductEventView.as_view(), name="b2b-events"),
]
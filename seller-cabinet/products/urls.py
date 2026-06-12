from django.urls import path
from . import views

urlpatterns = [
    path("products", views.ProductsView.as_view()),
    path("public/products", views.PublicProductCatalogView.as_view()),
    path("products/<uuid:product_id>", views.ProductDetailView.as_view()),

    path("tickets/<uuid:ticket_id>/approve", views.TicketApproveView.as_view()),

    path("skus", views.SKUCreateView.as_view()),
    path("skus/<uuid:sku_id>", views.SKUDetailView.as_view()),
    
    path("invoices", views.InvoiceCreateView.as_view()),
    path("invoices/accept", views.InvoiceAcceptView.as_view()),
    path("inventory/reserve", views.ReserveView.as_view()),
    path("inventory/unreserve", views.UnreserveView.as_view()),
    path("inventory/fulfill", views.FulfillView.as_view()),
    path("moderation/events", views.ModerationEventApplyView.as_view()),
    
    path("categories", views.CategoryListCreateView.as_view()),
    path("categories/<uuid:category_id>", views.CategoryDetailView.as_view()),
]

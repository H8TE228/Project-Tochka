from django.urls import path
from . import views

urlpatterns = [
    path("products", views.ProductCreateView.as_view()),
    path("products/<uuid:product_id>", views.ProductDetailView.as_view()),

    path("skus", views.SKUCreateView.as_view()),
    path("skus/<uuid:sku_id>", views.SKUDetailView.as_view()),

    path("invoices", views.InvoiceCreateView.as_view()),
    # Старый путь — для обратной совместимости (invoice_id в body)
    path("invoices/accept", views.InvoiceAcceptView.as_view()),
    # Новый канонический путь по openapi (invoice_id в URL)
    path("invoices/<uuid:invoice_id>/accept", views.InvoiceAcceptView.as_view()),

    path("reserve", views.ReserveView.as_view()),
    path("fulfill", views.FulfillView.as_view()),
    path("unreserve", views.UnreserveView.as_view()),
    path("events/moderation", views.ModerationEventApplyView.as_view()),

    path("categories", views.CategoryListCreateView.as_view()),
    path("categories/<uuid:category_id>", views.CategoryDetailView.as_view()),
]
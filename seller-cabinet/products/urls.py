from django.urls import path
from . import views

urlpatterns = [
    path("products", views.ProductCreateView.as_view()),
    path("products/<uuid:product_id>", views.ProductDetailView.as_view()),

    path("skus", views.SKUCreateView.as_view()),
    path("skus/<uuid:sku_id>", views.SKUDetailView.as_view()),
    
    path("invoices", views.InvoiceCreateView.as_view()),
    path("invoices/accept", views.InvoiceAcceptView.as_view()),
    
    path("categories", views.CategoryListCreateView.as_view()),
    path("categories/<uuid:category_id>", views.CategoryDetailView.as_view()),
]

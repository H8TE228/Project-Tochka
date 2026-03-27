from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from . import models


@admin.register(models.User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'created_at')
    list_filter = ('is_staff', 'is_superuser')
    search_fields = ('username', 'email')
    readonly_fields = ('created_at',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('created_at',)}),
    )


@admin.register(models.Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('title', 'seller', 'status', 'category', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'slug')
    raw_id_fields = ('seller', 'category')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(models.SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'price_cents', 'active_quantity', 'is_enabled')
    list_filter = ('is_enabled', 'product')
    search_fields = ('name', 'product__title')
    readonly_fields = ('created_at', 'updated_at')


# Регистрация остальных моделей (можно добавить позже)
# admin.site.register(models.ProductImage)
# admin.site.register(models.SKUImage)
# admin.site.register(models.ProductCharacteristic)
# admin.site.register(models.SKUCharacteristic)
# admin.site.register(models.FavoriteItem)
# admin.site.register(models.Cart)
# admin.site.register(models.CartItem)
# admin.site.register(models.Order)
# admin.site.register(models.OrderItem)
# admin.site.register(models.Banner)
# admin.site.register(models.Collection)

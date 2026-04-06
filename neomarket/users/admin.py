from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User

class UserAdmin(BaseUserAdmin):
    model = User
    readonly_fields = ['last_login', 'created_at', 'updated_at',]
    list_display = [
        'email',
        'username',
        'phone_number',
        'country',
        'region',
        'city',
        'district',
        'created_at',
        'updated_at'
    ]
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number', 'profile_picture')}),
        (_('Address'), {'fields': ('country', 'region', 'city', 'district', 'street', 'building', 'apartment')}),
        (_('Important dates'), {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'phone_number', 'password1', 'password2', 'is_staff'),
        }),
    )
    list_filter = ['country', 'region', 'city', 'district', 'created_at', 'updated_at']
    search_fields = ['email', 'username', 'phone_number']
    ordering = ['email',]

admin.site.register(User, UserAdmin)
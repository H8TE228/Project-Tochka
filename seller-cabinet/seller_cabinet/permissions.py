from rest_framework.permissions import BasePermission
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated


class IsSeller(BasePermission):
    """Allow access only to users with role='seller'."""

    message = "Only sellers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "seller"
        )


class HasValidServiceKey(BasePermission):
    """Allow service-to-service calls authenticated by X-Service-Key."""

    message = "Invalid X-Service-Key."

    def has_permission(self, request, view):
        actual = request.headers.get("X-Service-Key")
        expected = settings.SERVICE_API_KEY
        if not actual:
            raise NotAuthenticated("Missing X-Service-Key")
        if not expected or actual != expected:
            raise AuthenticationFailed("Invalid X-Service-Key")
        return True

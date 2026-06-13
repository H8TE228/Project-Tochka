from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.permissions import BasePermission, IsAuthenticated


class IsClient(BasePermission):
    """Allow access only to users with role='client'."""

    message = "Only clients can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "client"
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


class IsServiceAuthenticated(IsAuthenticated):
    """Service endpoints: caller must be authenticated via X-Service-Key."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        return getattr(request.user, "is_service", False)
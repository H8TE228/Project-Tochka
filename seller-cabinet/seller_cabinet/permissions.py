from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.exceptions import NotAuthenticated, PermissionDenied


class IsSeller(BasePermission):
    """Allow access only to users with role='seller'."""

    message = "Only sellers can perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        if getattr(request.user, "role", None) != "seller":
            raise PermissionDenied(self.message)
        return True


class IsServiceAuthenticated(IsAuthenticated):
    """Service endpoints: caller must be authenticated via X-Service-Key."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        return getattr(request.user, "is_service", False)


class IsModerator(BasePermission):
    """Allow access only to JWT users with role='moderator'."""

    message = "Only moderators can perform this action."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            raise NotAuthenticated()
        if getattr(request.user, "role", None) != "moderator":
            raise PermissionDenied(self.message)
        return True

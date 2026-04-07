from rest_framework.permissions import BasePermission


class IsSeller(BasePermission):
    """Allow access only to users with role='seller'."""

    message = "Only sellers can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "seller"
        )

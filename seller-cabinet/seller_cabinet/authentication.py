import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TokenUser:
    """Lightweight user object populated from JWT payload — no DB lookup."""

    is_authenticated = True

    def __init__(self, payload: dict):
        self.id = payload.get("user_id")
        self.email = payload.get("email", "")
        self.role = payload.get("role", "")


class JWTAuthentication(BaseAuthentication):
    """Validate access tokens issued by the auth service (shared SECRET_KEY)."""

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token.")

        return TokenUser(payload), token

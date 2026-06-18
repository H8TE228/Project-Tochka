import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated


class TokenUser:
    """Lightweight user object populated from JWT payload without DB lookup."""

    is_authenticated = True

    def __init__(self, payload: dict):
        self.id = payload.get("user_id")
        self.email = payload.get("email", "")
        self.role = payload.get("role", "")


class ServiceUser:
    """Service-to-service caller authenticated via X-Service-Key."""

    is_authenticated = True
    is_service = True
    role = "service"


class RequireServiceKeyAuthentication(BaseAuthentication):
    """Mandatory X-Service-Key for service-only endpoints (401 if missing)."""

    def authenticate(self, request):
        key = request.headers.get("X-Service-Key")
        if not key:
            raise NotAuthenticated("Missing X-Service-Key")
        expected = settings.SERVICE_API_KEY
        if not expected or key != expected:
            raise AuthenticationFailed("Invalid X-Service-Key")
        return ServiceUser(), key

    def authenticate_header(self, request):
        return "X-Service-Key"


class JWTAuthentication(BaseAuthentication):
    """Validate access tokens issued by the auth service."""

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

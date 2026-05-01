"""
Единый формат ошибок для всех endpoints (по канон-flow b2b-flows.md).
Формат: {"code": "...", "message": "..."}.
"""
from rest_framework.views import exception_handler
from rest_framework.exceptions import (
    NotFound, PermissionDenied, ValidationError,
    NotAuthenticated, AuthenticationFailed,
)
from rest_framework.exceptions import APIException


class NotOwner(APIException):
    status_code = 403
    default_detail = {"code": "NOT_OWNER", "message": "Resource does not belong to the authenticated seller"}
    default_code = "not_owner"


class HardBlockedForbidden(APIException):
    status_code = 403
    default_detail = {"code": "FORBIDDEN", "message": "Cannot edit hard-blocked product"}


class AlreadyDeleted(APIException):
    status_code = 400
    default_detail = {"code": "INVALID_REQUEST", "message": "Product already deleted"}

# Маппинг DRF-исключения -> code из канон-flow
_CODE_MAP = {
    NotFound: "NOT_FOUND",
    PermissionDenied: "FORBIDDEN",
    NotAuthenticated: "UNAUTHORIZED",
    AuthenticationFailed: "UNAUTHORIZED",
    ValidationError: "INVALID_REQUEST",
}


def _to_message(detail) -> str:
    """ValidationError приходит со словарём/списком — собираем читаемое сообщение."""
    if isinstance(detail, dict):
        # берём первое поле и его ошибку
        field, errs = next(iter(detail.items()))
        msg = errs[0] if isinstance(errs, list) else errs
        return f"{field}: {msg}"
    if isinstance(detail, list):
        return str(detail[0])
    return str(detail)


def canonical_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    # Уже наш формат — не трогаем (например, явный raise с {"code": ..., "message": ...})
    if isinstance(response.data, dict) and "code" in response.data and "message" in response.data:
        return response

    code = "INVALID_REQUEST"
    for exc_cls, c in _CODE_MAP.items():
        if isinstance(exc, exc_cls):
            code = c
            break

    response.data = {"code": code, "message": _to_message(response.data)}
    return response
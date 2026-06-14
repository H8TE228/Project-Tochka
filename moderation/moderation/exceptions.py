from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler


_CODE_MAP = {
    NotFound: "NOT_FOUND",
    PermissionDenied: "FORBIDDEN",
    NotAuthenticated: "UNAUTHORIZED",
    AuthenticationFailed: "UNAUTHORIZED",
    ValidationError: "INVALID_REQUEST",
}


def _to_message(detail) -> str:
    if isinstance(detail, dict):
        field, errors = next(iter(detail.items()))
        message = errors[0] if isinstance(errors, list) else errors
        return f"{field}: {message}"
    if isinstance(detail, list):
        return str(detail[0])
    return str(detail)


def canonical_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(response.data, dict) and "code" in response.data and "message" in response.data:
        return response

    code = "INVALID_REQUEST"
    for exc_cls, mapped_code in _CODE_MAP.items():
        if isinstance(exc, exc_cls):
            code = mapped_code
            break

    response.data = {"code": code, "message": _to_message(response.data)}
    return response

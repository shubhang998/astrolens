"""Map source/network failures into stable AstroLens connector errors."""

from __future__ import annotations

from socket import timeout as SocketTimeout
from typing import Any
from urllib.error import HTTPError, URLError

from astrolens.core.enums import ErrorCode
from astrolens.core.errors import AstroLensError

TIMEOUT_TYPES = (TimeoutError, SocketTimeout)


def connector_error_from_exception(
    exc: Exception,
    *,
    source: str,
    message: str,
    retryable: bool = True,
    details: dict[str, Any] | None = None,
) -> AstroLensError:
    """Classify a source exception without leaking raw stack traces."""

    error_details = {"source": source, **(details or {})}
    error_details["error_type"] = type(exc).__name__
    error_details["error"] = str(exc)

    if isinstance(exc, HTTPError):
        error_details["http_status"] = exc.code
        code, http_retryable = _http_error_code(exc.code)
        return AstroLensError(
            code,
            _message_for_code(source, message, code),
            retryable=http_retryable,
            details=error_details,
        )

    if _is_timeout_error(exc):
        return AstroLensError(
            ErrorCode.SOURCE_TIMEOUT,
            _message_for_code(source, message, ErrorCode.SOURCE_TIMEOUT),
            retryable=True,
            details=error_details,
        )

    return AstroLensError(
        ErrorCode.SOURCE_UNAVAILABLE,
        _message_for_code(source, message, ErrorCode.SOURCE_UNAVAILABLE),
        retryable=retryable,
        details=error_details,
    )


def _http_error_code(status_code: int) -> tuple[ErrorCode, bool]:
    if status_code == 429:
        return ErrorCode.RATE_LIMITED, True
    if status_code in {408, 504}:
        return ErrorCode.SOURCE_TIMEOUT, True
    if status_code in {401, 403}:
        return ErrorCode.PRODUCT_NOT_PUBLIC, False
    if status_code >= 500:
        return ErrorCode.SOURCE_UNAVAILABLE, True
    return ErrorCode.SOURCE_UNAVAILABLE, False


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TIMEOUT_TYPES):
        return True
    if isinstance(exc, URLError):
        reason = exc.reason
        if isinstance(reason, TIMEOUT_TYPES):
            return True
    return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()


def _message_for_code(source: str, message: str, code: ErrorCode) -> str:
    if code == ErrorCode.RATE_LIMITED:
        return f"{source} rate limited the archive request."
    if code == ErrorCode.SOURCE_TIMEOUT:
        return f"{source} did not respond before the timeout."
    if code == ErrorCode.PRODUCT_NOT_PUBLIC:
        return f"{source} rejected access to the requested public product metadata."
    return message

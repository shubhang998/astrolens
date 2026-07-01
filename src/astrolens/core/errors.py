"""Typed public error envelope and API exceptions."""

from typing import Any

from pydantic import Field

from astrolens.core.enums import ErrorCode
from astrolens.core.models import AstroLensModel


class APIErrorDetail(AstroLensModel):
    """Stable public error body."""

    code: ErrorCode
    message: str
    retryable: bool = False
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class APIError(AstroLensModel):
    """Stable error envelope returned by route exception handlers."""

    error: APIErrorDetail


class AstroLensError(Exception):
    """Base exception that can be mapped into an `APIError`."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)


class UnsupportedConnectorOperation(AstroLensError):
    """Raised when a connector does not implement a source operation."""

    def __init__(self, connector: str, operation: str) -> None:
        super().__init__(
            ErrorCode.UNSUPPORTED_CONNECTOR_OPERATION,
            f"{connector} does not support {operation}.",
            retryable=False,
            details={"connector": connector, "operation": operation},
        )

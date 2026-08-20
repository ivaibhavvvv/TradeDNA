from typing import Any, Optional
from fastapi import status


class TradeDNAException(Exception):
    """Base exception for all TradeDNA domain errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class BadRequestException(TradeDNAException):
    def __init__(self, message: str = "Bad request", code: str = "BAD_REQUEST", details: Optional[dict[str, Any]] = None):
        super().__init__(message=message, code=code, status_code=status.HTTP_400_BAD_REQUEST, details=details)


class UnauthorizedException(TradeDNAException):
    def __init__(self, message: str = "Authentication required", code: str = "UNAUTHORIZED"):
        super().__init__(message=message, code=code, status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenException(TradeDNAException):
    def __init__(self, message: str = "Access denied", code: str = "FORBIDDEN"):
        super().__init__(message=message, code=code, status_code=status.HTTP_403_FORBIDDEN)


class NotFoundException(TradeDNAException):
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(message=message, code=code, status_code=status.HTTP_404_NOT_FOUND)


class ValidationException(TradeDNAException):
    def __init__(self, message: str = "Invalid input payload", details: Optional[dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class ReconciliationDiscrepancyException(TradeDNAException):
    def __init__(self, message: str = "Balance reconciliation discrepancy detected", details: Optional[dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="RECONCILIATION_DISCREPANCY",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )

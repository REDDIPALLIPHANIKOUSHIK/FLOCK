"""Domain-specific exceptions for the Urja Meter Ops adapter layer."""

from typing import Optional


class PortalError(Exception):
    """Base exception for all portal adapter errors."""

    def __init__(self, message: str, status_code: int = 502, code: str = "PORTAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class PortalAuthenticationError(PortalError):
    """Raised when portal credentials fail or authentication handshake is rejected."""

    def __init__(self, message: str = "Failed to authenticate with upstream meter portal."):
        super().__init__(message, status_code=502, code="UPSTREAM_AUTH_FAILED")


class PortalSessionExpiredError(PortalError):
    """Raised when the active portal session has expired or is invalid."""

    def __init__(self, message: str = "Upstream portal session expired or invalid."):
        super().__init__(message, status_code=502, code="UPSTREAM_SESSION_EXPIRED")


class PortalNotFoundError(PortalError):
    """Raised when a meter or resource is not found in the portal."""

    def __init__(self, message: str = "The requested meter or resource was not found."):
        super().__init__(message, status_code=404, code="NOT_FOUND")


class PortalRateLimitError(PortalError):
    """Raised when the legacy portal responds with HTTP 429 Too Many Requests."""

    def __init__(
        self,
        message: str = "Upstream portal rate limit exceeded.",
        retry_after: Optional[int] = None
    ):
        super().__init__(message, status_code=429, code="UPSTREAM_RATE_LIMITED")
        self.retry_after = retry_after


class PortalTimeoutError(PortalError):
    """Raised when connection or read from upstream portal times out."""

    def __init__(self, message: str = "Upstream meter portal timed out."):
        super().__init__(message, status_code=504, code="UPSTREAM_TIMEOUT")


class PortalUpstreamError(PortalError):
    """Raised when upstream portal returns 5xx or unexpected network errors."""

    def __init__(self, message: str = "Upstream meter portal error.", status_code: int = 502):
        super().__init__(message, status_code=status_code, code="UPSTREAM_ERROR")


class PortalParseError(PortalError):
    """Raised when upstream HTML/JSON response cannot be parsed or normalized."""

    def __init__(self, message: str = "Failed to parse upstream portal response."):
        super().__init__(message, status_code=502, code="UPSTREAM_PARSE_ERROR")

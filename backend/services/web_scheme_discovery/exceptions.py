"""Exceptions for the web-scheme-discovery pipeline.

All exceptions are local to this package; they are caught at the service
and router boundary so the main FastAPI app never crashes because of
web discovery.
"""


class WebDiscoveryError(Exception):
    """Base error for web scheme discovery."""


class MissingApiKeyError(WebDiscoveryError):
    """Raised when TAVILY_API_KEY is not configured."""


class TavilyAPIError(WebDiscoveryError):
    """Raised for Tavily transport / HTTP / rate-limit / malformed errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ExtractionError(WebDiscoveryError):
    """Raised when search results cannot be converted to candidates."""


class ValidationError(WebDiscoveryError):
    """Raised for unexpected validator-internal failures (not rejections)."""

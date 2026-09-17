class CalleError(Exception):
    """Base exception for all CALL-E errors."""


class CalleAuthenticationError(CalleError):
    """Raised when the CALL-E API key is missing or invalid."""


class CalleValidationError(CalleError):
    """Raised when a request payload or phone number is invalid."""


class CalleAPIError(CalleError):
    """Raised when CALL-E returns a non-successful response."""

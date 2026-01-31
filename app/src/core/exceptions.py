"""Application exception classes."""


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""
    def __init__(self, resource: str = "Resource", id: str = ""):
        msg = f"{resource} not found" if not id else f"{resource} {id} not found"
        super().__init__(msg)


class PermissionError(Exception):
    """Raised when a user lacks required permissions."""
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message)


class ValidationError(Exception):
    """Raised for business logic validation failures."""
    pass


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""
    pass

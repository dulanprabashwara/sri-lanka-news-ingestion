class BackendClientError(RuntimeError):
    """Base error for expected internal backend submission failures."""


class BackendUnavailableError(BackendClientError):
    """Raised when the backend cannot be reached within the timeout."""


class BackendAuthenticationError(BackendClientError):
    """Raised when the backend rejects the shared ingestion secret."""


class BackendValidationError(BackendClientError):
    """Raised when the backend rejects a normalized article payload."""


class BackendServiceError(BackendClientError):
    """Raised for backend failures that are not validation or authentication."""


class BackendProtocolError(BackendClientError):
    """Raised when the backend response does not match the internal contract."""

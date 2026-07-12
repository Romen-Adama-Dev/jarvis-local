class JarvisError(Exception):
    code: str = "internal_error"
    status_code: int = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(JarvisError):
    code = "not_found"
    status_code = 404


class ValidationFailedError(JarvisError):
    code = "validation_failed"
    status_code = 422


class UnauthorizedError(JarvisError):
    code = "unauthorized"
    status_code = 401


class ForbiddenError(JarvisError):
    code = "forbidden"
    status_code = 403


class ConflictError(JarvisError):
    code = "conflict"
    status_code = 409


class InsufficientEvidenceError(JarvisError):
    code = "insufficient_evidence"
    status_code = 200


class ProviderUnavailableError(JarvisError):
    code = "provider_unavailable"
    status_code = 503


class RateLimitedError(JarvisError):
    code = "rate_limited"
    status_code = 429

"""Centralized exceptions and error models for CRYVEX ShopFlow Voice AI."""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class VoiceAIException(Exception):
    """Base exception for all Voice AI domain errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


class AuthenticationError(VoiceAIException):
    """Raised when authentication credentials are missing, invalid, or untrusted."""

    def __init__(self, message: str = "Invalid service authentication credentials"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            retryable=False,
        )


class TenantContextError(VoiceAIException):
    """Raised when tenant context is missing, invalid, or cross-tenant violation occurs."""

    def __init__(self, message: str = "Invalid or unverified tenant context"):
        super().__init__(
            message=message,
            error_code="TENANT_CONTEXT_INVALID",
            status_code=status.HTTP_403_FORBIDDEN,
            retryable=False,
        )


class InvalidAudioError(VoiceAIException):
    """Raised when audio format is unsupported, corrupted, or invalid."""

    def __init__(self, message: str = "Unsupported or malformed audio format"):
        super().__init__(
            message=message,
            error_code="INVALID_AUDIO_FORMAT",
            status_code=status.HTTP_400_BAD_REQUEST,
            retryable=False,
        )


class AudioPayloadTooLargeError(VoiceAIException):
    """Raised when uploaded audio exceeds configured size or duration limit."""

    def __init__(self, message: str = "Audio payload exceeds maximum permissible size or duration"):
        super().__init__(
            message=message,
            error_code="AUDIO_TOO_LARGE",
            status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
            retryable=False,
        )


class ModelNotReadyError(VoiceAIException):
    """Raised when speech model is still loading or currently uninitialized (Cold-start)."""

    def __init__(self, message: str = "Speech recognition model is loading or not yet ready"):
        super().__init__(
            message=message,
            error_code="MODEL_NOT_READY",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
            details={"retry_after_seconds": 3},
        )


class ModelInferenceError(VoiceAIException):
    """Raised when model inference fails during processing."""

    def __init__(self, message: str = "Speech recognition inference failed"):
        super().__init__(
            message=message,
            error_code="INFERENCE_FAILED",
            status_code=status.HTTP_502_BAD_GATEWAY,
            retryable=True,
        )


class CatalogueServiceUnavailableError(VoiceAIException):
    """Raised when internal ShopFlow catalogue service is unreachable or down."""

    def __init__(self, message: str = "ShopFlow catalogue service unavailable"):
        super().__init__(
            message=message,
            error_code="CATALOGUE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retryable=True,
            details={"retry_after_seconds": 2},
        )


class CatalogueTimeoutError(VoiceAIException):
    """Raised when catalogue lookup times out."""

    def __init__(self, message: str = "ShopFlow catalogue lookup timed out"):
        super().__init__(
            message=message,
            error_code="CATALOGUE_TIMEOUT",
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            retryable=True,
        )


class DuplicateRequestError(VoiceAIException):
    """Raised when an identical request is being processed or was processed under idempotency key."""

    def __init__(self, message: str = "Duplicate request detected"):
        super().__init__(
            message=message,
            error_code="DUPLICATE_REQUEST",
            status_code=status.HTTP_409_CONFLICT,
            retryable=False,
        )


class AmbiguousInterpretationError(VoiceAIException):
    """Raised when voice input has multiple conflicting product or quantity matches."""

    def __init__(self, message: str = "Voice interpretation is ambiguous and requires clarification", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code="AMBIGUOUS_INTERPRETATION",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            retryable=False,
            details=details,
        )

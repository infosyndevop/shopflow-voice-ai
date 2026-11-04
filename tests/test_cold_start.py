"""Tests for Reliability, Cold-Start, Resilience, Authentication, and Idempotency."""

import base64
import pytest
from app.core.config import settings
from app.core.errors import (
    AudioPayloadTooLargeError,
    AuthenticationError,
    CatalogueServiceUnavailableError,
    CatalogueTimeoutError,
    InvalidAudioError,
    ModelNotReadyError,
    TenantContextError,
)
from app.schemas.voice_schemas import (
    AudioTranscribeRequest,
    InterpretationRequest,
    ModelLifecycleState,
)
from app.security.service_auth import (
    get_tenant_context,
    sanitize_tenant_id,
    verify_service_credentials,
)
from app.services.catalogue.mock_catalogue import MockCatalogueProvider
from app.services.voice.conversation_engine import ConversationEngine
from app.services.voice.speech_recognition import (
    MockSpeechRecognitionProvider,
    SpeechModelManager,
)
from tests.conftest import run_async


def test_cold_start_model_not_ready_raises_503():
    async def _test():
        provider = MockSpeechRecognitionProvider()
        # Initial state before warmup
        assert provider.state == ModelLifecycleState.NOT_INITIALIZED
        with pytest.raises(ModelNotReadyError) as exc_info:
            await provider.transcribe(b"dummy audio")
        assert exc_info.value.status_code == 503
        assert exc_info.value.retryable is True
    run_async(_test())


def test_model_initialization_failure_handling():
    async def _test():
        failing_provider = MockSpeechRecognitionProvider(simulate_failure=True)
        await failing_provider.initialize()
        assert failing_provider.state == ModelLifecycleState.FAILED
        status = failing_provider.get_status()
        assert status.is_ready is False
        assert status.state == ModelLifecycleState.FAILED
    run_async(_test())


def test_catalogue_timeout_handling():
    async def _test():
        timeout_catalogue = MockCatalogueProvider(simulate_timeout=True)
        with pytest.raises(CatalogueTimeoutError) as exc_info:
            await timeout_catalogue.get_tenant_products("tenant_default")
        assert exc_info.value.status_code == 504
        assert exc_info.value.retryable is True
    run_async(_test())


def test_catalogue_offline_service_unavailable():
    async def _test():
        offline_catalogue = MockCatalogueProvider(simulate_offline=True)
        with pytest.raises(CatalogueServiceUnavailableError) as exc_info:
            await offline_catalogue.get_tenant_products("tenant_default")
        assert exc_info.value.status_code == 503
        assert exc_info.value.retryable is True
    run_async(_test())


def test_duplicate_request_idempotency_caching():
    engine = ConversationEngine()
    tenant_id = "tenant_default"
    idempotency_key = "idemp-req-unique-9988"

    assert engine.get_cached_idempotent_response(tenant_id, idempotency_key) is None

    from app.schemas.voice_schemas import InterpretationResponse, InterpretationStatus
    mock_resp = InterpretationResponse(
        status=InterpretationStatus.VERIFIED,
        transcript="two soaps",
        normalized_transcript="two soaps",
        items=[],
        unmatched_phrases=[],
        clarification_required=False,
    )
    engine.store_idempotent_response(tenant_id, idempotency_key, mock_resp)

    # Retry with same idempotency key returns cached response
    cached = engine.get_cached_idempotent_response(tenant_id, idempotency_key)
    assert cached is not None
    assert cached.transcript == "two soaps"


def test_invalid_service_credentials_rejected():
    with pytest.raises(AuthenticationError):
        verify_service_credentials(service_key="invalid-untrusted-key", authorization=None)

    with pytest.raises(AuthenticationError):
        verify_service_credentials(service_key=None, authorization=None)


def test_valid_service_credentials_accepted():
    assert verify_service_credentials(service_key=settings.SERVICE_API_KEY) is True
    assert verify_service_credentials(authorization=f"Bearer {settings.SERVICE_API_KEY}") is True


def test_tenant_id_sanitization_and_validation():
    # Valid tenant
    assert sanitize_tenant_id("tenant_123") == "tenant_123"
    assert sanitize_tenant_id("shop-north-01") == "shop-north-01"

    # Missing or empty
    with pytest.raises(TenantContextError):
        sanitize_tenant_id(None)
    with pytest.raises(TenantContextError):
        sanitize_tenant_id("   ")

    # Path traversal or SQL injection attempt
    with pytest.raises(TenantContextError):
        sanitize_tenant_id("../etc/passwd")
    with pytest.raises(TenantContextError):
        sanitize_tenant_id("tenant'; DROP TABLE--")


def test_oversized_audio_payload_rejected():
    async def _test():
        provider = MockSpeechRecognitionProvider()
        await provider.initialize()
        # Generate payload exceeding MAX_AUDIO_SIZE_BYTES
        huge_audio = b"0" * (settings.MAX_AUDIO_SIZE_BYTES + 1024)
        with pytest.raises(AudioPayloadTooLargeError) as exc_info:
            await provider.transcribe(huge_audio)
        assert exc_info.value.status_code == 413
    run_async(_test())


def test_empty_audio_payload_rejected():
    async def _test():
        provider = MockSpeechRecognitionProvider()
        await provider.initialize()
        with pytest.raises(InvalidAudioError) as exc_info:
            await provider.transcribe(b"")
        assert exc_info.value.status_code == 400
    run_async(_test())


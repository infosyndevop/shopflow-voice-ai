"""End-to-end API route tests verifying voice transcription and retail interpretation."""

import base64
import pytest
from app.api.health import health_diagnostics, health_live, health_model, health_ready
from app.api.voice import interpret_voice, transcribe_audio
from app.schemas.voice_schemas import (
    AudioTranscribeRequest,
    InterpretationRequest,
    InterpretationStatus,
    ItemStatus,
)
from app.security.service_auth import TenantSecurityContext
from app.services.voice.speech_recognition import model_manager
from tests.conftest import run_async


def test_health_live_endpoint():
    res = run_async(health_live())
    assert res.status == "alive"
    assert res.timestamp is not None


def test_health_ready_and_model_lifecycle():
    # 1. Warm up model
    run_async(model_manager.startup())

    class DummyResponse:
        status_code = 200

    resp = DummyResponse()
    res = run_async(health_ready(resp))
    assert res.status == "ready"
    assert res.model_ready is True
    assert res.catalogue_provider_ready is True

    model_res = run_async(health_model())
    assert model_res.is_ready is True
    assert model_res.worker_concurrency == 1


def test_health_diagnostics_endpoint():
    res = run_async(health_diagnostics())
    assert res.status == "healthy"
    assert res.uptime_seconds >= 0


def test_api_interpret_multi_variant_requires_clarification():
    async def _test():
        # "two urvashi soap" -> Urvashi soap has 100g and 150g variants.
        # Since variant is not specified, it must return needs_clarification.
        ctx = TenantSecurityContext(tenant_id="tenant_default", is_authenticated=True, request_id="req-1")
        req = InterpretationRequest(transcript="two urvashi soap")
        res = await interpret_voice(payload=req, security_ctx=ctx)

        assert res.status == InterpretationStatus.NEEDS_CLARIFICATION
        assert res.clarification_required is True
        assert len(res.items) == 1
        assert res.items[0].product_name == "Urvashi Soap"
        assert res.items[0].quantity == 2.0
        assert res.items[0].status == ItemStatus.NEEDS_CLARIFICATION
    run_async(_test())


def test_api_interpret_exact_variant_and_quantity_verified():
    async def _test():
        # "Three packets of 160 gram washing soap" -> exact product, exact variant 160g, exact quantity 3 packets
        ctx = TenantSecurityContext(tenant_id="tenant_default", is_authenticated=True, request_id="req-2")
        req = InterpretationRequest(transcript="Three packets of 160 gram washing soap")
        res = await interpret_voice(payload=req, security_ctx=ctx)

        assert res.status == InterpretationStatus.VERIFIED
        assert res.clarification_required is False
        assert len(res.items) == 1
        item = res.items[0]
        assert item.product_name == "Washing Soap"
        assert item.variant_name == "160g"
        assert item.package_size == "160g"
        assert item.quantity == 3.0
        assert item.unit == "packet"
        assert item.status == ItemStatus.VERIFIED
    run_async(_test())


def test_api_interpret_price_reference_not_confused_with_quantity():
    async def _test():
        # "Ten rupees egg biscuit"
        ctx = TenantSecurityContext(tenant_id="tenant_default", is_authenticated=True, request_id="req-3")
        req = InterpretationRequest(transcript="Ten rupees egg biscuit")
        res = await interpret_voice(payload=req, security_ctx=ctx)

        assert len(res.items) == 1
        item = res.items[0]
        assert item.product_name == "Egg Biscuit"
        assert item.price_reference == 10.0
        assert item.quantity is None  # 10 is NOT quantity!
    run_async(_test())


def test_api_transcribe_audio_endpoint():
    async def _test():
        run_async(model_manager.startup())
        ctx = TenantSecurityContext(tenant_id="tenant_default", is_authenticated=True, request_id="req-4")
        audio_b64 = base64.b64encode(b"two urvashi soap").decode("utf-8")
        req = AudioTranscribeRequest(audio_base64=audio_b64, mime_type="audio/wav")
        res = await transcribe_audio(payload=req, security_ctx=ctx)

        assert res.status == "success"
        assert "urvashi soap" in res.transcript
        assert res.confidence > 0.90
    run_async(_test())

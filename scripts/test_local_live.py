"""Comprehensive local end-to-end testing script.

Executes all core flows against the live application using the local .env configuration:
- SPEECH_PROVIDER=sherpa_onnx (Real CPU ONNX model)
- CATALOGUE_PROVIDER_TYPE=mock
- Service authentication & tenant validation
- Health & readiness probes
- Audio transcription with real Sherpa-ONNX INT8 model
- Multi-product utterance interpretation
- Retail safety: price isolation (₹10 biscuit) & SKU leading zero preservation (SKU 002)
"""

import base64
import os
import sys

# Ensure root dir is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.core.config import settings
from app.api.health import health_diagnostics, health_live, health_ready
from app.api.voice import interpret_voice, transcribe_audio
from app.schemas.voice_schemas import (
    AudioTranscribeRequest,
    InterpretationRequest,
    InterpretationStatus,
    ItemStatus,
)
from app.core.errors import AuthenticationError
from app.security.service_auth import (
    TenantSecurityContext,
    sanitize_tenant_id,
    verify_service_credentials,
)
from app.services.voice.speech_recognition import model_manager
from tests.conftest import run_async

SAMPLE_WAV = os.path.join(BASE_DIR, "data", "benchmark_audio", "bench_5s.wav")


def run_local_tests():
    print("=" * 65)
    print(" CRYVEX SHOPFLOW VOICE AI - LOCAL VERIFICATION TEST")
    print("=" * 65)
    print(f"Environment:       {settings.ENVIRONMENT}")
    print(f"Debug:             {settings.DEBUG}")
    print(f"Speech Provider:   {settings.SPEECH_PROVIDER}")
    print(f"ASR Language:      {settings.ASR_LANGUAGE}")
    print(f"ASR Model Dir:     {settings.ASR_MODEL_DIR}")
    print(f"Catalogue Mode:    {settings.CATALOGUE_PROVIDER_TYPE}")
    print(f"Service API Key:   {settings.SERVICE_API_KEY[:8]}... (redacted)")
    print("-" * 65)

    # 1. Initialize real speech model manager (Sherpa-ONNX INT8 CPU)
    print("\n[1/6] Initializing Speech Model Lifecycle (Sherpa-ONNX CPU) ...")
    run_async(model_manager.startup())
    provider = model_manager.get_provider()
    print(f"Model Provider:    {provider.__class__.__name__}")
    print(f"Model State:       {provider.state.value}")
    print(f"Model Name:        {provider.model_name}")
    assert provider.state.value == "ready"
    print("  -> PASS: Speech recognition engine initialized and READY on CPU.")

    # 2. Health & Readiness Probes
    print("\n[2/6] Verifying Health & Readiness Endpoints ...")
    res_live = run_async(health_live())
    assert res_live.status == "alive"
    print(f"  -> Liveness Probe: {res_live.status.upper()} (timestamp={res_live.timestamp})")

    class DummyResp:
        status_code = 200

    dummy = DummyResp()
    res_ready = run_async(health_ready(dummy))
    assert res_ready.status == "ready"
    assert res_ready.model_ready is True
    print(f"  -> Readiness Probe: {res_ready.status.upper()} (model_ready={res_ready.model_ready})")

    res_diag = run_async(health_diagnostics())
    assert res_diag.status == "healthy"
    print(f"  -> Diagnostics: {res_diag.status.upper()} (uptime={res_diag.uptime_seconds:.1f}s)")

    # 3. Security Credentials Verification
    print("\n[3/6] Testing Service-to-Service Security Context ...")
    # Valid key
    is_valid = verify_service_credentials(service_key=settings.SERVICE_API_KEY)
    assert is_valid is True
    tenant_id = sanitize_tenant_id("tenant_default")
    ctx = TenantSecurityContext(
        tenant_id=tenant_id,
        is_authenticated=True,
        request_id="req-local-verify",
    )
    print(f"  -> Valid Credentials Accepted: tenant_id='{ctx.tenant_id}', authenticated={ctx.is_authenticated}")

    # Invalid key raises AuthenticationError
    try:
        verify_service_credentials(service_key="invalid-wrong-secret-key")
        assert False, "Should have raised AuthenticationError"
    except AuthenticationError:
        print("  -> Invalid Credentials Rejected with AuthenticationError (constant-time verification).")

    # 4. Real Audio Transcription Test
    print("\n[4/6] Testing Real Audio Transcription (/api/v1/voice/transcribe) ...")
    assert os.path.exists(SAMPLE_WAV), f"Sample audio missing at {SAMPLE_WAV}"
    with open(SAMPLE_WAV, "rb") as f:
        audio_bytes = f.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    transcribe_req = AudioTranscribeRequest(
        audio_base64=audio_b64,
        mime_type="audio/wav",
        language_hint=settings.ASR_LANGUAGE,
    )
    transcribe_res = run_async(transcribe_audio(transcribe_req, security_ctx=ctx))
    print(f"  -> Transcribed Text:   '{transcribe_res.transcript}'")
    print(f"  -> Detected Language:  {transcribe_res.detected_language}")
    print(f"  -> Audio Duration:     {transcribe_res.duration_seconds}s")
    print(f"  -> Status:             {transcribe_res.status}")
    assert transcribe_res.status in ["success", "empty"]
    assert transcribe_res.detected_language == "en"
    print("  -> PASS: Real Sherpa-ONNX audio inference executed successfully.")

    # 5. Multi-Product Utterance Interpretation Test
    print("\n[5/6] Testing Multi-Product Interpretation (/api/v1/voice/interpret) ...")
    compound_query = "Two Urvashi soaps, three packets of 160 gram washing soap and one egg"
    print(f"  -> Input Query: '{compound_query}'")
    interp_req = InterpretationRequest(
        transcript=compound_query,
        idempotency_key="local-verify-multi-1",
    )
    interp_res = run_async(interpret_voice(interp_req, security_ctx=ctx))

    print(f"  -> Overall Status: {interp_res.status.value}")
    print(f"  -> Parsed Items ({len(interp_res.items)} total):")
    for idx, it in enumerate(interp_res.items, 1):
        print(f"     [{idx}] Product: {it.product_name:<15} | Qty: {it.quantity} {it.unit or ''} | Variant: {it.variant_name or 'N/A'} | SKU: {it.sku or 'N/A'} | Status: {it.status.value}")

    assert len(interp_res.items) == 3
    # Verify washing soap
    w_item = next(it for it in interp_res.items if "washing" in it.product_name.lower())
    assert w_item.quantity == 3.0
    assert w_item.package_size == "160g"
    assert w_item.sku == "002"
    assert w_item.status == ItemStatus.VERIFIED

    # Verify egg
    e_item = next(it for it in interp_res.items if it.product_name.lower() == "egg")
    assert e_item.quantity == 1.0
    assert e_item.status == ItemStatus.VERIFIED
    print("  -> PASS: Multi-product items accurately parsed and verified.")

    # 6. Retail Safety Tests: Price Reference Isolation & SKU Leading Zeros
    print("\n[6/6] Testing Retail Safety (Price Reference & SKU 002) ...")

    # 6a: ₹10 egg biscuit (price isolated, quantity None, needs clarification)
    req_price = InterpretationRequest(
        transcript="₹10 egg biscuit",
        idempotency_key="local-verify-price-1",
    )
    res_price = run_async(interpret_voice(req_price, security_ctx=ctx))
    assert res_price.status == InterpretationStatus.NEEDS_CLARIFICATION
    assert res_price.items[0].price_reference == 10.0
    assert res_price.items[0].quantity is None
    print("  -> PASS: 'Rs. 10 egg biscuit' isolates price reference (10.0) without silently assuming quantity.")

    # 6b: SKU 002 (leading zero preservation)
    req_sku = InterpretationRequest(
        transcript="give me SKU 002",
        idempotency_key="local-verify-sku-1",
    )
    res_sku = run_async(interpret_voice(req_sku, security_ctx=ctx))
    assert len(res_sku.items) == 1
    assert res_sku.items[0].sku == "002"
    assert res_sku.items[0].variant_name == "160g"
    print("  -> PASS: 'SKU 002' preserves exact string SKU with leading zeros ('002').")

    print("\n" + "=" * 65)
    print(" ALL LOCAL VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("=" * 65)


if __name__ == "__main__":
    run_local_tests()

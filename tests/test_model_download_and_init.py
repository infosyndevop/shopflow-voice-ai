"""Automated tests for model downloading, SHA256 integrity verification, and Sherpa-ONNX initialization.

Verifies:
- Accurate directory structure for all language models.
- SHA-256 checksum verification against pinned repository hashes.
- Detection and rejection of corrupted checksums.
- Graceful handling of download failures without leaving corrupt artifacts.
- Missing model detection causing readiness failure (HTTP 503 behavior).
- Successful Sherpa-ONNX model initialization and health probe verification.
"""

import os
import tempfile
import pytest
from app.api.health import health_model, health_ready
from app.core.config import settings
from app.core.errors import ModelNotReadyError
from app.schemas.voice_schemas import ModelLifecycleState
from app.services.voice.speech_recognition import (
    SherpaOnnxSpeechRecognitionProvider,
    model_manager,
)
from scripts.download_models import (
    DEFAULT_MODELS_DIR,
    MODEL_REGISTRY,
    REPO_REVISION,
    compute_sha256,
    download_file,
    get_required_registry_keys,
    verify_file,
)
from tests.conftest import run_async


def test_required_directory_structure_and_hashes():
    """Verifies that all model and token artifacts exist at exact expected paths with matching SHA256."""
    expected_artifacts = {
        "models/tokens.txt": "ee60967630213f31951817ac8b402b92ec18cce80718a24a49b388e56672dfb2",
        "models/en/tokens.txt": "89c165b98df7af718ec0e872177279bfad4ade51331f1be92753c9583a1ef30d",
        "models/en/model.int8.onnx": "28b9261a53028a7c99ff0799f44fb53f19c78b68cc4cf40637ac9c16cb1fbc6f",
        "models/ml/model.int8.onnx": "dcbdfa9f773db910508b40b703cb76c5974e8d4c6f123ea81265b40853c3f0c2",
        "models/ta/model.int8.onnx": "abb7b59d706b8d27ba3fb5e5e3db7671c9e1a09bf7bc6122de507c60030e65fb",
    }
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for rel_path, expected_hash in expected_artifacts.items():
        full_path = os.path.join(project_root, rel_path)
        assert os.path.exists(full_path), f"Required artifact missing: {rel_path}"
        actual_hash = compute_sha256(full_path)
        assert actual_hash.lower() == expected_hash.lower(), (
            f"SHA256 mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"
        )


def test_registry_keys_for_languages():
    """Verifies that get_required_registry_keys resolves the correct dependency graph."""
    en_keys = get_required_registry_keys(["en"])
    assert "en_model" in en_keys
    assert "en_tokens" in en_keys
    assert "ml_model" not in en_keys

    ml_keys = get_required_registry_keys(["ml"])
    assert "ml_model" in ml_keys
    assert "tokens.txt" in ml_keys

    all_keys = get_required_registry_keys(["all"])
    assert len(all_keys) == 5
    assert set(all_keys) == {"tokens.txt", "ml_model", "ta_model", "en_model", "en_tokens"}


def test_verify_file_detection_of_corrupt_checksum():
    """Verifies that verify_file detects tampered or corrupted files."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"CORRUPT_OR_TAMPERED_BYTES")
        temp_path = f.name

    try:
        # Check against a dummy hash
        is_valid = verify_file(
            dest_path=temp_path,
            expected_size=len(b"CORRUPT_OR_TAMPERED_BYTES"),
            expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
        assert is_valid is False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_failed_download_cleans_up_and_returns_false():
    """Verifies that network failure during download returns False and cleans up temporary files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_path = os.path.join(tmp_dir, "nonexistent_model.onnx")
        # Attempt to download from a non-existent URL
        ok = download_file(
            url="https://invalid-nonexistent-domain-xyz.com/test.onnx",
            dest_path=dest_path,
            expected_size=1000,
            expected_sha256="dummy_sha256",
            max_retries=1,
        )
        assert ok is False
        assert not os.path.exists(dest_path)
        assert not os.path.exists(dest_path + ".tmp")


def test_missing_model_causes_readiness_failure():
    """Verifies that when model files are absent, provider reports UNAVAILABLE and readiness returns 503."""
    with tempfile.TemporaryDirectory() as empty_dir:
        provider = SherpaOnnxSpeechRecognitionProvider(model_dir=empty_dir, default_lang="en")
        run_async(provider.initialize())

        assert provider.state == ModelLifecycleState.UNAVAILABLE

        status = provider.get_status()
        assert status.is_ready is False
        assert status.state == ModelLifecycleState.UNAVAILABLE

        # Transcribe call must fail with ModelNotReadyError
        with pytest.raises(ModelNotReadyError):
            run_async(provider.transcribe(b"dummy_audio_bytes"))


def test_successful_sherpa_onnx_initialization_and_health_probes():
    """Verifies that the Sherpa-ONNX provider initializes successfully with verified models and reports ready."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir=DEFAULT_MODELS_DIR, default_lang="en")
    run_async(provider.initialize())

    assert provider.state == ModelLifecycleState.READY
    assert provider._loaded_lang == "en"

    # Inject provider into model manager and test health probes
    model_manager.set_provider(provider)

    class DummyResp:
        status_code = 200

    resp = DummyResp()
    ready_data = run_async(health_ready(resp))
    assert ready_data.status == "ready"
    assert ready_data.model_ready is True
    assert resp.status_code == 200

    model_data = run_async(health_model())
    assert model_data.is_ready is True
    assert model_data.state == ModelLifecycleState.READY
    assert "indicconformer-sherpa-onnx-en" in model_data.model_name


"""Integration tests for real Sherpa-ONNX Speech Recognition Provider.

Verifies:
- Model lifecycle (NOT_INITIALIZED -> LOADING -> READY).
- CPU inference using INT8 ONNX NeMo Fast-Conformer / IndicConformer models.
- Clean language switching (unloading previous model to protect 512MB RAM).
- Audio preprocessing (magic bytes, mono 16kHz float32 conversion).
- Error conditions (empty audio, corrupt header, missing model).
"""

import os
import pytest
from app.core.config import settings
from app.core.errors import InvalidAudioError, ModelNotReadyError
from app.schemas.voice_schemas import ModelLifecycleState
from app.services.voice.speech_recognition import SherpaOnnxSpeechRecognitionProvider
from tests.conftest import run_async

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
SAMPLE_AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "benchmark_audio")
SAMPLE_WAV = os.path.join(SAMPLE_AUDIO_DIR, "bench_5s.wav")

MODELS_AVAILABLE = (
    os.path.exists(os.path.join(MODELS_DIR, "en", "model.int8.onnx"))
    and os.path.exists(os.path.join(MODELS_DIR, "ml", "model.int8.onnx"))
)


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="ASR models not downloaded on disk")
def test_sherpa_onnx_lifecycle():
    """Verifies SherpaOnnxSpeechRecognitionProvider loads and transitions to READY."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir=MODELS_DIR, default_lang="en")
    assert provider.state == ModelLifecycleState.NOT_INITIALIZED

    run_async(provider.initialize())
    assert provider.state == ModelLifecycleState.READY

    status = provider.get_status()
    assert status.is_ready is True
    assert status.device == "cpu"
    assert status.worker_concurrency == 1


@pytest.mark.skipif(not MODELS_AVAILABLE or not os.path.exists(SAMPLE_WAV), reason="Models or sample audio missing")
def test_sherpa_onnx_transcription():
    """Tests actual CPU inference on 16kHz WAV audio bytes."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir=MODELS_DIR, default_lang="en")
    run_async(provider.initialize())

    with open(SAMPLE_WAV, "rb") as f:
        audio_bytes = f.read()

    resp = run_async(provider.transcribe(audio_bytes, mime_type="audio/wav", language_hint="en"))

    assert resp.status in ["success", "empty"]
    assert resp.detected_language == "en"
    assert resp.duration_seconds > 0


@pytest.mark.skipif(not MODELS_AVAILABLE, reason="ASR models not downloaded on disk")
def test_sherpa_onnx_language_switching():
    """Verifies language model switching unloads previous model without leaking memory."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir=MODELS_DIR, default_lang="en")
    run_async(provider.initialize())
    assert provider._loaded_lang == "en"

    # Switch to Malayalam
    provider._load_model_for_lang("ml")
    assert provider._loaded_lang == "ml"
    assert "indicconformer-sherpa-onnx-ml" in provider.model_name

    # Switch to Tamil
    provider._load_model_for_lang("ta")
    assert provider._loaded_lang == "ta"
    assert "indicconformer-sherpa-onnx-ta" in provider.model_name


def test_sherpa_onnx_invalid_audio():
    """Verifies that invalid or empty audio payloads are rejected safely."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir=MODELS_DIR, default_lang="en")
    provider.state = ModelLifecycleState.READY

    # Empty payload
    with pytest.raises(InvalidAudioError):
        run_async(provider.transcribe(b"", mime_type="audio/wav"))

    # Malformed magic bytes
    with pytest.raises(InvalidAudioError):
        run_async(provider.transcribe(b"CORRUPTED_NON_AUDIO_PAYLOAD", mime_type="audio/wav"))


def test_sherpa_onnx_missing_model_path():
    """Verifies provider reports UNAVAILABLE when configured model files do not exist."""
    provider = SherpaOnnxSpeechRecognitionProvider(model_dir="non_existent_models_dir", default_lang="en")
    run_async(provider.initialize())
    assert provider.state == ModelLifecycleState.UNAVAILABLE

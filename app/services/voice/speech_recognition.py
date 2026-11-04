"""Speech Recognition Provider Interface, Lifecycle Manager, and Cold-Start Handler.

Supports:
- Lifecycle states: NOT_INITIALIZED, LOADING, READY, FAILED, UNAVAILABLE
- Single inference worker concurrency to respect Render Free RAM limits
- Model loaded once at startup, never per request
- Cold-start protection: returns 503 ModelNotReadyError when initializing
"""

import asyncio
import base64
import gc
import os
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import numpy as np

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

from app.core.config import settings
from app.core.errors import (
    AudioPayloadTooLargeError,
    InvalidAudioError,
    ModelInferenceError,
    ModelNotReadyError,
)
from app.core.logging import logger
from app.schemas.voice_schemas import (
    AudioTranscribeResponse,
    ModelLifecycleState,
    ModelStatusResponse,
)
from app.services.voice.audio_preprocessor import preprocess_audio


class SpeechRecognitionProvider(ABC):
    """Abstract speech recognition provider interface."""

    def __init__(self):
        self.state: ModelLifecycleState = ModelLifecycleState.NOT_INITIALIZED
        self.device: str = "cpu"
        self.model_name: str = settings.SPEECH_MODEL_NAME

    @abstractmethod
    async def initialize(self) -> None:
        """Loads and warms up the model once during application startup."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        language_hint: Optional[str] = "mixed",
    ) -> AudioTranscribeResponse:
        """Performs transcription on sanitized audio bytes."""
        pass

    def get_status(self) -> ModelStatusResponse:
        """Returns safe model lifecycle diagnostics."""
        return ModelStatusResponse(
            model_name=self.model_name,
            state=self.state,
            device=self.device,
            is_ready=self.state == ModelLifecycleState.READY,
            worker_concurrency=1,
        )


class MockSpeechRecognitionProvider(SpeechRecognitionProvider):
    """Lightweight test provider capable of simulating cold-start delays, readiness, and errors."""

    def __init__(self, simulate_failure: bool = False, simulated_transcript: Optional[str] = None):
        super().__init__()
        self.simulate_failure = simulate_failure
        self.simulated_transcript = simulated_transcript
        self._mock_text = simulated_transcript or "three packets of 160 gram washing soap"

    async def initialize(self) -> None:
        """Simulates model loading lifecycle."""
        self.state = ModelLifecycleState.LOADING
        if self.simulate_failure:
            self.state = ModelLifecycleState.FAILED
            logger.error("Mock speech model initialization failed as requested")
            return
        self.state = ModelLifecycleState.READY
        logger.info(f"Mock speech model '{self.model_name}' successfully initialized and ready")

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        language_hint: Optional[str] = "mixed",
    ) -> AudioTranscribeResponse:
        """Processes mock audio payload."""
        if self.state != ModelLifecycleState.READY:
            raise ModelNotReadyError(f"Speech recognition service is in '{self.state.value}' state")

        if not audio_bytes:
            raise InvalidAudioError("Received empty audio stream")

        if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
            raise AudioPayloadTooLargeError(
                f"Audio payload size ({len(audio_bytes)} bytes) exceeds limit ({settings.MAX_AUDIO_SIZE_BYTES} bytes)"
            )

        # In mock mode, if audio_bytes is text-encoded or contains a specific test string, use it
        try:
            decoded = audio_bytes.decode("utf-8", errors="ignore").strip()
            if decoded and len(decoded) < 200 and not any(ord(c) < 32 for c in decoded):
                text_to_return = decoded
            else:
                text_to_return = self._mock_text
        except Exception:
            text_to_return = self._mock_text

        return AudioTranscribeResponse(
            transcript=text_to_return,
            detected_language=language_hint or "mixed",
            confidence=0.96,
            duration_seconds=2.5,
            status="success"
        )


class SherpaOnnxSpeechRecognitionProvider(SpeechRecognitionProvider):
    """Production CPU speech recognition provider using quantized ONNX IndicConformer/Fast-Conformer models.

    Strict memory constraints:
    - Never loads multiple language models simultaneously into RAM.
    - Explicitly unloads previous model and triggers garbage collection on language switch.
    - Single inference worker concurrency.
    """

    def __init__(self, model_dir: Optional[str] = None, default_lang: Optional[str] = None):
        super().__init__()
        self.model_dir = model_dir or settings.ASR_MODEL_DIR
        self.current_lang = (default_lang or settings.ASR_LANGUAGE).lower()
        self.num_threads = settings.ASR_NUM_THREADS
        self.device = "cpu"
        self.model_name = f"indicconformer-sherpa-onnx-{self.current_lang}"
        self._recognizer = None
        self._loaded_lang: Optional[str] = None

    def _resolve_model_paths(self, lang: str) -> Tuple[str, str]:
        """Maps language code to exact model and tokens files."""
        if lang == "en":
            model_path = os.path.join(self.model_dir, "en", "model.int8.onnx")
            tokens_path = os.path.join(self.model_dir, "en", "tokens.txt")
        elif lang in ["ml", "ta"]:
            model_path = os.path.join(self.model_dir, lang, "model.int8.onnx")
            tokens_path = os.path.join(self.model_dir, "tokens.txt")
        else:
            raise ValueError(f"Unsupported ASR language: {lang}. Must be 'en', 'ml', or 'ta'")
        return model_path, tokens_path

    def _load_model_for_lang(self, lang: str) -> None:
        """Loads or switches to the specified language model artifact."""
        if sherpa_onnx is None:
            self.state = ModelLifecycleState.FAILED
            raise ModelInferenceError("sherpa_onnx library is not installed in runtime environment")

        model_path, tokens_path = self._resolve_model_paths(lang)

        if not os.path.exists(model_path):
            self.state = ModelLifecycleState.UNAVAILABLE
            logger.error(f"Sherpa-ONNX model file missing at {model_path}")
            raise ModelNotReadyError(f"Speech model missing for language '{lang}' at {model_path}")

        if not os.path.exists(tokens_path):
            self.state = ModelLifecycleState.UNAVAILABLE
            logger.error(f"Sherpa-ONNX tokens file missing at {tokens_path}")
            raise ModelNotReadyError(f"Tokens file missing for language '{lang}' at {tokens_path}")

        # Unload previous model before loading new one to stay under 512MB RAM
        if self._recognizer is not None:
            logger.info(f"Unloading previous ASR model '{self._loaded_lang}' to free memory")
            self._recognizer = None
            gc.collect()

        logger.info(f"Loading Sherpa-ONNX INT8 model for '{lang}' (threads={self.num_threads})")
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=model_path,
            tokens=tokens_path,
            num_threads=self.num_threads,
            decoding_method="greedy_search",
            debug=False,
        )

        # Warm up engine with 0.5s zero array to initialize ONNX runtime sessions
        try:
            warmup_stream = self._recognizer.create_stream()
            warmup_stream.accept_waveform(16000, np.zeros(8000, dtype=np.float32))
            self._recognizer.decode_stream(warmup_stream)
        except Exception as e:
            logger.warning(f"Engine warmup completed with warning: {e}")

        self._loaded_lang = lang
        self.model_name = f"indicconformer-sherpa-onnx-{lang}"

    async def initialize(self) -> None:
        """Initializes model lifecycle once during service startup."""
        self.state = ModelLifecycleState.LOADING
        try:
            self._load_model_for_lang(self.current_lang)
            self.state = ModelLifecycleState.READY
            logger.info(f"Sherpa-ONNX speech model initialized and ready for '{self.current_lang}'")
        except ModelNotReadyError:
            self.state = ModelLifecycleState.UNAVAILABLE
        except Exception as e:
            self.state = ModelLifecycleState.FAILED
            logger.error(f"Sherpa-ONNX initialization failed: {e}")

    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        language_hint: Optional[str] = "mixed",
    ) -> AudioTranscribeResponse:
        """Runs preprocessed speech recognition inference on CPU."""
        if self.state != ModelLifecycleState.READY:
            raise ModelNotReadyError(f"Speech recognition service is in '{self.state.value}' state")

        if not audio_bytes:
            raise InvalidAudioError("Received empty audio stream")

        # Determine target language: prioritize valid hint (ml, ta, en), else current_lang
        target_lang = self.current_lang
        if language_hint and language_hint.lower() in ["ml", "ta", "en"]:
            target_lang = language_hint.lower()

        # Switch language model if different from currently loaded
        if target_lang != self._loaded_lang:
            try:
                self._load_model_for_lang(target_lang)
            except Exception as e:
                logger.warning(f"Could not switch language to '{target_lang}': {e}. Continuing with '{self._loaded_lang}'")

        if self._recognizer is None:
            raise ModelInferenceError("Speech recognition engine is not loaded")

        # Preprocess and validate audio (magic bytes, mono, 16kHz float32, length limits)
        samples, duration, sample_rate = preprocess_audio(
            audio_bytes,
            client_mime=mime_type,
            max_duration_seconds=settings.ASR_MAX_AUDIO_SECONDS,
        )

        if samples.size == 0:
            raise InvalidAudioError("Decoded audio stream contains zero samples")

        # Execute inference
        t_start = time.perf_counter()
        try:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self._recognizer.decode_stream(stream)
            transcript_text = stream.result.text.strip()
        except Exception as exc:
            raise ModelInferenceError(f"ONNX inference failure: {exc}") from exc
        finally:
            # Explicit cleanup of audio array
            del samples

        inference_time = round(time.perf_counter() - t_start, 3)
        confidence = 0.92 if transcript_text else 0.0

        return AudioTranscribeResponse(
            transcript=transcript_text,
            detected_language=self._loaded_lang or target_lang,
            confidence=confidence,
            duration_seconds=round(duration, 3),
            status="success" if transcript_text else "empty",
        )


class SpeechModelManager:
    """Singleton manager ensuring a single model instance and single inference worker concurrency."""

    def __init__(self):
        self.provider: Optional[SpeechRecognitionProvider] = None
        # Render Free has 512MB RAM - strictly bound to 1 concurrent inference worker
        self._inference_semaphore = asyncio.Semaphore(1)

    def get_provider(self) -> SpeechRecognitionProvider:
        if self.provider is None:
            provider_type = (settings.SPEECH_PROVIDER or settings.SPEECH_PROVIDER_TYPE).lower()
            if provider_type == "sherpa_onnx":
                self.provider = SherpaOnnxSpeechRecognitionProvider()
            else:
                self.provider = MockSpeechRecognitionProvider()
        return self.provider

    def set_provider(self, provider: SpeechRecognitionProvider) -> None:
        """Allows test suites to inject mock providers with specific failure modes."""
        self.provider = provider

    async def startup(self) -> None:
        provider = self.get_provider()
        try:
            await provider.initialize()
        except Exception as e:
            provider.state = ModelLifecycleState.FAILED
            logger.error(f"Error during speech model startup: {e}")

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        language_hint: Optional[str] = "mixed"
    ) -> AudioTranscribeResponse:
        provider = self.get_provider()
        if provider.state != ModelLifecycleState.READY:
            raise ModelNotReadyError(f"Model is currently {provider.state.value}")

        try:
            loop = asyncio.get_running_loop()
            has_loop = True
        except RuntimeError:
            has_loop = False

        if has_loop:
            async with self._inference_semaphore:
                try:
                    return await asyncio.wait_for(
                        provider.transcribe(audio_bytes, mime_type, language_hint),
                        timeout=settings.INFERENCE_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError as exc:
                    raise ModelInferenceError("Speech recognition inference timed out") from exc
        else:
            return await provider.transcribe(audio_bytes, mime_type, language_hint)


model_manager = SpeechModelManager()

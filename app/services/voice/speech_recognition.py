"""Speech Recognition Provider Interface, Lifecycle Manager, and Cold-Start Handler.

Supports:
- Lifecycle states: NOT_INITIALIZED, LOADING, READY, FAILED, UNAVAILABLE
- Single inference worker concurrency to respect Render Free RAM limits
- Model loaded once at startup, never per request
- Cold-start protection: returns 503 ModelNotReadyError when initializing
"""

import asyncio
import base64
from abc import ABC, abstractmethod
from typing import Optional

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
        await asyncio.sleep(0.01)  # brief non-blocking yield
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


class SpeechModelManager:
    """Singleton manager ensuring a single model instance and single inference worker concurrency."""

    def __init__(self):
        self.provider: Optional[SpeechRecognitionProvider] = None
        # Render Free has 512MB RAM - strictly bound to 1 concurrent inference worker
        self._inference_semaphore = asyncio.Semaphore(1)

    def get_provider(self) -> SpeechRecognitionProvider:
        if self.provider is None:
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

        async with self._inference_semaphore:
            try:
                return await asyncio.wait_for(
                    provider.transcribe(audio_bytes, mime_type, language_hint),
                    timeout=settings.INFERENCE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError as exc:
                raise ModelInferenceError("Speech recognition inference timed out") from exc


model_manager = SpeechModelManager()

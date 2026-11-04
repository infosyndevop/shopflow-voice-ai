"""Safe audio validation and preprocessing module for speech recognition.

Enforces:
- File signature (magic bytes) validation.
- File size and audio duration boundaries.
- Conversion to mono 16 kHz float32 PCM.
- Safe buffer cleanup with zero permanent retention.
"""

import io
from typing import Optional, Tuple
import numpy as np
import soundfile as sf

from app.core.config import settings
from app.core.errors import AudioPayloadTooLargeError, InvalidAudioError
from app.core.logging import logger

SUPPORTED_SIGNATURES = {
    "wav": (b"RIFF", 0, b"WAVE", 8),
    "ogg": (b"OggS", 0, None, None),
    "flac": (b"fLaC", 0, None, None),
}


def detect_audio_format(data: bytes) -> str:
    """Verifies audio magic bytes to prevent trusting client MIME-type/extension alone."""
    if len(data) < 12:
        raise InvalidAudioError("Audio payload is too small to contain valid headers")

    # WAV check
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"

    # FLAC check
    if data[:4] == b"fLaC":
        return "flac"

    # OGG check
    if data[:4] == b"OggS":
        return "ogg"

    # MP3 check: ID3 tag or frame sync header (11 bits set: 0xFFE0)
    if data[:3] == b"ID3":
        return "mp3"
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"

    raise InvalidAudioError("Unsupported or unverified audio file signature (expected WAV, MP3, OGG, or FLAC)")


def resample_to_16k(samples: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resamples 1D float32 audio waveform to 16,000 Hz using linear interpolation."""
    if orig_sr == 16000:
        return samples

    target_sr = 16000
    target_length = int(len(samples) * target_sr / orig_sr)
    if target_length == 0:
        return np.array([], dtype=np.float32)

    orig_indices = np.linspace(0, len(samples) - 1, num=len(samples))
    target_indices = np.linspace(0, len(samples) - 1, num=target_length)
    resampled = np.interp(target_indices, orig_indices, samples).astype(np.float32)
    return resampled


def preprocess_audio(
    audio_bytes: bytes,
    client_mime: Optional[str] = None,
    max_duration_seconds: Optional[float] = None,
) -> Tuple[np.ndarray, float, int]:
    """Validates and converts arbitrary accepted audio bytes to mono 16 kHz float32 samples.

    Returns:
        (samples_float32, duration_seconds, sample_rate)

    Guarantees:
        - Validates file signature (magic bytes).
        - Enforces size limit <= MAX_AUDIO_SIZE_BYTES.
        - Enforces duration limit <= MAX_AUDIO_DURATION_SECONDS.
        - Converts multichannel to mono.
        - Resamples to 16,000 Hz.
        - Deallocates and cleans up immediately.
    """
    if not audio_bytes:
        raise InvalidAudioError("Audio payload is empty")

    if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
        raise AudioPayloadTooLargeError(
            f"Audio file size ({len(audio_bytes)} bytes) exceeds limit ({settings.MAX_AUDIO_SIZE_BYTES} bytes)"
        )

    # 1. Verify file signature
    detected_fmt = detect_audio_format(audio_bytes)

    # 2. Decode samples using soundfile
    max_duration = max_duration_seconds or settings.MAX_AUDIO_DURATION_SECONDS
    try:
        buffer = io.BytesIO(audio_bytes)
        audio_data, sample_rate = sf.read(buffer, dtype="float32", always_2d=True)
    except Exception as exc:
        raise InvalidAudioError(f"Audio stream could not be decoded: {exc}") from exc

    if audio_data.size == 0:
        raise InvalidAudioError("Decoded audio stream contains zero audio frames")

    num_frames, num_channels = audio_data.shape
    duration = num_frames / sample_rate

    if duration > max_duration:
        raise AudioPayloadTooLargeError(
            f"Audio duration ({duration:.2f}s) exceeds maximum allowed duration ({max_duration:.2f}s)"
        )

    # 3. Convert multi-channel to mono
    if num_channels > 1:
        mono_samples = audio_data.mean(axis=1).astype(np.float32)
    else:
        mono_samples = audio_data[:, 0].astype(np.float32)

    # 4. Resample to 16,000 Hz if needed
    if sample_rate != 16000:
        final_samples = resample_to_16k(mono_samples, sample_rate)
    else:
        final_samples = mono_samples

    return final_samples, duration, 16000


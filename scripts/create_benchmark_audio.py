"""Generate test audio files of precise durations (5s, 10s, 20s, 30s) at 16kHz mono PCM."""

import os
import wave
import numpy as np

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "benchmark_audio")


def generate_test_wav(filepath: str, duration_seconds: float, sample_rate: int = 16000):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples, endpoint=False)

    # Multi-frequency audio (fundamental 150 Hz + harmonics simulating vocal formant frequencies)
    waveform = (
        0.4 * np.sin(2 * np.pi * 150 * t) +
        0.25 * np.sin(2 * np.pi * 300 * t) +
        0.15 * np.sin(2 * np.pi * 700 * t) +
        0.10 * np.sin(2 * np.pi * 1500 * t)
    )

    # Normalize to 16-bit PCM integer
    pcm16 = (waveform * 32767).astype(np.int16)

    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)        # mono
        wf.setsampwidth(2)        # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())

    print(f"Generated: {filepath} ({duration_seconds}s, {os.path.getsize(filepath)} bytes)")


def generate_all_benchmark_audios():
    durations = [5, 10, 20, 30]
    for d in durations:
        filename = f"bench_{d}s.wav"
        dest = os.path.join(AUDIO_DIR, filename)
        generate_test_wav(dest, d)


if __name__ == "__main__":
    generate_all_benchmark_audios()


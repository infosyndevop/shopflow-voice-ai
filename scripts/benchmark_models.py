"""Benchmark IndicConformer ONNX speech models on Windows 11.

Measures:
- Model file size
- Model initialization / load time
- Baseline & Peak memory usage (tracemalloc & OS memory)
- CPU usage
- Transcription latency across 5s, 10s, 20s, 30s
- Real-Time Factor (RTF = latency / duration)
- Transcribed output
"""

import gc
import json
import os
import sys
import time
import tracemalloc
import numpy as np
import sherpa_onnx
import soundfile as sf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
AUDIO_DIR = os.path.join(BASE_DIR, "data", "benchmark_audio")
RESULTS_DIR = os.path.join(BASE_DIR, "data", "benchmark_results")


def get_model_paths(lang: str):
    if lang == "en":
        model_path = os.path.join(MODELS_DIR, "en", "model.int8.onnx")
        tokens_path = os.path.join(MODELS_DIR, "en", "tokens.txt")
    elif lang in ["ml", "ta"]:
        model_path = os.path.join(MODELS_DIR, lang, "model.int8.onnx")
        tokens_path = os.path.join(MODELS_DIR, "tokens.txt")
    else:
        raise ValueError(f"Unsupported language: {lang}")
    return model_path, tokens_path


def benchmark_language(lang: str, audio_durations=[5, 10, 20, 30], num_threads: int = 1):
    print(f"\n{'='*20} BENCHMARKING LANGUAGE: {lang.upper()} {'='*20}")
    model_path, tokens_path = get_model_paths(lang)

    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found: {model_path}")
        return None
    if not os.path.exists(tokens_path):
        print(f"ERROR: Tokens file not found: {tokens_path}")
        return None

    model_size_mb = os.path.getsize(model_path) / (1024 * 1024)
    tokens_size_kb = os.path.getsize(tokens_path) / 1024
    print(f"Model file: {model_path} ({model_size_mb:.2f} MB)")
    print(f"Tokens file: {tokens_path} ({tokens_size_kb:.2f} KB)")
    print(f"Configured CPU inference threads: {num_threads}")

    # Force garbage collection to isolate memory measurement
    gc.collect()
    tracemalloc.start()
    mem_before = tracemalloc.get_traced_memory()[0]

    # Measure model loading time
    t_load_start = time.perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=model_path,
        tokens=tokens_path,
        num_threads=num_threads,
        decoding_method="greedy_search",
        debug=False,
    )
    t_load = time.perf_counter() - t_load_start
    mem_after_load, peak_load = tracemalloc.get_traced_memory()
    idle_mem_mb = (mem_after_load - mem_before) / (1024 * 1024)

    print(f"Model Load Time: {t_load:.3f} s")
    print(f"Model Traced Memory: {idle_mem_mb:.2f} MB")

    results = {
        "language": lang,
        "model_file_size_mb": round(model_size_mb, 2),
        "load_time_seconds": round(t_load, 3),
        "idle_memory_mb": round(idle_mem_mb, 2),
        "num_threads": num_threads,
        "runs": [],
    }

    # Test audio durations
    for dur in audio_durations:
        wav_path = os.path.join(AUDIO_DIR, f"bench_{dur}s.wav")
        if not os.path.exists(wav_path):
            print(f"Warning: Audio file missing: {wav_path}")
            continue

        audio, sample_rate = sf.read(wav_path, dtype="float32", always_2d=True)
        samples = audio[:, 0]

        # Warmup single pass if first run
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)

        t_infer_start = time.perf_counter()
        cpu_start = time.process_time()
        recognizer.decode_stream(stream)
        t_infer = time.perf_counter() - t_infer_start
        cpu_time = time.process_time() - cpu_start

        current_mem, peak_mem = tracemalloc.get_traced_memory()
        text = stream.result.text
        rtf = t_infer / dur  # Real-Time Factor: < 1.0 means faster than real-time

        cpu_util_pct = (cpu_time / t_infer * 100) if t_infer > 0 else 0

        run_data = {
            "duration_seconds": dur,
            "transcription_time_seconds": round(t_infer, 3),
            "cpu_time_seconds": round(cpu_time, 3),
            "cpu_utilization_pct": round(cpu_util_pct, 1),
            "rtf": round(rtf, 4),
            "peak_memory_mb": round(peak_mem / (1024 * 1024), 2),
            "output_text": text,
        }
        results["runs"].append(run_data)

        print(f"  Duration: {dur:>2}s | Latency: {t_infer:6.3f}s | RTF: {rtf:6.4f} | CPU%: {cpu_util_pct:5.1f}% | Peak Mem: {run_data['peak_memory_mb']} MB")

    tracemalloc.stop()
    del recognizer
    gc.collect()

    return results


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    target_langs = sys.argv[1].split(",") if len(sys.argv) > 1 else ["en", "ml"]
    all_summary = {}

    for lang in target_langs:
        lang = lang.strip().lower()
        res = benchmark_language(lang)
        if res:
            all_summary[lang] = res
            out_file = os.path.join(RESULTS_DIR, f"benchmark_{lang}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)
            print(f"Saved benchmark to {out_file}")

    summary_file = os.path.join(RESULTS_DIR, "benchmark_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(all_summary, f, indent=2, ensure_ascii=False)
    print(f"\nComplete benchmark summary written to {summary_file}")


if __name__ == "__main__":
    main()


"""Download and verify IndicConformer ONNX models from HuggingFace."""

import hashlib
import os
import sys
import urllib.request

REPO_BASE = "https://huggingface.co/parismitaglobalsolutions/indicconformer-sherpa-onnx/resolve/main/"
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

MODEL_REGISTRY = {
    "tokens.txt": {
        "url": REPO_BASE + "tokens.txt",
        "dest": os.path.join(MODELS_DIR, "tokens.txt"),
        "expected_size": 67605,
        "sha256": "ee60967630213f31951817ac8b402b92ec18cce80718a24a49b388e56672dfb2",
    },
    "ml_model": {
        "url": REPO_BASE + "ml/model.int8.onnx",
        "dest": os.path.join(MODELS_DIR, "ml", "model.int8.onnx"),
        "expected_size": 197595555,
        "sha256": "dcbdfa9f773db910508b40b703cb76c5974e8d4c6f123ea81265b40853c3f0c2",
    },
    "ta_model": {
        "url": REPO_BASE + "ta/model.int8.onnx",
        "dest": os.path.join(MODELS_DIR, "ta", "model.int8.onnx"),
        "expected_size": 197595513,
        "sha256": "abb7b59d706b8d27ba3fb5e5e3db7671c9e1a09bf7bc6122de507c60030e65fb",
    },
    "en_model": {
        "url": REPO_BASE + "en/model.int8.onnx",
        "dest": os.path.join(MODELS_DIR, "en", "model.int8.onnx"),
        "expected_size": 174610057,
        "sha256": "28b9261a53028a7c99ff0799f44fb53f19c78b68cc4cf40637ac9c16cb1fbc6f",
    },
    "en_tokens": {
        "url": REPO_BASE + "en/tokens.txt",
        "dest": os.path.join(MODELS_DIR, "en", "tokens.txt"),
        "expected_size": 11433,
        "sha256": "89c165b98df7af718ec0e872177279bfad4ade51331f1be92753c9583a1ef30d",
    },
}


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest_path: str, expected_size: int, expected_sha256: str = None) -> bool:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    if os.path.exists(dest_path):
        actual_size = os.path.getsize(dest_path)
        if actual_size == expected_size:
            print(f"Already exists with correct size: {dest_path} ({actual_size} bytes)")
            if expected_sha256:
                actual_sha = compute_sha256(dest_path)
                if actual_sha == expected_sha256:
                    print(f"  SHA256 verified: {actual_sha}")
                    return True
                else:
                    print(f"  SHA256 mismatch! Expected {expected_sha256}, got {actual_sha}. Re-downloading...")
            else:
                return True

    print(f"Downloading {url} -> {dest_path} ({expected_size / 1024 / 1024:.2f} MB)...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_file:
            downloaded = 0
            while chunk := resp.read(1024 * 1024):
                out_file.write(chunk)
                downloaded += len(chunk)
                percent = (downloaded / expected_size) * 100 if expected_size else 0
                sys.stdout.write(f"\r  Progress: {downloaded / 1024 / 1024:.1f}/{expected_size / 1024 / 1024:.1f} MB ({percent:.1f}%)")
                sys.stdout.flush()
        print("\n  Download complete.")

        actual_sha = compute_sha256(dest_path)
        print(f"  Computed SHA256: {actual_sha}")
        if expected_sha256 and actual_sha != expected_sha256:
            print(f"  ERROR: SHA256 mismatch! Expected {expected_sha256}")
            return False
        return True
    except Exception as e:
        print(f"\n  ERROR downloading {url}: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def download_language_model(lang: str) -> bool:
    """Download model for specific language: 'ml', 'ta', or 'en'."""
    print(f"\n=== Downloading model for language: {lang} ===")
    success = True

    if lang in ["ml", "ta"]:
        # Shared tokens.txt
        t_entry = MODEL_REGISTRY["tokens.txt"]
        if not download_file(t_entry["url"], t_entry["dest"], t_entry["expected_size"], t_entry["sha256"]):
            return False

        # Language model
        m_entry = MODEL_REGISTRY[f"{lang}_model"]
        if not download_file(m_entry["url"], m_entry["dest"], m_entry["expected_size"], m_entry["sha256"]):
            return False
    elif lang == "en":
        # English model and tokens
        m_entry = MODEL_REGISTRY["en_model"]
        if not download_file(m_entry["url"], m_entry["dest"], m_entry["expected_size"], m_entry["sha256"]):
            return False
        t_entry = MODEL_REGISTRY["en_tokens"]
        if not download_file(t_entry["url"], t_entry["dest"], t_entry["expected_size"], t_entry["sha256"]):
            return False
    else:
        print(f"Unsupported language: {lang}")
        return False

    return True


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target == "all":
        for lang in ["en", "ml", "ta"]:
            download_language_model(lang)
    else:
        download_language_model(target)

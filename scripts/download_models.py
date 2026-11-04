"""Download and verify Sherpa-ONNX IndicConformer and Fast-Conformer models.

Pinned Hugging Face Repository:
https://huggingface.co/parismitaglobalsolutions/indicconformer-sherpa-onnx

Pinned Revision:
9721eb71eea141fae0982cfcdb9dd2e3d4953c4a

Guarantees:
- Enforces exact pinned commit revision on Hugging Face.
- Verifies exact SHA256 checksums before accepting files.
- Downloads to a temporary file (.tmp) before atomic rename to prevent corrupt artifacts.
- Automatically cleans up partial/corrupt files on failure.
- Returns non-zero exit code (sys.exit(1)) on any missing file or checksum mismatch to fail the build.
"""

import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

REPO_REVISION = "9721eb71eea141fae0982cfcdb9dd2e3d4953c4a"
REPO_BASE = f"https://huggingface.co/parismitaglobalsolutions/indicconformer-sherpa-onnx/resolve/{REPO_REVISION}/"
DEFAULT_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

MODEL_REGISTRY: Dict[str, Dict[str, any]] = {
    "tokens.txt": {
        "rel_url": "tokens.txt",
        "rel_path": "tokens.txt",
        "expected_size": 67605,
        "sha256": "ee60967630213f31951817ac8b402b92ec18cce80718a24a49b388e56672dfb2",
    },
    "ml_model": {
        "rel_url": "ml/model.int8.onnx",
        "rel_path": os.path.join("ml", "model.int8.onnx"),
        "expected_size": 197595555,
        "sha256": "dcbdfa9f773db910508b40b703cb76c5974e8d4c6f123ea81265b40853c3f0c2",
    },
    "ta_model": {
        "rel_url": "ta/model.int8.onnx",
        "rel_path": os.path.join("ta", "model.int8.onnx"),
        "expected_size": 197595513,
        "sha256": "abb7b59d706b8d27ba3fb5e5e3db7671c9e1a09bf7bc6122de507c60030e65fb",
    },
    "en_model": {
        "rel_url": "en/model.int8.onnx",
        "rel_path": os.path.join("en", "model.int8.onnx"),
        "expected_size": 174610057,
        "sha256": "28b9261a53028a7c99ff0799f44fb53f19c78b68cc4cf40637ac9c16cb1fbc6f",
    },
    "en_tokens": {
        "rel_url": "en/tokens.txt",
        "rel_path": os.path.join("en", "tokens.txt"),
        "expected_size": 11433,
        "sha256": "89c165b98df7af718ec0e872177279bfad4ade51331f1be92753c9583a1ef30d",
    },
}


def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 digest of a local file in 1 MB chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def verify_file(dest_path: str, expected_size: int, expected_sha256: str) -> bool:
    """Checks if file exists and strictly matches both size and SHA-256 hash."""
    if not os.path.exists(dest_path):
        return False
    actual_size = os.path.getsize(dest_path)
    if actual_size != expected_size:
        return False
    actual_sha = compute_sha256(dest_path)
    return actual_sha.lower() == expected_sha256.lower()


def download_file(
    url: str,
    dest_path: str,
    expected_size: int,
    expected_sha256: str,
    max_retries: int = 3,
) -> bool:
    """Downloads a single artifact with integrity check, retry logic, and atomic write."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    # 1. Fast verification if already exists
    if os.path.exists(dest_path):
        actual_size = os.path.getsize(dest_path)
        if actual_size == expected_size:
            actual_sha = compute_sha256(dest_path)
            if actual_sha.lower() == expected_sha256.lower():
                print(f"[VERIFIED] {dest_path} already exists ({actual_size:,} bytes, SHA256: {actual_sha[:16]}...)")
                return True
            else:
                print(f"[WARN] Hash mismatch for existing {dest_path}. Expected {expected_sha256}, got {actual_sha}. Re-downloading.")
        else:
            print(f"[WARN] Size mismatch for existing {dest_path} ({actual_size} != {expected_size}). Re-downloading.")
        try:
            os.remove(dest_path)
        except OSError:
            pass

    # 2. Download to a temporary file
    tmp_path = dest_path + ".tmp"
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    print(f"[DOWNLOADING] {url}")
    print(f"         ==> {dest_path} ({expected_size / (1024 * 1024):.2f} MB)")

    headers = {
        "User-Agent": "CRYVEX-ShopFlow-VoiceAI-Downloader/1.0",
        "Accept": "*/*",
    }
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(1, max_retries + 1):
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as out_file:
                downloaded = 0
                while chunk := resp.read(1024 * 1024):
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    percent = (downloaded / expected_size) * 100 if expected_size else 0
                    sys.stdout.write(
                        f"\r    Progress: {downloaded / (1024 * 1024):.1f}/{expected_size / (1024 * 1024):.1f} MB ({percent:.1f}%)"
                    )
                    sys.stdout.flush()

            sys.stdout.write("\n")
            elapsed = time.time() - t0
            print(f"    Download complete in {elapsed:.2f}s ({expected_size / elapsed / 1024 / 1024:.2f} MB/s)")

            # Verify size
            actual_size = os.path.getsize(tmp_path)
            if actual_size != expected_size:
                print(f"    [ERROR] Downloaded size mismatch: expected {expected_size}, got {actual_size}", file=sys.stderr)
                os.remove(tmp_path)
                continue

            # Verify SHA256
            actual_sha = compute_sha256(tmp_path)
            if actual_sha.lower() != expected_sha256.lower():
                print(
                    f"    [ERROR] SHA256 checksum mismatch!\n"
                    f"      Expected: {expected_sha256}\n"
                    f"      Actual:   {actual_sha}",
                    file=sys.stderr,
                )
                os.remove(tmp_path)
                continue

            # Atomic rename on success
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(tmp_path, dest_path)
            print(f"    [SUCCESS] Verified SHA256: {actual_sha}")
            return True

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"\n    [RETRY {attempt}/{max_retries}] Download error: {e}", file=sys.stderr)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            if attempt < max_retries:
                time.sleep(2 * attempt)

    print(f"[FATAL] Failed to download {url} after {max_retries} attempts.", file=sys.stderr)
    return False


def get_required_registry_keys(languages: List[str]) -> List[str]:
    """Determines which registry keys are required for the given language set."""
    keys = []
    normalized_langs = set(l.lower().strip() for l in languages)

    if "all" in normalized_langs:
        normalized_langs = {"en", "ml", "ta"}

    if "en" in normalized_langs:
        keys.extend(["en_tokens", "en_model"])

    if "ml" in normalized_langs or "ta" in normalized_langs:
        if "tokens.txt" not in keys:
            keys.append("tokens.txt")
        if "ml" in normalized_langs:
            keys.append("ml_model")
        if "ta" in normalized_langs:
            keys.append("ta_model")

    return keys


def download_models_for_languages(
    languages: List[str],
    models_dir: Optional[str] = None,
) -> bool:
    """Downloads and verifies all artifacts required for specified languages."""
    base_dir = models_dir or DEFAULT_MODELS_DIR
    os.makedirs(base_dir, exist_ok=True)

    required_keys = get_required_registry_keys(languages)
    if not required_keys:
        print(f"[ERROR] No valid language recognized in: {languages}", file=sys.stderr)
        return False

    print("=" * 65)
    print(f"CRYVEX VOICE AI: Model Artifact Downloader")
    print(f"Target Directory: {base_dir}")
    print(f"Languages:        {languages}")
    print(f"Required Files:   {len(required_keys)}")
    print(f"Pinned Revision:  {REPO_REVISION}")
    print("=" * 65)

    for key in required_keys:
        entry = MODEL_REGISTRY[key]
        url = REPO_BASE + entry["rel_url"]
        dest = os.path.join(base_dir, entry["rel_path"])

        ok = download_file(
            url=url,
            dest_path=dest,
            expected_size=entry["expected_size"],
            expected_sha256=entry["sha256"],
        )
        if not ok:
            print(f"\n[FATAL] Build failed: artifact {key} could not be retrieved and verified.", file=sys.stderr)
            return False

    print("\n" + "=" * 65)
    print("ALL REQUIRED MODEL ARTIFACTS VERIFIED SUCCESSFULLY")
    print("=" * 65)
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Download IndicConformer ONNX models for Sherpa-ONNX")
    parser.add_argument(
        "languages",
        nargs="*",
        default=[],
        help="Languages to download: 'en', 'ml', 'ta', or 'all' (default: reads ASR_LANGUAGE env var, fallback 'en')",
    )
    parser.add_argument(
        "--lang",
        dest="lang_flag",
        default=None,
        help="Optional flag specifying language ('en', 'ml', 'ta', 'all')",
    )
    parser.add_argument(
        "--models-dir",
        dest="models_dir",
        default=None,
        help="Optional destination models directory (default: <project-root>/models)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify checksums of existing files without downloading",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine languages from CLI args, flag, or environment variable
    langs = []
    if args.languages:
        langs.extend(args.languages)
    if args.lang_flag:
        langs.append(args.lang_flag)

    if not langs:
        env_lang = os.environ.get("ASR_LANGUAGE", "en").strip()
        langs = [env_lang]

    # Handle comma-separated input e.g. "en,ml,ta"
    expanded_langs = []
    for item in langs:
        expanded_langs.extend([x.strip() for x in item.split(",") if x.strip()])

    target_dir = args.models_dir or os.environ.get("ASR_MODEL_DIR") or DEFAULT_MODELS_DIR

    if args.check_only:
        print(f"Verifying existing model artifacts in: {target_dir}")
        required_keys = get_required_registry_keys(expanded_langs)
        all_ok = True
        for key in required_keys:
            entry = MODEL_REGISTRY[key]
            dest = os.path.join(target_dir, entry["rel_path"])
            ok = verify_file(dest, entry["expected_size"], entry["sha256"])
            status = "OK" if ok else "FAILED/MISSING"
            print(f"  [{status}] {dest}")
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)

    success = download_models_for_languages(expanded_langs, models_dir=target_dir)
    if not success:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

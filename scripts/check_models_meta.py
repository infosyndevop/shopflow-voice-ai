"""Script to inspect HuggingFace repository files, sizes, and headers."""

import urllib.request

files = [
    "tokens.txt",
    "ml/model.int8.onnx",
    "ta/model.int8.onnx",
    "en/model.int8.onnx",
    "en/tokens.txt",
]
base = "https://huggingface.co/parismitaglobalsolutions/indicconformer-sherpa-onnx/resolve/main/"

print("Checking model files on HuggingFace:")
for f in files:
    url = base + f
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
    try:
        with urllib.request.urlopen(req) as resp:
            size = int(resp.headers.get("Content-Length", 0))
            etag = resp.headers.get("ETag", "").strip('"')
            x_linked_etag = resp.headers.get("X-Linked-ETag", "").strip('"')
            sha = x_linked_etag or etag
            print(f"File: {f}")
            print(f"  Size: {size / (1024 * 1024):.2f} MB ({size} bytes)")
            print(f"  ETag/SHA: {sha}")
    except Exception as e:
        print(f"File: {f} -> ERROR: {e}")


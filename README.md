# CRYVEX SHOPFLOW VOICE AI BACKEND

An independent, tenant-isolated Voice Intelligence microservice engineered for retail billing environments supporting Malayalam, Tamil, English, and code-switching conversations.

The microservice interprets employee speech, extracts exact quantities and package sizes, matches SKUs with leading-zero preservation, isolates price references from quantities, and queries the authoritative ShopFlow product catalogue without creating duplicate databases or silently converting ambiguous speech into billing items.

---

## 1. Core Architecture

The architecture enforces strict decoupling from the ShopFlow billing database and core APIs:

```
[Retail Terminal / Cashier Mic]
              │ (Audio / Transcript)
              ▼
    [Voice AI Backend] (FastAPI Microservice)
       ├── Speech Recognition Layer (Loaded once, 1 inference worker)
       ├── Multilingual Normalizer (Malayalam, Tamil, English NFKC)
       ├── Number & Quantity Parser (Order Qty vs Package Size vs Price Reference)
       ├── Exact SKU Matcher (Preserves '002', detects product conflicts)
       ├── Candidate Discovery (Exact canonical/alias first, fuzzy discovery only)
       ├── Variant Matcher (Unambiguous resolution, never auto-substitutes)
       └── Confidence Engine (Multi-dimensional heuristic scoring)
              │
              │ (Authenticated Internal REST API with Tenant Isolation)
              ▼
   [Main ShopFlow Backend] (Authoritative PostgreSQL Catalogue)
```

### Module Structure

```
app/
├── main.py                     # FastAPI entrypoint, lifespan, centralized error handling
├── api/
│   ├── health.py               # Liveness, readiness, model state, diagnostics
│   └── voice.py                # Transcribe & interpret endpoints
├── core/
│   ├── config.py               # Pydantic Settings and environment configuration
│   ├── errors.py               # Centralized exception definitions
│   └── logging.py              # Safe redacted structured logger
├── database/
│   ├── connection.py           # Optional non-authoritative DB connection pool
│   └── models.py               # Documented schema contracts
├── schemas/
│   └── voice_schemas.py        # Pydantic request/response schemas & statuses
├── security/
│   └── service_auth.py         # Constant-time token verification & tenant context
└── services/
    ├── catalogue/
    │   ├── interface.py        # Abstract CatalogueProvider interface
    │   ├── mock_catalogue.py   # In-memory tenant-isolated retail fixtures
    │   └── http_catalogue.py   # Production client calling Main ShopFlow backend
    └── voice/
        ├── speech_recognition.py # Model lifecycle (NOT_INITIALIZED -> READY)
        ├── language_normalizer.py# Malayalam/Tamil/English NFKC normalization
        ├── number_parser.py    # Word numbers, spoken digit sequences ("002")
        ├── quantity_parser.py  # Quantities vs Package sizes vs Price references
        ├── sku_matcher.py      # Exact SKU lookup, leading zero preservation
        ├── product_matcher.py  # Exact canonical/alias first, fuzzy discovery only
        ├── variant_matcher.py  # Variant resolution & ambiguity detection
        ├── confidence_engine.py# Multi-dimensional confidence scoring
        └── conversation_engine.py # Multi-turn dialog & idempotency cache
```

---

## 2. Python Version and Windows 11 Local Setup

- **Python Version**: `3.11.8`
- **Operating System**: Windows 11 (8 GB RAM developer environment)

### Local Virtual Environment Setup

1. Open PowerShell in the project root:
   ```powershell
   cd c:\Users\Anandhu\OneDrive\Desktop\shopflow-voice-ai
   ```

2. Create virtual environment (if not already present):
   ```powershell
   python -m venv venv
   ```

3. Activate the virtual environment:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

4. Install dependencies:
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

---

## 3. Environment Variables Configuration

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Key environment configuration variables:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | Deployment environment (`development`, `production`) |
| `DEBUG` | `false` | Enable Swagger `/docs` when true |
| `SERVICE_API_KEY` | `min32chars...` | Service-to-service shared secret |
| `CATALOGUE_PROVIDER_TYPE` | `mock` | `mock` for local tests, `http` for ShopFlow backend |
| `SHOPFLOW_BACKEND_URL` | `http://localhost:8000` | Authoritative Main ShopFlow Backend URL |
| `SHOPFLOW_INTERNAL_API_KEY`| `None` | Authentication secret to call main backend |
| `SPEECH_PROVIDER_TYPE` | `mock` | `mock` for local tests or offline model |
| `SPEECH_MODEL_WARMUP_ON_STARTUP` | `true` | Pre-warms model once on startup |
| `DEFAULT_MAX_QUANTITY` | `500.0` | Retail sanity ceiling for quantities |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.85` | High-confidence verification threshold |

---

## 4. Local Startup and Testing Commands

### Start the Service Locally

```powershell
.\venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Run Automated Pytest Suite

```powershell
.\venv\Scripts\pytest.exe -v
```

Execute specific test suites:
```powershell
# Quantity and number parsing
.\venv\Scripts\pytest.exe tests/test_quantity_parser.py -v

# Exact SKU matching and leading zeros
.\venv\Scripts\pytest.exe tests/test_sku_matching.py -v

# Product matching and aliases
.\venv\Scripts\pytest.exe tests/test_product_matching.py -v

# False matches and ambiguity protection
.\venv\Scripts\pytest.exe tests/test_false_matches.py -v

# Cold-start, timeout, and resilience tests
.\venv\Scripts\pytest.exe tests/test_cold_start.py -v
```

---

## 5. API Documentation

### 1. `POST /api/v1/voice/transcribe`
Receives base64-encoded audio and returns a verified transcript.

**Headers**:
- `X-Service-Key`: `<SERVICE_API_KEY>`
- `X-Tenant-ID`: `<TENANT_ID>`

**Request Body**:
```json
{
  "audio_base64": "<base64_encoded_audio_bytes>",
  "mime_type": "audio/wav",
  "language_hint": "mixed"
}
```

**Response (200 OK)**:
```json
{
  "transcript": "three packets of 160 gram washing soap",
  "detected_language": "mixed",
  "confidence": 0.96,
  "duration_seconds": 2.5,
  "status": "success"
}
```

### 2. `POST /api/v1/voice/interpret`
Interprets raw transcript text using the authenticated tenant's catalogue.

**Headers**:
- `X-Service-Key`: `<SERVICE_API_KEY>`
- `X-Tenant-ID`: `<TENANT_ID>`

**Request Body**:
```json
{
  "transcript": "three packets of 160 gram washing soap",
  "session_id": "pos-terminal-01",
  "idempotency_key": "req-uuid-12345"
}
```

**Response (200 OK - Verified)**:
```json
{
  "status": "verified",
  "transcript": "three packets of 160 gram washing soap",
  "normalized_transcript": "three packet of 160 g washing soap",
  "items": [
    {
      "product_id": "prod-washing-soap",
      "product_name": "Washing Soap",
      "variant_id": "var-wash-160g",
      "variant_name": "160g",
      "sku": "002",
      "quantity": 3.0,
      "unit": "packet",
      "package_size": "160g",
      "price_reference": null,
      "product_confidence": 1.0,
      "quantity_confidence": 0.98,
      "status": "verified",
      "clarification_prompt": null,
      "candidate_options": []
    }
  ],
  "unmatched_phrases": [],
  "clarification_required": false,
  "clarification_question": null,
  "session_id": "pos-terminal-01",
  "request_id": "42299839-a9a3-4b68-9fe8-2e008c2a30cb"
}
```

### 3. Health Endpoints
- `GET /health/live`: Returns 200 OK if the process is responsive.
- `GET /health/ready`: Returns 200 OK when both the speech model and catalogue are initialized. Returns 503 during cold-start.
- `GET /health/model`: Returns model lifecycle state (`not_initialized`, `loading`, `ready`, `failed`).
- `GET /health/diagnostics`: Operational metrics (uptime, request count, memory).

---

## 6. Security Model and Tenant Isolation

1. **Authentication**: All voice operations require dedicated service-to-service credentials validated via constant-time comparison (`secrets.compare_digest`).
2. **Untrusted Input**: The `tenant_id` is derived strictly from verified request headers (`X-Tenant-ID`), never trusted blindly from client JSON bodies.
3. **Tenant Scoping**: All catalogue lookups, SKU matches, and aliases are scoped by `tenant_id`.
4. **Data Redaction**: Sensitive headers (`X-Service-Key`, `Authorization`) and raw audio bytes are sanitized from server logs.
5. **No Billing Authority**: The service cannot calculate final billing amounts, deduct stock, or create customer bills.

---

## 7. Main ShopFlow Backend Integration Contract

To connect the Voice AI microservice to the Main ShopFlow Backend, set `CATALOGUE_PROVIDER_TYPE=http` and consult the complete specification:
- **Specification Document**: [`docs/CATALOGUE_INTEGRATION_SPEC.md`](docs/CATALOGUE_INTEGRATION_SPEC.md)
- **Endpoint**: `GET /api/v1/internal/catalogue`
- **Auth**: Service credentials with constant-time verification (`X-Service-Client-Id`, `X-Service-Secret`)
- **Tenant Scoping**: Enforced through `X-Tenant-Id` header
- **Offline / Mock Mode**: `MockCatalogueProvider` is available for zero-dependency local testing.

---

## 8. Speech Recognition Engine & Model Benchmarking

The Voice AI microservice supports **Sherpa-ONNX CPU inference** using quantized INT8 NeMo Fast-Conformer and IndicConformer ONNX exports.

### Benchmarks on Windows 11 (8 GB RAM, 1 CPU thread)

| Model Language | Model File | Model Size | Load Time | 5s Audio Latency | 30s Audio Latency | Average RTF | Peak RAM |
|---|---|---|---|---|---|---|---|
| **English (`en`)** | `models/en/model.int8.onnx` | 166.52 MB | 1.135 s | 0.184 s | 1.267 s | **0.038** | ~210 MB |
| **Malayalam (`ml`)** | `models/ml/model.int8.onnx` | 188.44 MB | 0.694 s | 0.594 s | 4.038 s | **0.120** | ~238 MB |
| **Tamil (`ta`)** | `models/ta/model.int8.onnx` | 188.44 MB | 0.707 s | 0.554 s | 4.295 s | **0.119** | ~238 MB |

*Base Python backend memory: ~25.95 MB.*

### Strict Render Free (512 MB RAM) Protection Rules
1. **Never load multiple language models simultaneously**: When switching languages, previous models are cleanly unloaded from memory and Python garbage collection is triggered.
2. **Single Inference Worker**: Bound via `asyncio.Semaphore(1)` to eliminate RAM spikes.
3. **Download Tooling**: Models are downloaded with SHA256 checksum verification via `python scripts/download_models.py --lang en`.

---

## 9. Multi-Product & Conversational Interpretation

Supports complex compound sentences and conversational retail dialogs:
- **Multi-product Extraction**:
  `"Two Urvashi soaps, three packets of 160 gram washing soap and one egg"`
  -> Dissects into 3 distinct items, preserving exact package sizes, units, and quantities.
- **Partial Ambiguity Handling**:
  If any phrase is unverified or ambiguous, verified items are retained in `session.items` while the unresolved phrase is isolated for clarification.
- **Similar Product Protection**:
  "Egg" and "Egg Masala" are evaluated strictly against their canonical names and never merged.
- **Conversational Commands**:
  - Removals: `"remove washing soap"` -> flags status as `rejected`.
  - Corrections: `"not soap, egg"` -> replaces previous item with corrected item.
  - Clarification resolution: Resolves pending variant/quantity requests across conversation turns.

---

## 10. Automated Test Suite (65 Passing Tests)

Run the entire automated test suite:
```powershell
.\venv\Scripts\python -m pytest tests -v
```

Test Suites:
1. `tests/test_adversarial_quantities.py` (10 tests): Price reference isolation (₹10 biscuit), numeric brand protection (20-20), leading zero preservation (SKU 002), retail collectives (one dozen = 12), quantity boundaries.
2. `tests/test_multi_product.py` (5 tests): Multi-item extraction, multilingual conjunctions (Malayalam, Tamil, English), partial ambiguity retention, conversational removals.
3. `tests/test_real_speech_provider.py` (5 tests): Sherpa-ONNX model lifecycle, CPU inference on 16kHz WAV, language switching without memory leak, invalid audio rejection.
4. `tests/test_api_endpoints.py` (7 tests): Live/ready/diagnostics health checks, multi-variant clarification, price isolation, transcribe audio endpoint.
5. `tests/test_cold_start.py` (10 tests): 503 cold-start protection, catalogue timeouts, idempotency caching, service auth verification, tenant sanitization, payload limits.
6. `tests/test_false_matches.py` (7 tests): False match prevention (Egg vs Egg Masala), multi-variant ambiguity, SKU conflict detection, unverified tenant rejection.
7. `tests/test_product_matching.py` (5 tests): Exact canonical match, approved aliases, cross-tenant product isolation.
8. `tests/test_quantity_parser.py` (10 tests): English/Malayalam/Tamil number words, spoken digit sequences, units, package sizes, contradictory quantity rejection.
9. `tests/test_sku_matching.py` (6 tests): Exact SKU leading zero preservation, spoken digit SKUs, unknown SKU rejection, SKU vs product name conflict.

---

## 11. Render Free Deployment Instructions

1. Link your Git repository to your Render account.
2. Create a new **Web Service** on Render.
3. Select **Docker** as the runtime.
4. Set instance type to **Free** (512 MB RAM, 0.5 CPU).
5. Set Health Check path to `/health/live`.
6. Configure environment variables in the Render Dashboard matching `.env.example`:
   - Set `SPEECH_PROVIDER=sherpa_onnx` (or `mock` for lightweight deployments).
   - Set `ASR_LANGUAGE=en` (or `ml` / `ta`).
   - Set `SERVICE_API_KEY` (min 32 chars).
7. Deploy service.



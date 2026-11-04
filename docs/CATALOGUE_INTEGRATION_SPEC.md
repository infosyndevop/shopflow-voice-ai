# CRYVEX SHOPFLOW: Voice AI to Main Backend Catalogue Integration Specification

This document defines the formal, strict HTTP/JSON contract between the **ShopFlow Voice AI Backend** and the **ShopFlow Main Billing Backend**.

---

## 1. Architectural Boundaries and Non-Negotiable Rules

1. **Read-Only Catalogue Access**:
   The Voice AI service **only reads** product metadata, active variants, SKUs, barcodes, and alias mappings.
2. **Zero Billing Mutations**:
   The Voice AI backend **never** creates bills, **never** alters prices, **never** deducts stock, and **never** authorizes financial transactions.
3. **Tenant Strictness**:
   Every catalogue request is strictly isolated by `tenant_id`. Catalogues are never shared, merged, or cached cross-tenant.
4. **Resilience and Graceful Degradation**:
   If the catalogue endpoint is unreachable, timed out, or returns a 5xx error, Voice AI serves cached data within TTL or returns HTTP 503 (`CatalogueServiceUnavailableError`). It never crashes.

---

## 2. Integration Endpoint Contract

### `GET /api/v1/internal/catalogue`

Fetches active product catalogue records for a specific authenticated tenant.

#### Headers
| Header Name | Type | Required | Description |
|---|---|---|---|
| `X-Service-Client-Id` | String | Yes | Identity of Voice AI microservice client |
| `X-Service-Secret` | String | Yes | Shared internal secret (verified using constant-time comparison) |
| `X-Tenant-Id` | String | Yes | Target tenant identity (verified against client permissions) |
| `X-Request-Id` | String | Yes | Distributed tracing UUID |

#### Query Parameters
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `page` | Integer | No | `1` | Pagination page number |
| `page_size` | Integer | No | `100` | Max items per page (maximum: `250`) |
| `updated_after` | ISO8601 String | No | `None` | Incremental sync filter |

---

## 3. JSON Schema Specification

### Response Payload (`200 OK`)

```json
{
  "tenant_id": "tenant_12345",
  "page": 1,
  "page_size": 100,
  "total_products": 240,
  "has_more": true,
  "products": [
    {
      "product_id": "prod-wash-soap",
      "canonical_name": "Washing Soap",
      "category": "Household",
      "default_unit": "packet",
      "is_active": true,
      "variants": [
        {
          "variant_id": "var-wash-160g",
          "variant_name": "160g",
          "sku": "002",
          "barcode": "8901234567890",
          "package_size": "160g",
          "unit": "packet",
          "is_active": true,
          "stock_available": 45.0
        }
      ],
      "aliases": [
        {
          "alias_phrase": "തുണി സോപ്പ്",
          "product_id": "prod-wash-soap",
          "variant_id": null,
          "language": "ml",
          "is_active": true
        },
        {
          "alias_phrase": "washing soap",
          "product_id": "prod-wash-soap",
          "variant_id": null,
          "language": "en",
          "is_active": true
        }
      ]
    }
  ]
}
```

---

## 4. Field Definitions and Constraints

### Product Fields
- `product_id` (string, required): Permanent unique product identifier within tenant.
- `canonical_name` (string, required): Official display name used in billing.
- `category` (string, optional): Department or category.
- `default_unit` (string, required): Fallback unit if not specified in variant (`piece`, `packet`, `box`, `kg`, `g`, `litre`, `ml`).
- `is_active` (boolean, required): Inactive products are completely omitted from voice matching.

### Variant Fields
- `variant_id` (string, required): Unique identifier for variant.
- `variant_name` (string, required): Name describing variant (e.g. `160g`, `500ml`, `Small`).
- `sku` (string, optional): Stock Keeping Unit. **Crucial Rule**: SKUs are strictly string-typed to preserve leading zeros (e.g. `"002"` is never converted to integer `2`).
- `barcode` (string, optional): 8, 12, 13, or 14-digit numeric string.
- `package_size` (string, optional): Normalized package size with unit (e.g. `160g`, `1L`, `500ml`).
- `unit` (string, required): Standard unit (`packet`, `piece`, `kg`, etc.).
- `is_active` (boolean, required): Whether this variant is currently sold.
- `stock_available` (float, optional): Non-authoritative stock indicator. Main backend retains final authority during billing checkout.

### Alias Fields
- `alias_phrase` (string, required): Colloquial, phonetic, or vernacular phrase spoken by customers/staff.
- `language` (string, required): `"ml"` (Malayalam), `"ta"` (Tamil), `"en"` (English), or `"all"`.
- `variant_id` (string, optional): Directly links an alias to a specific variant if applicable.

---

## 5. Caching and Invalidation Contract

1. **TTL Caching**:
   Voice AI caches catalogue records locally in memory for `CATALOGUE_CACHE_TTL_SECONDS` (default: 60 seconds).
2. **Explicit Webhook Cache Invalidation**:
   Main backend sends `POST /api/v1/voice/catalogue/invalidate` with `{"tenant_id": "..."}` upon catalogue updates.
3. **Stale Cache Fallback**:
   If Main Backend is temporarily unreachable, Voice AI may serve stale cached data for up to 300 seconds, logging a warning with `X-Request-Id`.
4. **Cold Start & Offline Mode**:
   During tests and local offline development, `MockCatalogueProvider` is injected automatically without network dependency.

---

## 6. Error & Failure Handling

| Scenario | HTTP Status | Voice AI Behavior |
|---|---|---|
| Invalid Service Secret | `401 Unauthorized` | Logs security audit event; terminates request without retry. |
| Tenant ID Mismatch | `403 Forbidden` | Rejects interpretation; never exposes cross-tenant catalogue. |
| Upstream Timeout (> 3.0s) | `504 Gateway Timeout` | Catches timeout; falls back to cache or raises `CatalogueTimeoutError`. |
| Main Backend Offline (5xx) | `502 / 503` | Raises `CatalogueServiceUnavailableError`; returns HTTP 503 to POS client. |


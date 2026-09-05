# TraFriend API Specification

## 1. Status and scope

This is the proposed public HTTP contract for the MVP. It is intentionally framework-neutral at the contract level even though FastAPI will implement it. Examples are illustrative; the generated OpenAPI document becomes authoritative once implementation begins.

Public API base path:

```text
/api/v1
```

The API is read-oriented. Calculation `POST` requests are side-effect free and are not persisted as user history in the MVP. Reference capture and provider ingestion are worker responsibilities, not public endpoints. This phase exposes only a local manual CLI for overnight capture; it does not add an unauthenticated development or administration route.

`OVERNIGHT_OPEN` and `OVERNIGHT_SNAPSHOT` are distinct internal reference types. A future public reference representation will include `reference_type`, `source`, `source_feed`, `observed_at`, `market_timestamp`, `price_basis`, `quality`, and `status`. It may expose only an atomically complete active pair; partial attempts remain operational data.

## 2. Contract conventions

### 2.1 Media types and naming

- JSON request and response bodies use `application/json`.
- Errors use `application/problem+json`.
- Field names use `snake_case`.
- Resource identifiers are opaque strings. Clients must not derive meaning from ID formats.
- Ticker symbols are display/search values, not stable primary keys.
- All timestamps are RFC 3339 strings in UTC, for example `2026-09-05T00:00:04Z`.
- Market trading dates use ISO `YYYY-MM-DD` and are derived using the configured U.S. exchange calendar.
- Prices, ratios, leverage factors, and returns are serialized as decimal strings, never JSON floating-point numbers.
- Ratios and returns use fractional units: `"0.0588"` means `5.88%`.
- Enums are lowercase strings.

### 2.2 Success envelope

Single-resource response:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_01J..."
  }
}
```

Collection response:

```json
{
  "data": [],
  "meta": {
    "request_id": "req_01J...",
    "next_cursor": null
  }
}
```

### 2.3 Error envelope

Errors follow Problem Details semantics and include a stable machine code:

```json
{
  "type": "https://trafriend.example/problems/reference-unavailable",
  "title": "Daily Reference Price unavailable",
  "status": 503,
  "detail": "No complete reference price set is available for this relationship and trading date.",
  "instance": "/api/v1/leveraged-etf/calculations",
  "code": "REFERENCE_UNAVAILABLE",
  "request_id": "req_01J...",
  "errors": []
}
```

`detail` is safe for users but is not a stable programmatic contract. Clients branch on `status` and `code`.

Initial error codes:

| HTTP | Code | Meaning |
|---:|---|---|
| 400 | `INVALID_REQUEST` | JSON is malformed or parameters conflict |
| 404 | `INSTRUMENT_NOT_FOUND` | Instrument ID does not exist |
| 404 | `RELATIONSHIP_NOT_FOUND` | Relationship ID does not exist or is inactive for the requested context |
| 409 | `REFERENCE_VERSION_INACTIVE` | UI submitted a reference version that has since been superseded |
| 422 | `VALIDATION_ERROR` | One or more fields violate the schema |
| 422 | `CALCULATION_OUT_OF_DOMAIN` | The theoretical model produces a non-positive price or violates a formula invariant |
| 422 | `UNSUPPORTED_INTERVAL` | Requested analytics interval is unavailable |
| 422 | `RANGE_TOO_LARGE` | Date range exceeds the limit for the selected interval |
| 503 | `REFERENCE_UNAVAILABLE` | No complete current reference pair is published |
| 503 | `DATA_TEMPORARILY_UNAVAILABLE` | Required stored analytics data cannot currently be served |
| 429 | `RATE_LIMITED` | Public request limit exceeded |

Provider-specific error messages and credentials must never appear in public error bodies.

### 2.4 HTTP and caching

- GET endpoints support `ETag`/`If-None-Match` when practical.
- Reference and latest-value responses use short cache lifetimes consistent with their displayed freshness.
- Historical finalized data may use longer immutable caching.
- Calculation responses use `Cache-Control: no-store` by default.
- Every response includes or echoes an `X-Request-ID`.
- Public endpoints may be rate-limited by IP or another privacy-conscious anonymous key.
- Production CORS permits only configured TraFriend frontend origins.

## 3. Shared representations

### 3.1 Instrument summary

```json
{
  "id": "ins_nvda_xnas",
  "symbol": "NVDA",
  "name": "NVIDIA Corporation",
  "instrument_type": "stock",
  "exchange_mic": "XNAS",
  "currency": "USD",
  "status": "active",
  "capabilities": {
    "leveraged_relationships": true,
    "profit_ratio": true
  }
}
```

`instrument_type` is one of `stock`, `etf`, or `leveraged_etf` for the MVP. `capabilities` reflects TraFriend data availability, not a general statement about the security.

### 3.2 Leveraged product relationship

```json
{
  "id": "rel_nvda_nvdl_2x",
  "underlying": {
    "id": "ins_nvda_xnas",
    "symbol": "NVDA",
    "name": "NVIDIA Corporation",
    "instrument_type": "stock",
    "exchange_mic": "XNAS",
    "currency": "USD",
    "status": "active",
    "capabilities": {
      "leveraged_relationships": true,
      "profit_ratio": true
    }
  },
  "leveraged_product": {
    "id": "ins_nvdl_xnas",
    "symbol": "NVDL",
    "name": "GraniteShares 2x Long NVDA Daily ETF",
    "instrument_type": "leveraged_etf",
    "exchange_mic": "XNAS",
    "currency": "USD",
    "status": "active",
    "capabilities": {
      "leveraged_relationships": true,
      "profit_ratio": false
    }
  },
  "leverage_factor": "2",
  "objective_period": "daily",
  "effective_from": "2023-12-04",
  "effective_to": null
}
```

Inverse products use a negative factor such as `"-3"`.

### 3.3 Daily reference set

```json
{
  "id": "refv_01J...",
  "relationship_id": "rel_nvda_nvdl_2x",
  "trading_date": "2026-09-08",
  "session": "us_overnight_open",
  "status": "active",
  "version": 1,
  "underlying": {
    "instrument_id": "ins_nvda_xnas",
    "symbol": "NVDA",
    "price": "170.00000000",
    "quoted_at": "2026-09-08T00:00:02Z"
  },
  "leveraged_product": {
    "instrument_id": "ins_nvdl_xnas",
    "symbol": "NVDL",
    "price": "80.00000000",
    "quoted_at": "2026-09-08T00:00:04Z"
  },
  "captured_at": "2026-09-08T00:00:05Z",
  "provider": "mock",
  "freshness": "current"
}
```

`provider` is a safe public label, not configuration or credentials. `freshness` is one of `current`, `stale`, or `unknown`. Calculator submission is enabled only for an `active` reference that passes application freshness policy.

## 4. Instrument endpoints

### 4.1 Search instruments

```http
GET /api/v1/instruments/search?query=nvda&limit=10
```

Query parameters:

| Name | Type | Required | Rules |
|---|---|---:|---|
| `query` | string | yes | Trimmed, 1-64 characters |
| `limit` | integer | no | Default 10, minimum 1, maximum 25 |
| `instrument_type` | enum | no | `stock`, `etf`, or `leveraged_etf` |

Response `200`:

```json
{
  "data": [
    {
      "id": "ins_nvda_xnas",
      "symbol": "NVDA",
      "name": "NVIDIA Corporation",
      "instrument_type": "stock",
      "exchange_mic": "XNAS",
      "currency": "USD",
      "status": "active",
      "capabilities": {
        "leveraged_relationships": true,
        "profit_ratio": true
      }
    },
    {
      "id": "ins_nvdl_xnas",
      "symbol": "NVDL",
      "name": "GraniteShares 2x Long NVDA Daily ETF",
      "instrument_type": "leveraged_etf",
      "exchange_mic": "XNAS",
      "currency": "USD",
      "status": "active",
      "capabilities": {
        "leveraged_relationships": true,
        "profit_ratio": false
      }
    }
  ],
  "meta": {
    "request_id": "req_01J...",
    "next_cursor": null
  }
}
```

Search reads the normalized instrument catalog. It does not expose arbitrary provider search payloads.

### 4.2 Get an instrument

```http
GET /api/v1/instruments/{instrument_id}
```

Response `200`: success envelope containing one Instrument summary.

### 4.3 Resolve leveraged products

```http
GET /api/v1/instruments/{instrument_id}/leveraged-products
```

If `instrument_id` is an underlying, the response returns that instrument and all active leveraged products. If it is a leveraged ETF, the response resolves its canonical underlying and returns sibling products as well.

Response `200`:

```json
{
  "data": {
    "selected_instrument_id": "ins_nvdl_xnas",
    "underlying": {
      "id": "ins_nvda_xnas",
      "symbol": "NVDA",
      "name": "NVIDIA Corporation",
      "instrument_type": "stock",
      "exchange_mic": "XNAS",
      "currency": "USD",
      "status": "active",
      "capabilities": {
        "leveraged_relationships": true,
        "profit_ratio": true
      }
    },
    "relationships": [
      {
        "id": "rel_nvda_nvdl_2x",
        "leveraged_product": {
          "id": "ins_nvdl_xnas",
          "symbol": "NVDL",
          "name": "GraniteShares 2x Long NVDA Daily ETF",
          "instrument_type": "leveraged_etf",
          "exchange_mic": "XNAS",
          "currency": "USD",
          "status": "active",
          "capabilities": {
            "leveraged_relationships": true,
            "profit_ratio": false
          }
        },
        "leverage_factor": "2",
        "objective_period": "daily",
        "effective_from": "2023-12-04",
        "effective_to": null,
        "reference_availability": "current"
      }
    ]
  },
  "meta": {
    "request_id": "req_01J..."
  }
}
```

`reference_availability` is `current`, `stale`, or `unavailable` and allows the UI to communicate status before selecting a pair.

## 5. Leveraged ETF endpoints

### 5.1 Get active Daily Reference Price set

```http
GET /api/v1/leveraged-etf/relationships/{relationship_id}/reference
```

Optional query parameter:

| Name | Type | Behavior |
|---|---|---|
| `trading_date` | date | Omit for the current exchange trading date. Historical access is reserved until explicitly enabled. |

Response `200`: success envelope containing the Daily reference set representation.

Response `503` with `REFERENCE_UNAVAILABLE` if no complete valid pair is active. The API must not silently substitute another trading date.

### 5.2 Calculate a theoretical target

```http
POST /api/v1/leveraged-etf/calculations
```

Request:

```json
{
  "relationship_id": "rel_nvda_nvdl_2x",
  "reference_version_id": "refv_01J...",
  "input_side": "underlying",
  "target_price": "180.00"
}
```

Fields:

| Name | Type | Required | Rules |
|---|---|---:|---|
| `relationship_id` | string | yes | Must name an active daily-leverage relationship |
| `reference_version_id` | string | yes | Must be the current active version for that relationship |
| `input_side` | enum | yes | `underlying` or `leveraged_product` |
| `target_price` | decimal string | yes | Finite and greater than zero; maximum scale/size defined in OpenAPI |

The client never sends reference prices or a leverage factor. The server loads them from the named immutable version and verifies that version is still active. This prevents a UI from displaying one reference and calculating with another after an operational correction.

Forward response `200`:

```json
{
  "data": {
    "formula_version": "leveraged-daily-linear/v1",
    "relationship_id": "rel_nvda_nvdl_2x",
    "leverage_factor": "2",
    "objective_period": "daily",
    "input": {
      "side": "underlying",
      "instrument_id": "ins_nvda_xnas",
      "symbol": "NVDA",
      "target_price": "180.00"
    },
    "output": {
      "side": "leveraged_product",
      "instrument_id": "ins_nvdl_xnas",
      "symbol": "NVDL",
      "theoretical_target_price": "89.41176471"
    },
    "underlying_return": "0.0588235294117647",
    "leveraged_return": "0.1176470588235294",
    "reference": {
      "id": "refv_01J...",
      "trading_date": "2026-09-08",
      "session": "us_overnight_open",
      "underlying_price": "170.00000000",
      "leveraged_product_price": "80.00000000",
      "underlying_quoted_at": "2026-09-08T00:00:02Z",
      "leveraged_product_quoted_at": "2026-09-08T00:00:04Z",
      "provider": "mock"
    },
    "calculated_at": "2026-09-08T14:30:00Z",
    "warnings": [
      {
        "code": "THEORETICAL_SINGLE_DAY_ONLY",
        "message": "This estimate uses a single-day linear leverage relationship and is not a multi-day price forecast."
      }
    ]
  },
  "meta": {
    "request_id": "req_01J..."
  }
}
```

Reverse requests set `input_side` to `leveraged_product`; the response swaps input/output sides and calculates the implied underlying return and target.

The API returns `CALCULATION_OUT_OF_DOMAIN` when the computed price is non-positive. The response may include safe structured context such as the violated boundary but must not return the invalid value as a price result.

## 6. Profit Ratio endpoints

These endpoints become release-blocking only after the metric definition and provider methodology are approved. They must still work against deterministic Mock data during development.

### 6.1 Get latest Profit Ratio

```http
GET /api/v1/profit-ratio/instruments/{instrument_id}/latest
```

Response `200`:

```json
{
  "data": {
    "instrument": {
      "id": "ins_nvda_xnas",
      "symbol": "NVDA",
      "name": "NVIDIA Corporation",
      "instrument_type": "stock",
      "exchange_mic": "XNAS",
      "currency": "USD",
      "status": "active",
      "capabilities": {
        "leveraged_relationships": true,
        "profit_ratio": true
      }
    },
    "ratio": "0.826",
    "observed_at": "2026-09-04T20:00:00Z",
    "trading_date": "2026-09-04",
    "freshness": "current",
    "methodology": {
      "id": "provider-cost-basis-estimate",
      "version": "1",
      "display_name": "Provider-estimated profitable cost-basis ratio"
    },
    "provider": "mock"
  },
  "meta": {
    "request_id": "req_01J..."
  }
}
```

Unsupported instruments return `404 INSTRUMENT_NOT_FOUND` only if the instrument itself does not exist. An existing instrument without this capability returns a typed `422` error with code `PROFIT_RATIO_UNSUPPORTED`.

### 6.2 Get Profit Ratio history and price comparison

```http
GET /api/v1/profit-ratio/instruments/{instrument_id}/history?start=2026-06-01&end=2026-09-04&interval=1d&include_price=true
```

Query parameters:

| Name | Type | Required | Rules |
|---|---|---:|---|
| `start` | date | yes | Inclusive exchange trading date |
| `end` | date | yes | Inclusive exchange trading date; not before `start` |
| `interval` | enum | no | Initially `1d`; more intervals require stored source resolution |
| `include_price` | boolean | no | Default `true` |

Response `200`:

```json
{
  "data": {
    "instrument_id": "ins_nvda_xnas",
    "symbol": "NVDA",
    "interval": "1d",
    "timezone": "America/New_York",
    "methodology": {
      "id": "provider-cost-basis-estimate",
      "version": "1",
      "display_name": "Provider-estimated profitable cost-basis ratio"
    },
    "profit_ratio_series": [
      {
        "timestamp": "2026-09-03T20:00:00Z",
        "trading_date": "2026-09-03",
        "ratio": "0.771",
        "quality": "final"
      },
      {
        "timestamp": "2026-09-04T20:00:00Z",
        "trading_date": "2026-09-04",
        "ratio": "0.826",
        "quality": "final"
      }
    ],
    "price_series": [
      {
        "timestamp": "2026-09-03T20:00:00Z",
        "trading_date": "2026-09-03",
        "close": "168.37",
        "adjustment": "unadjusted"
      },
      {
        "timestamp": "2026-09-04T20:00:00Z",
        "trading_date": "2026-09-04",
        "close": "170.00",
        "adjustment": "unadjusted"
      }
    ],
    "gaps": [],
    "as_of": "2026-09-05T02:15:00Z",
    "provider": "mock"
  },
  "meta": {
    "request_id": "req_01J..."
  }
}
```

The two arrays remain separate. Clients align them using `trading_date`/`timestamp` and the declared interval. The API does not fabricate points or silently forward-fill missing ratios. `gaps` reports known missing periods or methodology breaks.

### 6.3 Future Profit Ratio OHLC

A future endpoint may expose genuine OHLC bars:

```text
GET /api/v1/profit-ratio/instruments/{instrument_id}/bars
```

It is not part of the initial contract. It may be specified only after source sampling frequency, bar boundaries, partial-bar behavior, and methodology are approved.

## 7. Service endpoints

### 7.1 Phase 1 health

```http
GET /health
```

Returns `200` when the API process is serving requests and identifies the active market-data adapter as `mock`. It does not call an external provider.

### 7.2 Future liveness

```http
GET /health/live
```

Returns `200` if the API process is running. It does not call a provider.

### 7.3 Future readiness

```http
GET /health/ready
```

Returns `200` when dependencies required to serve stored reads are available, otherwise `503`. A live provider outage alone does not make the read API unready if stored data can still be served.

Detailed provider, database, job, and secret diagnostics must not be public.

## 8. Versioning and compatibility policy

- Additive optional response fields are backward-compatible within `/api/v1`.
- Removing/renaming fields, changing decimal units, changing enum meaning, or changing formula behavior is breaking.
- Formula changes receive a new `formula_version`; methodology changes receive a new methodology version even when the route remains stable.
- Breaking HTTP changes use `/api/v2` or a documented, time-bounded migration.
- The repository stores a reviewed OpenAPI snapshot and checks generated-client drift in CI after implementation begins.

## 9. Internal boundaries

The following are deliberately absent from the public API:

- Provider credentials and raw provider error bodies.
- Raw Futu/OpenD connections or SDK objects.
- Capture triggers and manual reference activation.
- Database IDs that expose sequential internals, if avoidable.
- Arbitrary SQL/report endpoints.
- User-supplied reference prices or leverage factors for authoritative results.

Operational commands may be implemented as authenticated administrative tools or direct worker commands later, with their own threat model and audit trail.

# TraFriend Architecture

## 1. Architecture goals

TraFriend should begin as a small, deployable system without baking vendor, framework, or UI concerns into its financial rules. The design optimizes for:

- Correct and reproducible financial calculations.
- Strict separation between the browser, backend, database, and market data providers.
- Local and CI development without live market data.
- Auditable Daily Close Anchors and provider provenance.
- Incremental addition of new financial tools.
- A straightforward path from a modular monolith to separate services only if scale or ownership later requires it.

## 2. Chosen system shape

Use a **monorepo with independently deployable frontend and backend applications**. The backend is a **modular monolith** with ports-and-adapters boundaries. PostgreSQL persists immutable Daily Close Anchors, the curated leveraged-product universe, and separately sourced market rankings. Daily capture is an independently runnable application command; an external platform scheduler may invoke it without placing a loop in FastAPI.

```text
Browser
   |
   | HTTPS / JSON
   v
Next.js web application (Vercel)
   |
   | HTTPS / versioned public API
   v
FastAPI application ----------------------> PostgreSQL
   |                                           ^
   | application ports                         |
   v                                           |
Market-data adapters <--- scheduled worker ----+
   |
   +--> Mock provider (local and CI)
   +--> Alpaca REST adapter (manual validation only)
   +--> Futu/OpenD adapter (future option)
   +--> Tiingo/Databento adapter (future option)
```

The browser never connects directly to a market provider or the database. Calculation requests use reference data already captured by the backend and therefore do not depend on a live quote request.

## 3. Repository layout

The following is the repository structure established in Phase 1, with later directories identified where relevant.

```text
TraFriend/
├── README.md                         # User-facing product overview only
├── AGENTS.md                         # Repository contribution rules
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── API_SPEC.md
│   ├── DATA_MODEL.md
│   ├── DEVELOPMENT.md
│   ├── adr/                          # Short architecture decision records
│   └── operations/                   # Runbooks added with live infrastructure
├── apps/
│   └── web/                          # Next.js + TypeScript application
│       ├── src/app/                  # App Router routes/layouts
│       ├── src/features/
│       │   ├── leveraged-calculator/
│       │   └── profit-ratio/
│       ├── src/components/           # Shared composed components
│       ├── src/components/ui/        # shadcn/ui-owned primitives
│       ├── src/i18n/                  # Typed locale config, dictionaries, and providers
│       └── src/lib/api/              # Typed API client; generated schemas later
├── services/
│   └── api/                          # Python + FastAPI application
│       ├── pyproject.toml
│       ├── migrations/               # Alembic Daily Close Anchor schema history
│       ├── src/trafriend_api/
│       │   ├── main.py               # Composition root only
│       │   ├── presentation/http/    # FastAPI routers, schemas, exception mapping
│       │   ├── application/
│       │   │   ├── services/         # Use-case orchestration
│       │   │   ├── ports/            # Provider/repository/clock/calendar interfaces
│       │   │   └── dto/              # Added when use-case DTOs expand
│       │   ├── domain/               # Pure models, formulas, and domain errors
│       │   ├── infrastructure/
│       │   │   ├── persistence/      # PostgreSQL repositories and mappings
│       │   │   ├── market_data/
│       │   │   │   ├── mock/
│       │   │   │   └── futu/         # Later; provider-specific code stays here
│       │   │   ├── calendar/
│       │   │   └── observability/
│       │   ├── jobs/                 # Added with scheduled capture
│       │   └── settings.py           # Backend-only validated settings
│       └── tests/
│           ├── unit/                 # Pure domain and application tests
│           ├── integration/          # DB/HTTP/adapter tests
│           ├── contract/             # Common provider conformance suite
│           └── fixtures/             # Added as the Mock catalog expands
├── packages/
│   └── api-client/                   # Optional generated TS client; no domain formula
├── scripts/                          # Thin, documented developer/CI entry points
├── .github/workflows/                # CI and deployment workflows
└── .env.example                      # Names only; never real secret values
```

Do not create a generic shared domain package spanning Python and TypeScript. The Python domain module is authoritative for calculations. The frontend consumes the versioned API and may share generated transport types, not a second implementation of the financial formula.

## 4. Backend boundaries and dependency rules

### 4.1 Domain layer

The domain layer contains immutable value objects, calculation functions, invariants, and domain errors. It must not import FastAPI, an ORM, a provider SDK, environment settings, or UI concepts.

The leveraged ETF module owns:

- Signed leverage-factor validation.
- Forward and reverse formulas.
- Decimal precision and model-domain checks.
- Reference-set eligibility rules that are genuinely financial/domain rules.

The Profit Ratio module owns:

- Ratio bounds and methodology identity.
- Observation/bar invariants.
- Series ordering and gap semantics.

### 4.2 Application layer

The application layer implements use cases and declares ports. It may depend on domain modules, but not concrete infrastructure. Initial use cases include:

- Search instruments.
- Resolve an instrument and its underlying/leveraged relationships.
- Get the active Daily Close Anchor.
- Calculate a leveraged or underlying theoretical target.
- Capture and publish daily close anchors.
- Resolve all cached anchors for one underlying and capture only missing latest-session pairs on demand.
- Calculate every available leveraged child from one underlying target.
- Read an independently sourced popular-underlying ranking.
- Get current and historical Profit Ratio data.

Clock and trading-calendar behavior are injected ports so tests can control dates, daylight saving transitions, and holidays.

### 4.3 Presentation layer

FastAPI routers translate HTTP input into application DTOs and translate results/errors into the API envelope. Routers do not contain formulas, SQL, provider SDK calls, or business decisions.

The OpenAPI document generated by FastAPI is the authoritative transport schema. A TypeScript client/schema can be generated from a committed, reviewed OpenAPI snapshot. Breaking HTTP changes require a new API version or a documented migration.

### 4.4 Infrastructure layer

Infrastructure contains concrete provider adapters, repositories, calendar libraries, logging, and external clients. ORM records and provider response objects are mapped at the boundary; they do not escape into application or domain code.

The composition root selects concrete adapters from validated backend settings. No module should instantiate a provider client at import time.

## 5. Provider abstraction

Use small capability-oriented interfaces instead of one all-purpose vendor interface:

```text
InstrumentCatalogPort
  search(query, limit) -> instruments
  get_by_provider_key(key) -> instrument metadata

QuoteProviderPort
  get_quotes(instrument_keys) -> timestamped quote results

ProfitRatioProviderPort
  get_latest(instrument_key) -> observation
  get_history(instrument_key, start, end, interval) -> observations

TradingCalendarPort
  session_for(timestamp) -> session/trading date
  capture_window(trading_date) -> time window

CompletedSessionCalendar
  latest_completed_session(timestamp) -> trading date and exchange close instant

DailyCloseMarketDataProvider
  get_daily_close_bars(symbols, start_date, end_date) -> normalized daily closes

DailyCloseAnchorRepository
  save(anchor) -> immutable version
  latest(relationship_id) -> anchor

LeveragedRelationshipCatalog
  search_instruments(query, limit) -> provider-independent metadata
  get_relationship(id) -> verified signed-leverage metadata
  get_leveraged_relationships(instrument_id) -> all active children

MarketRankingRepository
  get_dataset(period, ranking_type, limit) -> sourced underlyings
  replace_verified_rows(rows) -> atomic importer operation

OvernightMarketDataProvider
  get_latest_quotes(symbols) -> normalized quotes
  get_overnight_snapshot(symbols, target_timestamp) -> normalized quotes
  get_overnight_bars(symbols, start, end, timeframe) -> normalized bars

HistoricalOvernightMarketDataProvider
  get_historical_overnight_bars(symbols, start, end, timeframe) -> normalized OHLCV bars
  get_historical_overnight_quotes(symbols, start, end) -> normalized two-sided quotes

OvernightReferenceRepository
  save(capture) -> immutable version
  latest(trading_date, reference_type, symbols) -> capture
```

Repository ports are separate from external-data ports. This prevents vendor switching from affecting storage or use cases.

The historical interface is a bounded, read-only manual-diagnostic port. It is not used by calculator reads or public routes and does not expand the production `OVERNIGHT_OPEN` window.

Every market data adapter must:

- Map vendor identifiers to canonical internal instrument IDs.
- Return normalized decimal values, UTC timestamps, currency, source name, and a source record identifier when available.
- Preserve provider-specific metadata only in a bounded provenance field.
- Distinguish not-found, unsupported, rate-limited, authentication, transport, stale-data, and malformed-data failures.
- Declare capabilities instead of emulating unavailable data.
- Pass the same provider contract test suite.
- Keep credentials in backend-only settings and redact secrets from logs and exceptions.

The Mock provider is a first-class adapter, not scattered test conditionals. It reads deterministic fixtures for normal, inverse, stale, missing, partial, holiday, boundary, delayed, provider-failure, missing-open, and out-of-sync scenarios. Local development and CI default to Mock and require no network or vendor account.

The first real adapter uses Alpaca's hosted HTTP API. Daily close validation uses unadjusted `1Day` bars from the configured `sip` or `iex` feed and preserves explicit quality. Separately, overnight diagnostics use the derived `overnight` latest-quote feed and source-native `boats` history. Feed and quality are separate configuration; delayed data is never relabeled real-time.

Provider feasibility, cost, operational tradeoffs, and data rights are tracked in `OVERNIGHT_DATA_PROVIDER_RESEARCH.md`. The Alpaca adapter is approved only for manual validation until the required public-display/redistribution rights are confirmed in writing.

## 6. Daily Close Anchor lifecycle

### 6.1 Calculator anchor

`DAILY_CLOSE_ANCHOR` is the calculator's only reference method. It contains the regular-session closing prices of the underlying and leveraged ETF for one same, latest completed XNYS trading date. The calendar adapter determines that session from an aware current instant, including holidays and special closes; the service does not infer it from wall-clock hour or weekday logic.

The provider returns normalized `DailyCloseBar` values. The application service accepts exactly one expected-date bar per symbol, validates positive Decimal closes, provider/feed provenance, usable quality, and non-future timestamps, then stores an immutable `COMPLETE` anchor. `PARTIAL` and `UNAVAILABLE` remain explicit capture outcomes but are not published to the calculator table. A prior-date response indicates provider lag and is rejected rather than used as fallback. On reads, the service compares the persisted anchor date with the calendar's latest completed session, so an older complete row cannot become a silent fallback after a failed newer capture.

### 6.2 Capture workflow

```text
External scheduler or manual command
  -> resolve the latest completed exchange session
  -> resolve curated signed leverage metadata
  -> request the two daily bars in one provider batch
  -> normalize and validate same-date closes
  -> assemble each underlying/leveraged pair
  -> transactionally insert or reuse the immutable pair
  -> recreate the repository and verify a DB-only calculation
```

Validation includes positive prices, expected currency, supported instrument status, expected trading date, provider/feed provenance, market timestamp, and observation time. A pair is atomic: one valid close and one missing/rejected close is not calculator-eligible.

The legacy manual command captures one relationship per invocation. The
`capture_popular_daily_closes` command expands each selected underlying into every
active catalog relationship and isolates a missing child from unrelated valid
pairs. A ranked underlying with no active supported relationship is retained in
the ranking but reported as `SKIPPED_NO_SUPPORTED_PRODUCT`; it causes no provider
request and is neither unavailable nor retryable. A supported relationship's
logical anchor identity is `(underlying_symbol, leveraged_product_symbol,
trading_date)`. An identical retry returns the existing row. Materially different
immutable facts for the same identity raise `AnchorConflictError`; no update
occurs. A database trigger rejects direct row updates and deletes. A future
correction workflow will require an explicit reviewed migration/version policy
rather than weakening this invariant.

### 6.3 Read workflow

A calculation loads the active relationship from `LeveragedRelationshipCatalog` and the latest stored complete Daily Close Anchor through `DailyCloseAnchorRepository`. With `DATABASE_URL`, the composition root selects `PostgreSQLLeveragedUniverseRepository`, `PostgreSQLMarketRankingRepository`, and `PostgreSQLDailyCloseAnchorRepository`; without it, deterministic local/CI tests retain in-memory adapters. Anchor and calculation requests do not call the broad market-data provider or Alpaca. The pure domain formula returns the result with the exact anchor version.

Metadata search is catalog-only and has distinct underlying and leveraged-product
ports/endpoints; the combined endpoint remains compatibility-only. Selecting either
kind of supported symbol invokes the on-demand resolve use case: it resolves the
canonical underlying, checks every current relationship anchor first, calls the
configured daily-close provider only for missing latest-session pairs, persists
complete pairs, and returns an explicit unavailable row for missing children. With a
PostgreSQL configuration, the Mock adapter is read-only for this workflow so it
cannot contaminate persisted real anchors. The browser never calls Alpaca directly.

The provider-independent catalog is populated by immutable, source-attributed
snapshot migrations. Migration `20260907_0007` broadens search beyond Popular to
the complete verified 2026-09-07 daily single-stock universe: 236 stock underlyings,
QQQ and SOXX, and 493 leveraged products. Candidate discovery may use Alpaca's active
asset directory, but inclusion still requires an explicit daily factor and an
official issuer source. Search never infers a relationship or calls Alpaca per
keystroke.

If the expected completed-session version is unavailable, partial, stale, mixed-date, or lagging, the application returns a typed data-availability error. It must not silently substitute a prior session. A future explicitly labeled historical calculator may allow the caller to choose an older trading date.

### 6.4 Separate overnight diagnostics

`OVERNIGHT_OPEN` and `OVERNIGHT_SNAPSHOT` remain implemented behind `OvernightMarketDataProvider` and `HistoricalOvernightMarketDataProvider` for research and diagnostics. Their 20:00-04:00 ET session mapping, 20:00-20:15 opening window, 20:05 snapshot target, midpoint basis, and skew rules are unchanged. They are not calculator inputs and cannot be substituted for `DAILY_CLOSE_ANCHOR`.

### 6.5 Scheduling

Scheduling stays outside the request-serving web process.
`run_daily_market_update` is the production orchestration entry point: it refreshes
the current month-to-date ranking and then delegates Daily Close work to the
existing idempotent popular-capture service. It asks the exchange calendar for the
latest completed session on every invocation, so DST, holidays, weekends, and
early closes are not encoded in cron time. An already-current invocation exits
successfully as `SKIPPED`; a run containing only `INSERTED`, `EXISTING`, and
`SKIPPED_NO_SUPPORTED_PRODUCT` outcomes is complete and exits zero. Provider
publication lag or another supported-relationship failure is
`PARTIAL_RETRYABLE`. The lower-level `capture_popular_daily_closes` command remains
available for initialization and targeted operations. No command contains a
persistent loop and FastAPI never starts a scheduler.

Market rankings are calculated independently from the anchor workflow. `MarketRankingService` obtains Alpaca's active U.S.-equity asset universe through `RankingMarketDataProvider`, applies explicit security exclusions, requests raw SIP daily bars in batches, and calculates `SUM(daily VWAP * daily share volume)` only for symbols complete across every exchange-calendar session. The original September 2026 dataset retains its explicit `SEPTEMBER_TO_DATE` state; later incomplete periods use `MONTH_TO_DATE`. `MarketRankingRepository.replace_verified_rows` atomically replaces one effective period/type, preserving ranking/anchor separation and rerun idempotency. A source-attributed CSV importer remains as an alternate ingestion boundary.

The PostgreSQL repository already combines a transaction-scoped advisory lock with unique logical-identity and relationship/version constraints. Store all timestamps as timezone-aware instants and the exchange trading date separately.

## 7. Calculator design

The calculator is a pure transformation:

```text
(Daily Close Anchor, signed leverage factor, input side, target Decimal)
    -> calculation result or typed domain error
```

Use Python `Decimal`; never binary floating point for authoritative financial calculations. A proposed baseline is sufficient internal precision for provider price scales, with API prices serialized as decimal strings. Display rounding is instrument-aware where known and otherwise follows a documented default. Rounding policy must be confirmed in an architecture decision record before implementation.

Important invariants:

- Anchor and target prices are finite and greater than zero.
- Leverage is finite, signed, and not zero.
- The relationship connects the two anchor instruments.
- The calculation uses one complete same-date anchor version.
- A theoretical result less than or equal to zero is outside the model domain.
- Reverse results must also produce a positive underlying price.

Tests should include examples for `+2x`, `+3x`, `-1x`, `-2x`, and `-3x`; zero moves; forward/reverse round trips; decimal/rounding boundaries; and moves that cross the non-positive theoretical-price boundary.

## 8. Profit Ratio architecture

The 2026-09-08 vertical slice adds `ProfitRatioService`, narrow repository/capture/
calendar ports, `PostgreSQLProfitRatioRepository`, and a QQQ-only daily endpoint UI.
`capture_profit_ratio` is a finite worker command, separate from ranking and
leveraged-anchor capture. The normal read service has no provider dependency wired.
Without DATABASE_URL, explicit deterministic Mock endpoint fixtures are used; with
PostgreSQL, only persisted records are read. There is no live float/seed/state
pipeline yet, so real price captures retain null ratios with explicit input gaps.
The pure Decimal turnover-model candidate is gated and not a validated production
method. See ADR 0006 and `PROFIT_RATIO_OPERATIONS.md` for boundaries and scheduling.

The new reviewed `openapi-profit-ratio.json` snapshot and generated frontend types
are produced by `export_profit_ratio_contract`; a deterministic drift test compares
them with the actual FastAPI schemas. Legacy prototype types remain separate.

Profit Ratio uses its own domain, application service, provider port, repository, and API routes. This allows its methodology and data source to evolve without changing the calculator.

The ingestion path stores raw normalized observations with methodology versions. Read models may later aggregate observations into OHLC bars only when sampling frequency supports genuine open, high, low, and close values. Price history and Profit Ratio history remain separate series joined for presentation by an explicit interval/timezone rule.

The public API should expose gaps, partial intervals, and methodology transitions. It should not silently forward-fill missing ratios or join values from incompatible methodology versions.

## 9. Frontend architecture

The Next.js application is organized by product feature. Each feature contains its own server/client components, view models, validation messages, and tests. Shared shadcn/ui primitives stay generic and contain no market logic.

Guidelines:

- Prefer server-side reads for initial public pages where it improves performance and discoverability; use client components for search interactions, target input, and charts.
- All data comes through the FastAPI public API. Do not embed provider SDKs or credentials in Next.js server actions as an alternate data path.
- The frontend may validate shape and provide immediate input feedback, but the backend remains authoritative for the formula and reference choice.
- Keep percentage/price formatting separate from calculation.
- Treat decimal values from the API as strings until parsed by a decimal-safe display utility; do not silently introduce IEEE-754 rounding into displayed inputs/outputs.
- Every data panel includes loading, empty, stale, unavailable, and error states.
- Charts provide accessible summaries or a data table and do not imply continuity across missing points.
- Centralize the API base URL and only expose genuinely public configuration to browser code.

### 9.1 Internationalization

The web application supports English (`en`) and Simplified Chinese (`zh-CN`). A typed dictionary under `src/i18n/` is the source of truth for user-facing frontend copy. New pages, features, accessible labels, empty/error states, and metadata must add both locale entries in the same change; feature components must not introduce independent translation tables.

The selected locale is stored in the non-sensitive `trafriend_locale` preference cookie. Server components read it to render page content and metadata in the selected language. The root locale provider supplies the same locale to interactive client components, updates the document `lang` attribute, and refreshes the server-component tree after a switch. Locale preference is a UI concern only and is never sent to a market-data provider.

Stable API error and warning codes are mapped to localized frontend messages. Vendor or backend prose is not used as localized UI copy. Symbols, canonical IDs, provider labels, formula versions, and market values remain source data rather than translated content. Locale-sensitive date and currency presentation belongs in formatting code, never in financial calculations.

## 10. API and cache strategy

- Public endpoints live under `/api/v1`.
- GET responses may use short-lived HTTP/CDN caching and ETags where freshness semantics are clear.
- Calculation POST requests are deterministic and side-effect free but should not be cached publicly by default because target inputs appear in the request.
- Anchor and analytics responses include timestamps, `trading_date`, status, and provenance.
- Provider calls happen during ingestion, not on public read endpoints, except for a future explicitly designed live-data feature.
- Redis is not required initially. Introduce it only for demonstrated cross-instance cache, rate-limit, or job-queue needs.

## 11. Security architecture

Trust boundaries are the browser/API boundary, API/database boundary, and backend/provider boundary.

- Provider credentials are injected only into backend or worker processes from environment secrets or a managed secret store.
- Never prefix secrets with `NEXT_PUBLIC_`, serialize them into API responses, commit them, place them in fixtures, or log request headers containing them.
- Vercel hosts the frontend only. Backend and Futu/OpenD connectivity, if used, require separately secured hosting appropriate to the provider's networking/runtime constraints.
- Validate all query/body fields and cap search text, list limits, date ranges, and chart resolution.
- Add rate limiting at the backend or edge before broad public release.
- Restrict internal job and administrative endpoints; prefer direct worker commands over public scheduler endpoints.
- Apply least-privilege database roles and encrypted transport.
- Include dependency, secret, and static checks in CI before production deployment.

## 12. Testing strategy

### 12.1 Backend

- **Unit:** formulas, value objects, completed-session mapping, close-anchor selection, Profit Ratio invariants.
- **Property/boundary:** forward/reverse equivalence within policy, signed leverage, extreme permitted decimals, non-positive output domains.
- **Application:** use cases with fake clocks, repositories, calendars, and provider ports.
- **Provider contract:** the same conformance suite runs against Mock and each real adapter; live vendor tests are opt-in and not required for ordinary CI.
- **Integration:** PostgreSQL repositories, migrations, FastAPI schemas/error mapping, capture idempotency and transactions.
- **End-to-end:** search-to-calculation and Profit Ratio history flows against deterministic seeded data.

### 12.2 Frontend

- Component tests for input direction, formatting, disclosures, and all data states.
- Contract tests against the generated client/OpenAPI fixture.
- End-to-end browser tests for keyboard-accessible core journeys.
- Visual regression checks for key mobile and desktop states when UI development begins.

No test in the default suite may require live market credentials or assume the market is open.

## 13. Observability and operations

Use structured logs with a request/run correlation ID. Important events include selected anchor version, capture outcome, provider error class, and methodology version; do not log secrets or unnecessary full vendor payloads.

Initial metrics and alerts:

- Valid Daily Close Anchor coverage by trading date.
- Capture completion latency from scheduled window.
- Partial/failed pairs and retry exhaustion.
- Provider latency, rate limiting, authentication failures, and stale quotes.
- API p50/p95/p99 latency and error rate by route/error code.
- Profit Ratio last-success age and ingestion gaps.

Health endpoints distinguish process liveness from readiness. Provider health should not make calculation reads unready when stored reference data remains valid.

## 14. Deployment evolution

### Stage 1: local and CI

- Next.js dev process.
- FastAPI dev process.
- Mock provider with fixtures.
- In-memory repositories for early unit/application work, followed quickly by PostgreSQL integration tests when persistence begins.

### Stage 2: preview

- Frontend preview on Vercel.
- Separately hosted API and worker.
- Managed PostgreSQL.
- Mock or sandbox provider data.

### Stage 3: production

- Vercel frontend.
- Independently scaled backend API and worker/scheduler.
- Managed PostgreSQL with backups and migration controls.
- Licensed/configured live provider adapter, private connectivity as required, monitoring, and secret management.

## 15. Extension pattern for new financial tools

Each new tool should add a vertical backend module and a frontend feature rather than expanding a universal analytics service:

1. Define terminology, assumptions, non-goals, and formula/data provenance.
2. Add domain types and pure rules.
3. Add narrow application ports and use cases.
4. Implement Mock fixtures and automated tests.
5. Add infrastructure adapters and persistence mappings.
6. Publish versioned API contracts.
7. Build a feature-isolated UI with disclosures and data states.

Cross-tool code belongs in shared modules only after there is a demonstrated stable abstraction.

## 16. Primary technical risks

| Risk | Consequence | Mitigation |
|---|---|---|
| Incorrect completed-session mapping | A calculation uses the wrong day's anchor | Exchange calendar port, before/after-close, weekend, holiday, and early-close tests |
| Missing, mixed-date, or lagging daily bars | Pair is not a coherent anchor | Exact expected-date validation, explicit partial/unavailable states, no prior-session fallback |
| Daily leverage model misunderstood as a forecast | User over-trusts output | Prominent single-day wording, return assumptions and references in every result, no multi-day UI |
| Negative theoretical values at extreme moves | Nonsensical prices are displayed | Enforce model-domain errors and test boundaries |
| Provider lock-in or vendor SDK leakage | Expensive replacement and brittle tests | Narrow ports, normalized DTOs, contract suite, infrastructure-only SDK imports |
| Market data licensing or redistribution constraints | Product or deployment cannot legally ship | Confirm data rights before provider selection; store/expose only permitted fields |
| Profit Ratio is undefined or provider-specific | Misleading or discontinuous history | Approve definition and methodology version; keep provenance; never merge incompatible series silently |
| Corporate actions and relationship changes | Broken historical continuity | Effective-dated relationships, immutable versions, adjustment/methodology metadata |
| Secret exposure through frontend or logs | Provider/account compromise | Backend-only secrets, redaction, build-time scans, least privilege |
| Frontend/backend decimal drift | Results differ across layers | One authoritative Python formula, decimal strings in transport, generated API types |
| Scheduled job duplication or partial writes | Multiple anchors or unusable references | Locks, uniqueness constraints, idempotent runs, transactions, pair-level status |
| Live provider outage | Missing reference day | Bounded retry and alerting; clear unavailable state; no silent stale fallback |

## 17. Required architecture decisions before implementation milestones

Record material choices in `docs/adr/` as short decision records. The first decisions should cover:

1. Decimal precision, serialization, and display rounding.
2. Overnight-session definition, quote field, freshness, and pair timestamp-skew limits.
3. Market calendar library and observed holiday policy.
4. Profit Ratio definition, methodology/version semantics, and data source rights.
5. Provider adapter selection and Futu/OpenD deployment constraints.
6. Scheduler/worker mechanism and production idempotency strategy.

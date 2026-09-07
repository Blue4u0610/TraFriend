# Local Development

## Phase 1 stack

- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS 4, and shadcn/ui.
- Backend: Python 3.9+, FastAPI, Pydantic 2, Uvicorn, SQLAlchemy 2, Alembic, psycopg 3, and pytest.
- Data: deterministic in-memory Mock mode when `DATABASE_URL` is absent; PostgreSQL-backed universe metadata, rankings, and Daily Close Anchors when it is set; optional Alpaca REST capture and overnight diagnostics.
- Not included: Futu/OpenD, an in-process scheduler, authentication, or Profit Ratio production data.

The frontend and backend run as separate applications. Their dependencies and commands are intentionally independent.

## Prerequisites

- Node.js 22 LTS and npm.
- Python 3.9 or later.
- PostgreSQL for persistent Daily Close Anchors. A GUI client is optional and not required.

Verify the runtimes:

```bash
node --version
npm --version
python3 --version
```

## Backend setup

From the repository root:

```bash
cd services/api
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
```

Start the API:

```bash
.venv/bin/uvicorn trafriend_api.main:app --reload --host 127.0.0.1 --port 8010
```

Useful local URLs:

- Health: `http://127.0.0.1:8010/health`
- OpenAPI: `http://127.0.0.1:8010/openapi.json`
- Interactive API docs: `http://127.0.0.1:8010/docs`

Without `DATABASE_URL`, the public API keeps deterministic in-memory Mock anchors and needs no market-data account or database. With `DATABASE_URL`, catalog search, ranking reads, and calculator anchors use PostgreSQL. Normal calculations never request Alpaca. A selected-symbol resolve may capture only a missing latest-session pair when `TRAFRIEND_DAILY_CLOSE_PROVIDER=alpaca`; the safe default remains `mock`.

## Local PostgreSQL setup

Check an existing installation before changing it:

```bash
psql --version
pg_isready -h localhost -p 5432
```

If an installer placed binaries outside `PATH`, invoke its `bin/psql` and `bin/pg_isready` directly. Start the server using its existing installation method (for example, the vendor service or `brew services`); TraFriend does not require Docker, DBeaver, or pgAdmin.

Create a least-privilege local application role and dedicated database from an administrator session if they do not already exist:

```sql
CREATE ROLE trafriend_app LOGIN PASSWORD 'choose-a-local-password';
CREATE DATABASE trafriend_dev OWNER trafriend_app;
```

Set the credential-bearing URL only in the backend process environment:

```bash
export DATABASE_URL='postgresql+psycopg://trafriend_app:your-local-password@localhost:5432/trafriend_dev'
```

Apply the schema from `services/api`:

```bash
.venv/bin/alembic upgrade head
```

The migrations create `daily_close_anchors`, `underlyings`, `leveraged_products`, and `market_rankings`. `alembic downgrade base` is supported for a disposable database, but it destroys stored anchors and must not be used on data that must be retained.

## Manual Daily Close Anchor capture

The calculator uses `DAILY_CLOSE_ANCHOR`, not an overnight open or snapshot. With `DATABASE_URL` and backend-only Alpaca credentials in the current process, capture one configured pair from `services/api`:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_daily_close_anchor \
  --underlying SNDK \
  --leveraged-etf SNXX
```

The command asks the XNYS calendar for the latest completed session, makes one batched `1Day` request with `feed=sip` and `adjustment=raw`, validates both symbols on exactly that trading date, and atomically persists the complete pair. It prints `INSERTED` on the first capture and `EXISTING` for an identical retry. A materially different close, leverage, provider, feed, date, or market timestamp for the same symbol-pair/date identity raises an explicit immutable conflict; it never updates the stored row. Missing, stale, mismatched-date, and unavailable pairs are not persisted.

Capture the second validated pair the same way:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_daily_close_anchor \
  --underlying QQQ \
  --leveraged-etf TQQQ
```

Each successful command disposes and recreates its database engine/repository, reads the anchor back, and runs the requested deterministic calculator scenario. The legacy read-only `validate_daily_close_anchor` command remains available for in-memory provider diagnostics.

Default environment overrides are:

```bash
export TRAFRIEND_ALPACA_DAILY_BARS_FEED=sip
export TRAFRIEND_ALPACA_DAILY_BARS_QUALITY=DELAYED
```

There is no provider fallback on calculation requests. The API selects PostgreSQL for
Daily Close Anchor reads when `DATABASE_URL` is configured. The selected-symbol
resolve use case is the only user-facing on-demand cache path; bulk capture remains
an explicit backend command. For a real local on-demand smoke test, start FastAPI
with the inherited database and credentials plus the non-secret adapter selection:

```bash
TRAFRIEND_DAILY_CLOSE_PROVIDER=alpaca \
.venv/bin/uvicorn trafriend_api.main:app --host 127.0.0.1 --port 8010
```

The default `mock` setting remains credential-free for CI and in-memory development.
When `DATABASE_URL` is present, that default may read persisted anchors but is not
allowed to write Mock closes into PostgreSQL; uncached rows remain explicitly
unavailable until the Alpaca adapter is selected.

## Leveraged universe and daily capture job

Migration `20260906_0002` establishes the catalog schema and its original eight
issuer/SEC-verified relationships. Migrations `20260907_0004` and
`20260907_0005` expand the verified 2026-09-07 snapshot to 264 active daily products
across 75 underlyings. This covers every directly mapped daily leveraged product
found for the 73 current September Top-100 stocks that have such a product, plus QQQ
and SOXX. The snapshot is based on official issuer catalogs plus active Alpaca assets;
it intentionally excludes option-income, different-index/basket, and non-daily-reset
products and must be refreshed as issuers launch or close funds.
Search is metadata-only and is exposed as separate underlying and leveraged-product
routes. The independently runnable capture command expands an underlying into all of
its products:

```bash
TRAFRIEND_DAILY_CLOSE_PROVIDER=alpaca \
.venv/bin/python -m trafriend_api.scripts.capture_popular_daily_closes \
  --symbols QQQ,SNDK
```

Omit `--symbols` only after a verified popular dataset is populated. The command
resolves the actual latest completed XNYS session, reports `COMPLETE`, `PARTIAL`,
or `FAILED`, and returns exit status 0, 2, or 1 respectively. It is safe to
retry: complete identical anchors report `EXISTING`; missing provider data for a
supported product remains unavailable without corrupting valid siblings.

A ranked underlying may legitimately have no active calculator-supported
leveraged product. Popular capture reports it separately as
`SKIPPED_NO_SUPPORTED_PRODUCT`, does not request market data for it, and does not
make an otherwise successful run partial or retryable. The ranking row remains
visible in the Popular API with a supported-product count of zero.

An external cron or deployment scheduler may invoke this command after the regular session and retry publication lag. Do not put a loop or sleep in FastAPI and do not hardcode a UTC close time. The command always asks the exchange calendar, which handles DST, weekends, holidays, and early closes.

## Month-to-date market-ranking calculation

The approved first-party metric is `SUM(daily VWAP * daily share volume)` across every completed September 2026 exchange session. The calculation uses Alpaca's active `us_equity` asset list and raw SIP `1Day` bars in batches of at most 200 symbols. A symbol is complete only when one positive VWAP/volume bar exists for every expected session; there is no close-price fallback for missing VWAP.

Run the authenticated, idempotent calculation from `services/api`:

```bash
.venv/bin/python -m trafriend_api.scripts.calculate_mtd_rankings
```

The command defaults to the month containing the latest completed NYSE session.
Use `--period 2026-09` for a deliberate historical rebuild. The legacy
`calculate_september_mtd_rankings` entry point remains an alias for that period.

The exchange calendar determines the completed session dates. The security filter excludes OTC records and metadata/name patterns that explicitly identify ETFs/ETNs, leveraged or inverse funds, warrants, rights, units, preferred shares, and blank-check acquisition companies. Alpaca does not expose a comprehensive security-type field, so ordinary-stock versus every possible non-leveraged ETF distinction cannot be proven perfectly from this interface. The curated ETF/product symbols are always excluded.

The command atomically replaces the selected period / `DOLLAR_TRADING_VOLUME` dataset; reruns cannot create duplicate ranks or symbols. September 2026 remains `SEPTEMBER_TO_DATE` until complete; other incomplete months use `MONTH_TO_DATE`.

## Market-ranking importer

The source-attributed CSV importer remains available for a separately licensed dataset. It is not needed for the Alpaca first-party build and never seeds placeholders.

Import a verified CSV containing `rank,symbol,trading_metric` only after recording its source and covered interval:

```bash
.venv/bin/python -m trafriend_api.scripts.import_market_rankings \
  --file /absolute/path/september-ranking.csv \
  --period 2026-09 \
  --period-start 2026-09-01 \
  --period-end 2026-09-04 \
  --period-status SEPTEMBER_TO_DATE \
  --source 'licensed-source-and-methodology'
```

The importer atomically replaces one period/type. It refuses to label September 2026 final before the month ends. Alpaca's standard account terms do not grant public redistribution rights; obtain written permission or a separate licensed data source before exposing stored real closes or rankings in a public product.

## Separate manual overnight diagnostics

The following commands preserve the earlier overnight research implementation. `OVERNIGHT_OPEN` and `OVERNIGHT_SNAPSHOT` are not calculator anchors and are not used by calculation API requests.

Run from `services/api`. Mock mode is deterministic and requires no credentials:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_overnight_reference \
  --provider mock \
  --symbols SNDK,SNXX \
  --date 2026-09-08 \
  --reference-type overnight-snapshot \
  --verbose
```

Test the missing-20:00-bar rule:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_overnight_reference \
  --provider mock \
  --mock-scenario missing_open \
  --symbols SNDK,SNXX \
  --date 2026-09-08 \
  --reference-type overnight-open \
  --verbose
```

The Mock output should show SNDK `1704.20` and SNXX `20.08` for the snapshot, with synchronized 20:05:01 ET market timestamps. It should show a 20:02 ET bar timestamp for the `missing_open` scenario. Exit status is `0` for a complete capture and `2` for partial/unavailable data.

### Configure Alpaca credentials

Copy `.env.example` only as a reference. The CLI reads the process environment; it does not automatically load a repository `.env` file. Supply secrets through the shell or a backend secret manager, never `apps/web` or a `NEXT_PUBLIC_*` variable:

```bash
export ALPACA_API_KEY='your-key-id'
export ALPACA_SECRET_KEY='your-secret-key'
```

The legacy backend names `TRAFRIEND_ALPACA_KEY_ID` and `TRAFRIEND_ALPACA_SECRET_KEY` remain accepted for compatibility, but the documented names above take precedence. Do not commit a populated `.env`; `.gitignore` excludes `.env` and `.env.*` except `.env.example`.

### Test real historical `OVERNIGHT_OPEN`

Choose a previous valid exchange trading date. On Alpaca's free plan, the requested bar window must end at least 15 minutes before the request. For example, the 2026-09-04 trading date maps to the overnight window beginning Thursday 2026-09-03 at 20:00 ET:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_overnight_reference \
  --provider alpaca \
  --symbols SNDK,SNXX \
  --date 2026-09-04 \
  --reference-type overnight-open \
  --verbose
```

The command requests one batch of `feed=boats`, searches from 20:00 through 20:15 ET on the prior calendar evening, and selects the first valid one-minute bar for each symbol. Free-plan defaults label those historical bars `DELAYED`. A missing 20:00 bar may select the first later bar inside the window; a bar before 20:00 or from a previous session is never used.

### Diagnose a complete historical overnight session

Use the separate read-only diagnostic command when investigating liquidity outside the production opening window or historical two-sided BOATS quotes. This does not capture a reference set or alter the 20:00-20:15 `OVERNIGHT_OPEN` policy:

```bash
.venv/bin/python -m trafriend_api.scripts.diagnose_overnight_history \
  --symbols SNDK,SNXX \
  --date 2026-09-04 \
  --quote-time 20:05 \
  --quote-window-seconds 60
```

The command requests the complete 20:00-04:00 ET session as `feed=boats` one-minute bars and a bounded historical quote window centered on the requested Eastern time. It reports OHLCV for the first bar, the final bar, and the valid two-sided quote closest to the target. Exact-distance quote ties choose the earlier timestamp. Historical quote and bar quality use the configured BOATS historical quality, which defaults to `DELAYED` for the free plan.

### Test live `OVERNIGHT_SNAPSHOT`

Run this close to 20:05 ET on a Sunday-through-Thursday evening whose following date is an XNYS trading day. From the 2026-09-05 development date, the next test window is Monday 2026-09-07 around 20:05 ET for trading date 2026-09-08; Sunday night is closed because Monday is Labor Day:

```bash
.venv/bin/python -m trafriend_api.scripts.capture_overnight_reference \
  --provider alpaca \
  --symbols SNDK,SNXX \
  --date 2026-09-08 \
  --reference-type overnight-snapshot \
  --verbose
```

Free-plan defaults make one batch latest-quotes request with `feed=overnight`, record the bid/ask midpoint, and label the value `REALTIME` while preserving the derived-feed provenance. `--verbose` prints the ET/UTC request window, normalized timestamps, selection/rejection reason, and synchronization difference. The capture is valid only if both symbols are present, fall within the configured target tolerance, and differ by no more than five seconds.

With an Algo Trader Plus entitlement, use source-native, immediate BOATS data explicitly:

```bash
export TRAFRIEND_ALPACA_SNAPSHOT_FEED=boats
export TRAFRIEND_ALPACA_SNAPSHOT_QUALITY=REALTIME
export TRAFRIEND_ALPACA_BARS_QUALITY=REALTIME
```

### Interpret capture results

- `REALTIME`: provider configuration declares immediate delivery. For free Alpaca snapshots, this is an indicative derived `overnight` quote, not a BOATS last trade.
- `DELAYED`: provider configuration declares delayed delivery; free BOATS historical data is delayed at least 15 minutes.
- `STALE`: the timestamp is outside the allowed session/capture window or synchronization tolerance; the value is rejected.
- `PARTIAL`: at least one requested symbol is available and at least one is missing/rejected. It cannot activate a reference pair.
- `UNAVAILABLE`: no requested symbol is usable, the exchange calendar says there is no session, or a provider failure prevented capture.

The command stores only an in-memory immutable capture version and prints it. It does not create a scheduler, public endpoint, or PostgreSQL write. Individual Alpaca API access does not grant permission to redistribute data on TraFriend's public website; review `OVERNIGHT_DATA_PROVIDER_RESEARCH.md` before real-data use.

## Frontend setup

In a second terminal, from the repository root:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`.

Use the language selector at the top right to switch between English and Simplified Chinese. The selection is saved in the `trafriend_locale` preference cookie. When adding frontend functionality, place every user-facing string—including metadata, accessibility labels, errors, loading/empty states, and disclosures—in both typed dictionaries under `apps/web/src/i18n/`; do not hard-code feature copy in components.

The development fallback API URL is `http://localhost:8010`. To override it locally, create `apps/web/.env.local` containing only:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8010
```

This variable is public by design because it contains only the TraFriend API origin. Never put a provider credential in a `NEXT_PUBLIC_*` variable.

## Verification commands

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
npm test
npm run build
```

Backend:

```bash
cd services/api
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Verify production-mode startup after a successful frontend build:

```bash
cd apps/web
npm run start
```

Verify API startup:

```bash
cd services/api
.venv/bin/uvicorn trafriend_api.main:app --host 127.0.0.1 --port 8010
```

## API surface

Phase 1 implements:

- `GET /health`
- `GET /api/v1/instruments/search`
- `GET /api/v1/instruments/{instrument_id}`
- `GET /api/v1/instruments/{instrument_id}/leveraged-products`
- `GET /api/v1/universe/search`
- `GET /api/v1/universe/underlyings/search`
- `GET /api/v1/universe/leveraged-products/search`
- `GET /api/v1/underlyings/{symbol}`
- `GET /api/v1/underlyings/{symbol}/leveraged-products`
- `POST /api/v1/underlyings/{symbol}/resolve`
- `POST /api/v1/underlyings/{symbol}/calculations`
- `GET /api/v1/popular`
- `GET /api/v1/leveraged-etf/relationships/{relationship_id}/anchor`
- `POST /api/v1/leveraged-etf/calculations`
- `GET /api/v1/profit-ratio/instruments/{instrument_id}/latest`
- `GET /api/v1/profit-ratio/instruments/{instrument_id}/history`

Mock close anchors and Profit Ratio points are deterministic. They are deliberately not presented as live market data.

## Troubleshooting

- If the dashboard says `API offline`, ensure Uvicorn is running on port 8000.
- If the leverage page was opened before Uvicorn, start the API and use the page's
  `Retry data` action. The QQQ workspace and Popular dataset recover without a full-page
  reload; metadata search reports its own loading, empty, and API-unavailable states.
- If browser requests are rejected by CORS after changing the frontend port, add the exact local origin to `TRAFRIEND_CORS_ORIGINS` before starting the API.
- If port 3000 or 8010 is already in use, select another port and update `NEXT_PUBLIC_API_BASE_URL` and the backend CORS origin together.

Production deployment and external Render Cron instructions live in
[`deployment.md`](deployment.md). FastAPI never starts a scheduler or background
capture loop.
- If a language change appears stale during development, confirm cookies are enabled for `localhost` and reload once; clearing the `trafriend_locale` cookie restores English as the default.
- Delete and recreate only the affected application's generated caches (`apps/web/.next` or `services/api/.pytest_cache`) when diagnosing stale local output; do not remove source or lockfiles.

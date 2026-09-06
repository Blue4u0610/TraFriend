# Local Development

## Phase 1 stack

- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS 4, and shadcn/ui.
- Backend: Python 3.9+, FastAPI, Pydantic 2, Uvicorn, and pytest.
- Data: deterministic in-memory Mock provider by default; optional Alpaca REST adapter for manual daily-close and overnight validation.
- Not included: Futu/OpenD implementation, PostgreSQL, public live-data serving, or automatic scheduling.

The frontend and backend run as separate applications. Their dependencies and commands are intentionally independent.

## Prerequisites

- Node.js 22 LTS and npm.
- Python 3.9 or later.

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
.venv/bin/uvicorn trafriend_api.main:app --reload --host 127.0.0.1 --port 8000
```

Useful local URLs:

- Health: `http://127.0.0.1:8000/health`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`
- Interactive API docs: `http://127.0.0.1:8000/docs`

The public API still uses the Mock provider and needs no market-data account or credential. The Alpaca adapter is reachable only through the manual backend commands described below.

## Manual Daily Close Anchor validation

The calculator uses `DAILY_CLOSE_ANCHOR`, not an overnight open or snapshot. With backend-only Alpaca credentials in the current process, validate the latest completed regular-session close pairs from `services/api`:

```bash
.venv/bin/python -m trafriend_api.scripts.validate_daily_close_anchor
```

The command asks the XNYS calendar for the latest completed session, makes batched `1Day` requests with `feed=sip` and `adjustment=raw`, and validates SNDK/SNXX and QQQ/TQQQ on exactly that trading date. It also runs the requested deterministic scenarios: SNDK `+5%` maps to SNXX `+10%`, and QQQ `+2%` maps to TQQQ `+6%`. Output includes close, provider market timestamp, backend observation time, feed, quality, and status. It never prints credentials.

Default environment overrides are:

```bash
export TRAFRIEND_ALPACA_DAILY_BARS_FEED=sip
export TRAFRIEND_ALPACA_DAILY_BARS_QUALITY=DELAYED
```

The diagnostic writes only an in-memory immutable anchor version. It does not add PostgreSQL, a scheduler, an ingestion route, or frontend live data.

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

The default API URL is `http://127.0.0.1:8000`. To override it locally, create `apps/web/.env.local` containing only:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

This variable is public by design because it contains only the TraFriend API origin. Never put a provider credential in a `NEXT_PUBLIC_*` variable.

## Verification commands

Frontend:

```bash
cd apps/web
npm run lint
npm run typecheck
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
.venv/bin/uvicorn trafriend_api.main:app --host 127.0.0.1 --port 8000
```

## Mock API surface

Phase 1 implements:

- `GET /health`
- `GET /api/v1/instruments/search`
- `GET /api/v1/instruments/{instrument_id}`
- `GET /api/v1/instruments/{instrument_id}/leveraged-products`
- `GET /api/v1/leveraged-etf/relationships/{relationship_id}/anchor`
- `POST /api/v1/leveraged-etf/calculations`
- `GET /api/v1/profit-ratio/instruments/{instrument_id}/latest`
- `GET /api/v1/profit-ratio/instruments/{instrument_id}/history`

Mock close anchors and Profit Ratio points are deterministic. They are deliberately not presented as live market data.

## Troubleshooting

- If the dashboard says `API offline`, ensure Uvicorn is running on port 8000.
- If browser requests are rejected by CORS after changing the frontend port, add the exact local origin to `TRAFRIEND_CORS_ORIGINS` before starting the API.
- If port 3000 or 8000 is already in use, select another port and update `NEXT_PUBLIC_API_BASE_URL` and the backend CORS origin together.
- If a language change appears stale during development, confirm cookies are enabled for `localhost` and reload once; clearing the `trafriend_locale` cookie restores English as the default.
- Delete and recreate only the affected application's generated caches (`apps/web/.next` or `services/api/.pytest_cache`) when diagnosing stale local output; do not remove source or lockfiles.

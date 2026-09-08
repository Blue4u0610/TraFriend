# QQQ stock price charts and optional Profit Ratio

## What is and is not available

The QQQ-only search and charts read PostgreSQL through dedicated public read
endpoints. Selecting a stock displays complete price OHLC candles by default.
Price daily K, daily return, and Profit Ratio are independently selectable layers in
one synchronized trading-date chart with explicit USD and percentage scales.
Two ratio endpoint values can form a body but cannot supply intraday ratio high/low.
A missing ratio does not hide stock search, valid price candles, or daily returns.
An explicit Mock fixture is used only when no PostgreSQL configuration is supplied.

The current Alpaca adapter can capture real consolidated regular open/close prices.
It **cannot yet publish real Profit Ratio values**: validated prior cost states,
effective-dated float and corporate-action/minute coverage inputs are missing.
Successful price capture reports `DATA_INSUFFICIENT`, with null ratios. See ADR 0006.
The legacy single-point `/instruments/{id}/latest` and `/history` endpoints remain
the older Mock prototype and are not used by the new chart.

## Initialize (backend/worker only)

In `services/api`, use backend secrets inherited from the environment; do not paste
credential-bearing URLs into commands, docs or the frontend.

```sh
.venv/bin/alembic upgrade head
.venv/bin/python -m trafriend_api.scripts.bootstrap_production
.venv/bin/python -m trafriend_api.scripts.capture_qqq_price_history \
  --start 2026-06-08 --end 2026-09-04
```

Bootstrap now verifies the independent price table and initializes empty QQQ search
metadata from the verified normalized 102-equity issuer snapshot dated 2026-09-04.
It makes no vendor request and inserts no fake market prices. Existing metadata is
preserved; a later deployment cannot replace a newer snapshot with the bundled date.
An operator may explicitly use `--refresh-universe` on either capture command to
refresh sourced membership. This refresh imports the current Invesco snapshot and preserves
canonical identities already known by TraFriend and rejects malformed/incomplete
issuer responses. Repeat snapshots are idempotent; different same-date facts
conflict. No migrations fetch a vendor or seed licensed production market prices.

## Three-month price replay

For the development-round range (current constituents, not historical membership):

```sh
.venv/bin/python -m trafriend_api.scripts.capture_qqq_price_history \
  --start 2026-06-08 --end 2026-09-04
```

This independent command batches raw/split SIP daily bars with pagination and stores
genuine OHLC in `market_daily_price_bars`, without requiring or creating numerical
Profit Ratios. Prices are raw eligible consolidated regular-session prices; returns
use the prior session close on the current split basis, not dividend-reinvested returns.
Only completed sessions plus 20 minutes are captured. Existing bars are reused,
missing dates remain missing, and immutable conflicts never overwrite valid history.
Use the older `capture_profit_ratio` command for OPEN/CLOSE ratio-input observations;
it also delegates completed-day independent OHLC capture. Price acquisition does not
solve unavailable cost-distribution/float inputs or generate synthetic ratio values.

Local real replay on 2026-09-08: 102 securities, 63 sessions, 6,417 bars inserted;
9 unavailable dates (HONA June 8-12; SPCX June 8-11), zero conflicts. Rerun:
0 inserted, 6,417 existing, same 9 gaps, zero duplicate rows. This is local
`trafriend_dev` evidence, not a claim that Render data has been populated. Existing
28 calculator anchors and 12,834 prior endpoint-price records were preserved.

For deployment, execute this command in the backend's inherited production
environment after migration and metadata bootstrap. Git push and migration alone
do not transfer local market-price rows. Do not expose an unauthenticated capture
endpoint or add credentials to a build command. A partial capture exits 2 while
retaining valid bars; inspect the report and preserve explicit missing dates rather
than treating a partial result as a failed application migration.

## Daily scheduled invocation

The independently runnable command is:

```sh
python -m trafriend_api.scripts.capture_profit_ratio
```

Run it from the backend working directory/environment. No arguments means a bounded
seven-calendar-day catch-up window starting no earlier than 2026-09-08. It checks
each calendar session's OPEN and CLOSE phase, waits logically until +20 minutes,
and returns immediately for phases not due. Existing successful/insufficient
records avoid provider calls. Older outages require an explicit bounded replay.
The same worker now separately captures completed-day OHLC, irrespective of missing
ratio model inputs. Historical ratio prefetch failure is isolated and cannot prevent
an independent price attempt. No second in-process scheduler is introduced.

An external scheduled worker can invoke this at the 20th and 50th minute of each
hour. The session calendar, not the scheduler's UTC schedule, determines whether
work is due; holidays and early closes need no manual UTC edits. This produces only
two logical observations per stock/session. FastAPI contains no scheduler loop.
Issuer refresh is a separate operator action; monitor the displayed snapshot date
and refresh when the portfolio changes rather than claiming perpetual completeness.

Exit 0 means the invocation completed without retryable input acquisition errors.
Always inspect the JSON status: `DATA_INSUFFICIENT` is **not** a usable numerical
Profit Ratio. Exit 2 means `PARTIAL_RETRYABLE`; exit 1 means conflict/configuration
failure. Model-input absence is non-retryable until an operator supplies validated
inputs, so it must not cause repeated provider requests. The explicit
`--retry-insufficient` option reevaluates such records after input prerequisites
change. This option is not a way to fabricate or forcibly overwrite values.

No cloud deployment, paid service or Render Cron job is automatically created by
the code. Any local Codex automation is a temporary development runner, requires
the host/application to remain available, and is not cloud production scheduling.

For this local development run a Codex thread automation named
`TraFriend QQQ 开收盘数据采集` was activated on 2026-09-08. It checks the due work
on weekdays around the regular open, the possible early close, and the regular
close, with an additional retry check. Its target is local `trafriend_dev` only;
it must stop if inherited secrets are unavailable or the configured target differs.
It does not enable numeric ratios while model prerequisites remain absent.

Test diagnostics must exclude database URLs from fixture representations. The
existing PostgreSQL fixture now uses `repr=False` for its credential-bearing field.
If a prior failure output disclosed credentials, rotate the affected local password
and refresh the runtime secret; never paste the old or new values into chat.

## Contract and verification

```sh
.venv/bin/python -m trafriend_api.scripts.export_profit_ratio_contract
TRAFRIEND_TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
.venv/bin/alembic current
```

The contract generator exports `openapi-profit-ratio.json` and the frontend's
generated `profit-ratio.ts` from FastAPI's response models. Do not edit generated
files manually. Frontend checks: `npm run lint`, `npm run typecheck`,
`npm test -- --run`, `npm run build`.

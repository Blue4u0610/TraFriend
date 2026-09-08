# QQQ equity open/close capture

## What is and is not available

The QQQ-only search and open/close chart read PostgreSQL through dedicated public
read endpoints. Two endpoint values can form an open/close body but cannot supply
intraday high/low. A missing ratio does not hide valid prices or daily returns.
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
.venv/bin/python -m trafriend_api.scripts.capture_profit_ratio --refresh-universe
```

The refresh imports the current Invesco QQQ equity-holdings snapshot. It preserves
canonical identities already known by TraFriend and rejects malformed/incomplete
issuer responses. Repeat snapshots are idempotent; different same-date facts
conflict. No migrations fetch a vendor or seed licensed production market prices.

## Three-month price replay

For the development-round range (current constituents, not historical membership):

```sh
.venv/bin/python -m trafriend_api.scripts.capture_profit_ratio \
  --start 2026-06-08 --end 2026-09-04
```

The command batches daily bars and pagination, stores distinct OPEN/CLOSE records,
and reports unavailable data per symbol. It does not label reconstructed historical
inputs as observations actually acquired at the historical opening instant.
It will store null Profit Ratios rather than guess historical state.

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

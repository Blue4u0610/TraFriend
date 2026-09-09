# Production Deployment Preparation

This runbook prepares a dashboard-driven deployment with Vercel for `apps/web`,
Render for `services/api`, Render PostgreSQL, and an external Render Cron Job. It
does not create cloud resources. Use placeholder domains below until the real domain
is connected.

## Before public launch

Technical deployment is ready for private/development use. Alpaca credentials permit
API access but do not by themselves prove public market-data redistribution rights.
Confirm the required display and redistribution license in writing before publicly
serving Alpaca-derived closes or rankings. This licensing task does not require
changing the deployment architecture.

## Code updates versus data updates

These are deliberately separate workflows:

```text
CODE UPDATE WORKFLOW
PyCharm / Codex -> commit -> push -> Vercel and Render deploy

DATA UPDATE WORKFLOW
Render Cron or an intentional manual production command
  -> Alpaca -> Render PostgreSQL -> existing FastAPI read -> website refresh
```

Daily ranking, Daily Close Anchor, and OHLC rows do not require a Git commit, push,
Vercel rebuild, Render Web Service redeploy, or FastAPI restart. PostgreSQL is read
per request; a committed row is visible on the next normal API read. Local
`trafriend_dev` is development-only and is never copied to production. A schema
change is different: it requires reviewed code, a migration, deployment, and
`alembic upgrade head`.

## 1. Push the reviewed repository

Push only reviewed source commits to the Git provider connected to Vercel and Render.
Never commit `.env`, credentials, `.idea`, `.venv`, `node_modules`, or `.next`.

## 2. Create Render PostgreSQL

Create a PostgreSQL database in the same Render region as the API and Cron Job. Use
Render's internal database URL for those services. TraFriend accepts the common
`postgresql://` Render URL and selects the installed psycopg 3 driver internally; it
also accepts explicit `postgresql+psycopg://`. Do not expose PostgreSQL through a
custom public domain.

## 3. Configure the Render backend environment

Create a Render Web Service with root directory `services/api` and set:

```text
DATABASE_URL=<Render internal PostgreSQL URL>
ALPACA_API_KEY=<backend secret>
ALPACA_SECRET_KEY=<backend secret>
TRAFRIEND_ENV=production
TRAFRIEND_CORS_ORIGINS=https://trafriend.com,https://www.trafriend.com
TRAFRIEND_DAILY_CLOSE_PROVIDER=alpaca
TRAFRIEND_ALPACA_DAILY_BARS_FEED=sip
TRAFRIEND_ALPACA_DAILY_BARS_QUALITY=DELAYED
```

Replace the example frontend origins with the actual Vercel/custom origins. Do not
use `*`. Render supplies `PORT`; do not create a fixed production port secret.

## 4. Install and migrate

Use this Render build command, derived from `services/api/pyproject.toml`:

```bash
pip install .
```

From a Render Shell or one-off job in `services/api`, apply the complete migration
chain:

```bash
alembic upgrade head
```

Migrations use `DATABASE_URL`; no host, role, password, or database name is hardcoded.

## 5. Bootstrap provider-independent metadata

Run the idempotent bootstrap after migrations:

```bash
python -m trafriend_api.scripts.bootstrap_production
```

The command safely reapplies `alembic upgrade head`, verifies the current revision,
required tables, and the curated `underlyings` and `leveraged_products` rows. Those
verified rows are migration-owned, so bootstrap never fabricates rankings or prices.
Running it twice is safe.

## 6. Initialize rankings and Daily Close Anchors

First calculate the provider-derived ranking for the month containing the latest
completed exchange session:

```bash
python -m trafriend_api.scripts.calculate_mtd_rankings
```

Then capture latest completed regular-session anchors for every supported underlying
in that ranking:

```bash
python -m trafriend_api.scripts.capture_popular_daily_closes --provider alpaca
```

Both commands are idempotent. Ranking data is atomically replaced from verified
source bars. Identical anchors return `EXISTING`; conflicting immutable values are
not overwritten. Neither command falls back to an older market session.
Ranked stocks with no active calculator-supported leveraged product remain in the
Popular dataset but report `SKIPPED_NO_SUPPORTED_PRODUCT`. They do not trigger a
market-data request, count as unavailable, or make the command retryable. Capture
output reports inserted, existing, structural skips, unavailable rows, and
conflicts separately.

## 7. Deploy Render FastAPI

Use:

- Root Directory: `services/api`
- Build Command: `pip install .`
- Start Command: `uvicorn trafriend_api.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

The start command deliberately omits `--reload`. `/health` reports process health and
does not expose database or credential details. Use the validation command below for
database readiness.

Verify the Render URL returns HTTP 200:

```bash
curl --fail --show-error https://your-render-service.example/health
```

## 8. Deploy the Vercel frontend

Create a Vercel project with:

- Root Directory: `apps/web`
- Framework Preset: Next.js
- Install Command: `npm install` (Vercel's detected default)
- Build Command: `npm run build`
- Environment Variable:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.trafriend.com
```

Set this variable before building because `NEXT_PUBLIC_*` values are embedded in the
browser bundle. It is the only frontend API setting and is public by design. Never
place `DATABASE_URL` or Alpaca credentials in Vercel. Production rejects a missing
API URL and rejects an `http://` API URL.

## 9. Configure custom domains and HTTPS

The intended layout is:

```text
trafriend.com      -> Vercel frontend
www.trafriend.com  -> Vercel redirect or frontend alias
api.trafriend.com  -> Render FastAPI
```

Use the DNS records currently shown by the Vercel and Render dashboards at the domain
registrar; platform record targets can change, so none are hardcoded here. Both
platforms terminate HTTPS. After the API domain works, set Vercel's
`NEXT_PUBLIC_API_BASE_URL` to its `https://` URL, redeploy the frontend, and set exact
frontend origins in `TRAFRIEND_CORS_ORIGINS`.

## 10. Configure Render Cron

Create a separate Render Cron Job using the same repository, region, and backend
secret environment:

- Root Directory: `services/api`
- Build Command: `pip install .`
- Run Command: `python -m trafriend_api.scripts.run_daily_market_update`
- Schedule: `30 17,18,20,21,22 * * 1-5` (Render cron schedules use UTC)
- Environment: the same production `DATABASE_URL`, Alpaca credentials,
  `TRAFRIEND_ENV=production`, and safe `TRAFRIEND_CORS_ORIGINS` used by the backend;
  no frontend variables

The five weekday wake-ups cover NYSE early closes and normal closes in both daylight
and standard time, with a final publication-lag retry. The command—not the cron
expression—asks the NYSE calendar for the latest completed session, including
holidays and early closes. A wake-up before the next session has completed is an
idempotent current-session check; it does not manufacture a new trading date. The
first successful run updates MTD rankings, Daily Close Anchors, and QQQ-stock daily
OHLC; later wake-ups see immutable current rows and avoid duplicate provider reads. A
weekend, holiday, or current rerun reports `SKIPPED` and exits zero. Missing or delayed
provider data reports `PARTIAL_RETRYABLE` and exits 2 without substituting an older
session. Zero-product ranked symbols are successful structural skips and never cause
retry status. FastAPI contains no scheduler or infinite loop.

The command prints only `PRODUCTION`/`DEVELOPMENT`, database hostname, database name,
trading date, ranking status, and concise anchor/OHLC counters. It never prints the
database URL, database role/password, or Alpaca secrets. A remote database is
rejected unless `TRAFRIEND_ENV=production`; a local database is rejected in
production mode.

## 11. Operator commands

Run commands from `services/api`. Values for secrets must already be present in the
process environment or the hosting platform secret store; never paste them into a
checked-in script.

### A. Local development data update

```bash
TRAFRIEND_ENV=development \
.venv/bin/python -m trafriend_api.scripts.run_daily_market_update
```

This accepts only the inherited local `trafriend_dev` URL.

### B. Manual production data update from a Mac

After securely injecting the Render external `DATABASE_URL` and Alpaca credentials
into the current shell:

```bash
TRAFRIEND_ENV=production \
TRAFRIEND_CORS_ORIGINS=https://www.trafriend.xyz \
.venv/bin/python -m trafriend_api.scripts.run_daily_market_update
```

This runs the normal provider capture directly against Render PostgreSQL. It does
not copy the local database and requires no Git operation or redeploy.

### C. One-time production OHLC backfill

```bash
TRAFRIEND_ENV=production \
TRAFRIEND_CORS_ORIGINS=https://www.trafriend.xyz \
.venv/bin/python -m trafriend_api.scripts.capture_qqq_price_history \
  --start 2026-06-08 \
  --end 2026-09-04
```

Historical backfill is deliberate and bounded; it is not part of daily Cron.

### D. Routine Render Cron update

```bash
python -m trafriend_api.scripts.run_daily_market_update
```

Render supplies all production environment values. No interactive flag or loop is
used.

### E. Production database migration when schema changes

```bash
alembic upgrade head
```

Run this only as part of a reviewed schema deployment. Routine data updates never
run or create migrations.

## 12. Validate the deployment

From the Render backend shell, run the non-destructive checker without displaying
secret values:

```bash
python -m trafriend_api.scripts.validate_deployment \
  --api-url https://api.trafriend.com
```

It reports only SET/MISSING credential state, database connectivity, migration/table
state, row counts, latest expected/available anchor dates, and `/health` status.

## 13. End-to-end checklist

1. Push the reviewed Git repository.
2. Create Render PostgreSQL.
3. Configure backend environment variables and secrets.
4. Run `alembic upgrade head`.
5. Run `python -m trafriend_api.scripts.bootstrap_production` twice and confirm both succeed.
6. Initialize MTD ranking and latest anchors with the commands above.
7. Deploy Render FastAPI without `--reload`.
8. Confirm `/health` returns HTTP 200.
9. Deploy `apps/web` on Vercel with the production API URL.
10. Verify Search, Popular, Watchlist, forward calculation, and reverse calculation.
11. Add the frontend domains in Vercel and at the registrar.
12. Add the API domain in Render and at the registrar.
13. Update exact production CORS origins and restart the API.
14. Create the external Render Cron Job.
15. Run the deployment validator and an end-to-end calculator read.
16. Inspect the next scheduled update result; retry only if it reports `PARTIAL_RETRYABLE`.

Normal calculator reads continue to use PostgreSQL only. Alpaca remains capture-only.

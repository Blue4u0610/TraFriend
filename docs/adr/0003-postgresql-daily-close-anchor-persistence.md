# ADR 0003: PostgreSQL Daily Close Anchor persistence

- Status: Accepted
- Date: 2026-09-06

## Context

Daily Close Anchors were process-local, so calculator references disappeared on restart. Capture must be idempotent, immutable, exact-decimal, and independent from normal calculator reads. The current relationship catalog is still small curated application metadata, and no scheduler or broader persistence model is authorized yet.

## Decision

Use synchronous SQLAlchemy 2 with psycopg 3 behind `DailyCloseAnchorRepository`, and manage the PostgreSQL schema exclusively through Alembic migrations. `DATABASE_URL` selects `PostgreSQLDailyCloseAnchorRepository`; its absence retains `InMemoryDailyCloseAnchorRepository` for deterministic local and CI tests.

Migration `20260906_0001` stores each complete underlying/leveraged pair atomically in `daily_close_anchors`. Prices use `numeric(20,8)` and signed leverage uses `numeric(8,4)`. The logical identity is `(underlying_symbol, leveraged_product_symbol, trading_date)`. A transaction-scoped advisory lock plus database uniqueness makes identical retries reuse the existing row, while materially different immutable facts raise an explicit conflict. A database trigger rejects direct updates and deletes.

Incomplete or rejected captures are not inserted. The application compares a retrieved row with the exchange calendar's latest completed session, preventing an older complete anchor from becoming a fallback after a newer capture failure. Alpaca is used only by the manual capture path. Calculator requests resolve curated relationship metadata through a dedicated in-memory catalog and anchor data through the repository, so they invoke neither Alpaca nor the broad market-data provider.

## Consequences

- Anchors survive process, engine, repository, and application recreation.
- Ordinary tests remain credential-free and network-free.
- A future correction workflow must append a reviewed higher version; it cannot mutate an existing row.
- A future operational-attempt audit table, persisted relationship catalog, scheduler, deployment setup, and production role separation remain separate rounds.

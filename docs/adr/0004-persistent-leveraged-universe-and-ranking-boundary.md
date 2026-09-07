# ADR 0004: Persist leveraged-product metadata separately from rankings and anchors

- Status: Accepted
- Date: 2026-09-06

## Context

The validated calculator already reads immutable pair-level Daily Close Anchors from PostgreSQL. Product search, one-to-many leveraged relationships, scheduled capture selection, and a future Top-100 view now require reusable metadata. Market popularity is time-varying sourced data and must not be confused with curated product relationships or close observations.

Alpaca's [documented most-active screener](https://docs.alpaca.markets/us/reference/mostactives-1) returns up to 100 current-day SIP symbols ranked by share volume or trade count. It does not implement the approved September-to-date dollar trading volume metric. Alpaca also [states that standard API market data cannot be redistributed](https://alpaca.markets/support/redistribute-alpaca-api) without permission.

## Decision

1. Keep `daily_close_anchors` and `PostgreSQLDailyCloseAnchorRepository` unchanged as the calculator's only price source.
2. Add `underlyings` and `leveraged_products` tables and implement `PostgreSQLLeveragedUniverseRepository` behind the existing `LeveragedRelationshipCatalog` boundary.
3. Store signed leverage, direction, issuer, effective dates, authoritative source URL, and verification time. Never infer a relationship from a ticker.
4. Add an independent `market_rankings` table and `MarketRankingRepository`. The approved type is `DOLLAR_TRADING_VOLUME`; period completeness and population completeness are separate states.
5. Keep ranking ingestion provider-independent and seed no placeholder ranks. ADR 0005 supersedes the initial decision to leave September 2026 empty by approving a reproducible Alpaca daily-bar aggregation.
6. Keep the scheduled operation external to FastAPI. `capture_popular_daily_closes` is the idempotent command a scheduler invokes; it uses the exchange calendar at runtime.
7. Search uses only universe metadata. Deliberate symbol selection may run an on-demand cache check/capture; normal calculator reads remain PostgreSQL-only.

## Consequences

- One underlying can expose every verified long and inverse child without duplicating user watchlist entries.
- A missing child close does not invalidate valid sibling anchors or calculations.
- Ranking sources and methodologies can change without altering product metadata or historical anchors.
- Public launch remains blocked on market-data display/redistribution rights.
- The browser stores only underlying symbols in `localStorage`; no authentication or user table is introduced.

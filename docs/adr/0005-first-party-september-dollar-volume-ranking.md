# ADR 0005: Calculate September dollar-volume ranking from daily VWAP

- Status: Accepted
- Date: 2026-09-06

## Context

Alpaca's current-day most-active screener does not provide the required September-to-date dollar-volume ranking. Alpaca does provide a documented active U.S.-equity asset list and multi-symbol historical daily bars containing share volume and VWAP. September 2026 is incomplete, so session coverage must be exchange-calendar-derived and explicitly labeled `SEPTEMBER_TO_DATE`.

The asset response does not include a comprehensive common-stock/ETF/security-type field. It does expose status, tradability, exchange, symbol, and name. This supports reliable exclusion of OTC issues and securities explicitly identified by symbol/name, but cannot prove perfect classification of every ordinary stock versus every non-leveraged ETF.

## Decision

1. Build candidates from active, tradable `us_equity` assets on listed U.S. exchanges rather than from TraFriend's curated leveraged-product universe.
2. Exclude curated ETFs/products plus symbol/name metadata explicitly identifying ETFs/ETNs, leveraged/inverse funds, warrants, rights, units, preferred shares, and blank-check acquisition vehicles.
3. Request raw SIP `1Day` bars in batches of at most 200 symbols for every exchange-calendar-completed September session.
4. Calculate each complete symbol as `SUM(daily VWAP * daily share volume)` using `Decimal`. Do not substitute close for a missing VWAP. A candidate missing any expected day is excluded as incomplete.
5. Sort descending, select 100, and atomically replace the `2026-09` / `DOLLAR_TRADING_VOLUME` dataset. Persist calculation source, asset metadata, completeness, and session counts.
6. Keep the period `SEPTEMBER_TO_DATE` until the month completes. Keep public redistribution approval separate from technical data access.

## Consequences

- The ranking is reproducible first-party aggregation, not a copied third-party list.
- Reruns refresh one logical ranking set without duplicate ranks or symbols.
- Ranking price/volume observations do not become Daily Close Anchors and cannot affect calculator reads.
- Security-type filtering is conservative but limited by Alpaca's available asset metadata; the limitation remains visible in developer documentation.

# ADR 0008: Futu-reported chip profit ratio

- Status: Accepted; local live read entitlement validated
- Date: 2026-09-12

## Context

Alpaca supplies the genuine QQQ price candles used by the price-first chart but
does not supply a validated cost distribution from which TraFriend can reproduce
Futu's displayed “筹码获利比例”. Screenshot/OCR automation is fragile and loses
timestamp, quality and methodology provenance. Futu OpenD Stock Screening V2
documents the featured property `CHIPS_PROFIT_RATIO` (5101). OpenD v10.10 returns
this field as a normalized `0..1` value. Market snapshots supply regular-session
open/latest price context and an update time used to reject stale responses.

## Decision

Use the official `futu-api` Python SDK and a locally authenticated Futu OpenD.
Sample the current provider-reported value at two bounded exchange-calendar phases:
20–55 minutes after the actual regular-session open and 20–55 minutes after the
actual regular-session close. This naturally handles holidays, DST and early closes.
The worker scans a bounded U.S. screen sorted by market cap, keeps only members from
TraFriend's dated QQQ catalog, and obtains price context in one batch snapshot.
This avoids relying on the current OpenD `INDEX_ID` filter, which returned an empty
U.S. result during real validation. The scan stops as soon as all requested catalog
symbols are found and never exceeds ten 200-row pages.

Preserve the provider value as a fractional Decimal in `[0, 1]`. Persist it
under `FUTU_CHIPS_PROFIT_RATIO/1`, status `REPORTED`, provider `futu`, and feed
`stock-screen-v2+market-snapshot`. `observed_at` records receipt time. As in ADR
0006, `market_timestamp` is the exchange-calendar OPEN/CLOSE phase being evaluated,
not an individual trade time; the snapshot update time must be current-session data.
The public API remains database-only. Missing or stale data remains an explicit gap.
The old `CHIP_TURNOVER/1` experimental method remains separate and is never merged
with this series.

## Consequences

- There is no historical backfill: OpenD exposes the current featured value, not a
  documented historical series. Collection begins only after successful live runs.
- OpenD must be running and logged in on the worker host. The host must be awake and
  have the necessary U.S. data entitlement.
- Entitlement quality starts as `UNKNOWN`; an operator may set it to `REALTIME` or
  `DELAYED` only after account-specific verification.
- Provider licensing and redistribution rights must be confirmed before public
  production display. The adapter and schema do not grant those rights.
- GUI automation/OCR is not a fallback. A missing OpenD value stays unavailable.

Sources:

- https://openapi.futunn.com/futu-api-doc/en/quote/get-stock-screen.html
- https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html
- https://openapi.futunn.com/futu-api-doc/en/opend/opend-cmd.html

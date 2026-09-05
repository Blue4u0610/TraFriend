# ADR 0001: Provider-neutral overnight references with Alpaca as the first validation adapter

- Status: accepted for manual validation; production provider and licensing remain pending
- Date: 2026-09-05

## Context

TraFriend needs true U.S. overnight data from 20:00-04:00 ET, not ordinary 04:00-20:00 extended-hours data. It needs two non-interchangeable methods: the first one-minute overnight bar open and a synchronized quote snapshot near 20:05 ET. The product is public, so data redistribution rights matter separately from technical API access.

## Decision

Define a narrow `OvernightMarketDataProvider` application port for latest quotes, target-time snapshots, and overnight bars. Normalize all provider values into Decimal prices, UTC timestamps, explicit source/feed, price basis, and `REALTIME`, `DELAYED`, `STALE`, or `UNAVAILABLE` quality.

Implement Mock as the default and Alpaca as the first real manual-validation adapter. Use hosted REST rather than a provider SDK. Free-plan snapshot validation uses Alpaca's derived `overnight` latest quote midpoint; opening bars use historical `boats` 1-minute bars and remain explicitly delayed. The service, not the adapter, owns session/trading-date resolution, first-bar selection, freshness, synchronization, partial status, and immutable repository writes.

Use an injected XNYS exchange calendar and `America/New_York` session boundaries. Store UTC instants and the separately derived exchange trading date.

Do not implement scheduling, PostgreSQL persistence, or a public capture endpoint until manual feed and licensing gates pass.

## Consequences

- Futu/OpenD, Tiingo, Databento, or another licensed provider can replace Alpaca without changing frontend or capture-service semantics.
- Free local/CI tests remain deterministic and credential-free.
- An Alpaca free account can validate 20:05 indicative snapshots immediately, but exact source-native opening bars are delayed 15 minutes.
- Immediate BOATS data requires Alpaca Algo Trader Plus ($99/month) or another qualified provider.
- Alpaca's ordinary API terms do not grant redistribution. TraFriend cannot publish real-provider results until written public-display rights are secured.
- The in-memory repository proves version/idempotency behavior but does not survive process exit; PostgreSQL and atomic pair activation remain later work.

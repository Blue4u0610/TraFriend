# ADR 0002: Anchor calculator scenarios to completed regular-session closes

- Status: Accepted
- Date: 2026-09-05

## Context

TraFriend's initial calculator prototype reused its overnight research capture as the calculator reference. That implied a reset at the 20:00 ET overnight opening, but the product objective is a theoretical relationship based on a leveraged ETF's stated **daily** objective.

The [SNXX Summary Prospectus](https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm) says SNXX seeks 200% of SNDK's daily performance, defines a single trading day from one NAV calculation to the next, expects daily rebalancing, and warns that compounded returns over longer periods will likely differ from the daily objective. [FINRA](https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products) likewise explains that most geared ETPs reset exposure daily, generally measure the objective close-to-close, and can diverge materially over longer periods because daily returns compound.

Neither source names 20:00 ET as a reset. The conclusion that an overnight opening is not the calculator reset is an inference from the sources' NAV-to-NAV and close-to-close definitions and their daily-rebalancing descriptions.

Historical Alpaca BOATS diagnostics also found that independent first overnight trades were not necessarily synchronized: QQQ's first tested trade was 20:02 ET while TQQQ's was 20:00 ET. SNXX returned no trade across one full tested overnight session and no valid two-sided historical BOATS quote near 20:05 ET. Those results remain useful provider evidence, but they do not define the fund objective period.

## Decision

Use `DAILY_CLOSE_ANCHOR` as the calculator's only reference method:

- Resolve the latest completed U.S. regular trading session through the injected XNYS calendar.
- Retrieve the underlying and leveraged ETF daily closes for exactly that trading date through a narrow provider-neutral daily-bar port.
- Accept only one positive, usable, same-provider/feed value for each member on the expected date.
- Store the pair as an immutable version and allow calculation only when the pair is `COMPLETE`.
- Reject missing members, mixed dates, provider lag, stale/unavailable quality, malformed/future data, and any attempt to fall back to a prior session.
- Load the stored anchor during calculator reads; do not call a live provider from a calculation request.

The formula algebra does not change. `U0` and `L0` now mean the two regular-session closes in the Daily Close Anchor. The visible formula version changes to `leveraged-daily-close-linear/v2` because the reference semantics changed.

The supported relationship universe remains explicit metadata; no ticker-based inference is introduced.

Because the earlier `/api/v1` route was a local Phase 1 prototype and had not been released as a public production contract, replace `/relationships/{id}/reference` with `/relationships/{id}/anchor` and replace `reference_version_id` with `anchor_version_id`; do not retain an alias whose name preserves the corrected semantics.

## Consequences

- The calculator aligns with the daily objective period described by the issuer and FINRA.
- Before the current session closes, the latest completed session remains the previous valid exchange session; after a weekend or holiday, the calendar selects the last completed session.
- Alpaca `1Day` bars can validate the adapter and close data, but production storage, scheduling, licensing, and public redistribution rights remain separate work.
- Actual ETF prices can differ from the linear estimate because of bid/ask spreads, premium/discount to NAV, tracking error, financing and fees, liquidity, market conditions, distributions, and corporate actions.
- Multiplying a multi-day cumulative underlying return by the leverage factor remains explicitly unsupported because daily-reset returns compound path-dependently.
- Existing `OVERNIGHT_OPEN`, `OVERNIGHT_SNAPSHOT`, historical BOATS ports, CLIs, tests, and evidence remain unchanged and isolated from calculator behavior.

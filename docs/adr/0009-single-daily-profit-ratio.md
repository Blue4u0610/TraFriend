# ADR 0009: Single daily Profit Ratio with explicit timing basis

- Status: Accepted
- Date: 2026-09-15

## Context

The QQQ price chart originally modeled separate OPEN and CLOSE Profit Ratio endpoints.
That is useful only when each observation is genuinely sampled in a verified market
window. Futu's desktop chip-distribution history exposes one value for each visible
trading date, but the inspected UI does not disclose the exact effective intraday
time. Calling those historical values “close” would add unsupported provenance.

The product needs one understandable daily Profit Ratio series alongside genuine
daily OHLC and return. It must preserve historical values without fabricating timing,
interpolating gaps or rewriting the existing immutable endpoint audit trail.

## Decision

Add immutable `profit_ratio_daily_observations` storage keyed by instrument,
methodology/version and trading date. Every observation carries a timing basis:

- `CLOSE` means a real capture occurred inside the calendar-derived close window.
- `DAILY_TIME_UNVERIFIED` means the provider reported a trading-date value but its
  effective time could not be verified.

The read model exposes one daily `profit_ratio`. A valid CLOSE endpoint is preferred;
otherwise a stored daily observation may be used. OPEN observations are retained for
audit/backward compatibility but are not relabeled as the page's daily value. The API
also returns timing, quality, provider, feed, methodology and source-note fields.
The UI displays one point/line and one table column and labels unverified timing.

The first bounded import is a reviewed 30-row SNDK series for 2026-08-04 through
2026-09-15. Its time basis is `DAILY_TIME_UNVERIFIED`. Independent Alpaca daily OHLC
is captured separately and joined by trading date. Imports are validated, idempotent
and conflict on any attempted immutable factual change.

Future automatic Futu capture runs only in the genuine calendar-derived CLOSE window.
The Mac launchd schedule checks at 16:20 and 16:50 New York time for the normal close
and retry; the application calendar remains authoritative for holidays/early closes.

## Consequences

- The page presents one daily Profit Ratio instead of an artificial two-endpoint bar.
- Historical values remain useful while visibly disclosing their timing limitation.
- Genuine daily price OHLC/high/low and return remain independent of ratio coverage.
- Missing ratios stay missing; there is no interpolation or forward fill.
- The legacy OPEN/CLOSE schema and response fields remain available for compatible
  clients and audit, but new UI behavior uses the unified additive fields.
- Futu methodology/licensing and public redistribution remain provider-dependent and
  require operator review; this decision does not infer Futu's internal calculation.

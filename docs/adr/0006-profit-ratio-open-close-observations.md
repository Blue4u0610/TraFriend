# ADR 0006: QQQ equity open/close observations and explicit model-input gaps

Date: 2026-09-08

Status: endpoint capture/read design implemented; numerical turnover methodology
remains experimental and is not enabled with real inputs.

## Decision

The requested first chart contains two endpoints per regular trading day, not
Profit Ratio OHLC. There is no high/low field or fabricated wick. The independent
profit-ratio module stores OPEN and CLOSE observations and separate price facts;
it neither reads nor changes leveraged Daily Close Anchors.

Scope is the equity holdings in a sourced, effective-dated Invesco QQQ snapshot.
This is a practical QQQ equity universe, not a certified historical Nasdaq-100
membership feed and not the dollar-volume Popular Top-100. Multiple share classes
are retained. Cash, collateral and futures are excluded. Current-constituent
historical replay has survivorship bias and must not be called historical index
membership. Snapshot dates and the `QQQ_EQUITY_HOLDINGS:Invesco` source are public.

## Methodology boundary

`CHIP_TURNOVER/1` is a testable candidate, not Futu's algorithm or a measurement of
actual shareholder tax lots. With a validated prior cost distribution D and an
effective-dated float F, each minute retains `exp(-volume/F)` of old cost weights
and assigns the replacement mass to that minute's VWAP. Fractional cost weights
sum to one, computation uses Decimal, and strictly lower costs count as profitable
(equal cost is breakeven). OPEN evaluates the prior session's distribution at the
current regular open. CLOSE evaluates a chronologically updated distribution.
The minute VWAP is a price allocation approximation; repeated trading does not
identify which owners sold. No error bound relative to true positions is claimed.

Required before any real numerical result: sourced prior distribution with
validated initialization, dated float coverage, reviewed corporate-action basis,
and (for CLOSE) verified regular-minute coverage. Tests use synthetic fixtures
explicitly marked Mock. The live Alpaca input adapter supplies none of these
prerequisite approvals and therefore emits **null** ratios with an explicit
`VALIDATED_PRIOR_DISTRIBUTION_MISSING` reason. Storing from today does not recover
historical holders' acquisition costs. A 90-day price backfill alone is not a
90-day Profit Ratio backfill.

The candidate minute interval is `[regular_open, regular_close)`. A comprehensive
closing-auction treatment remains unresolved; `minute_coverage_complete` must not
be enabled until the trade/session boundary policy is reviewed. Alpaca daily volume
is not used as regular-session turnover because extended-hours prints can update
daily volume without updating daily prices. Raw volume/float, float updates,
spin-offs, splits, and initial-state uncertainty need independent validation.

There is no approved live float/seed adapter, minute-state persistence or numerical
historical replay pipeline in this round. These are not disguised by synthetic
seed distributions or a constant current float applied to history.

## Price and time semantics

SIP daily O/C are consolidated eligible-bar prices, not a claim of exact primary
exchange official auction values. Stored `market_timestamp` is the calendar phase
instant being evaluated; it is not an individual trade timestamp. `observed_at`
is acquisition time. Publication is attempted at open/close +20 minutes. XNYS
supplies the common US equity holiday and special-close schedule, including DST.
The code does not run a permanent loop in FastAPI.

The previous close is split-adjusted onto the current day's raw share basis, using
the same response range for current/prior split-adjusted prices. The displayed
daily return is `raw_close / previous_close_on_current_share_basis - 1`, excluding
dividend reinvestment. Ratio change is a difference in fractional ratios and is
displayed in **percentage points**. Missing previous close leaves return null.

## Persistence and alternatives

Immutable snapshot/price/observation tables, unique logical keys, transaction
advisory locks, and database mutation-rejection triggers prevent conflicting
retries. Missing-model-input records may append a higher estimated revision only
when the underlying price facts match. Arbitrary price corrections are not yet an
operator feature; conflicts require review, never silent overwrites. Future
stateful-model revisions must replay dependent subsequent sessions.

We rejected one-point fake OHLC, substituting another session, rolling volume
profiles relabeled as shareholder Profit Ratio, guessed float numbers, browser
vendor requests, and 100-symbol desktop scraping.

## Data rights

Issuer access is metadata discovery, not blanket permission to redistribute its
full holdings payload. Only normalized identity/source/effective-date data is kept.
Alpaca historical entitlement is not public-display authorization. Current work
uses authenticated local research capture; confirm source/derived-data storage
and public-display rights before production publication.

Sources:

- https://www.invesco.com/qqq-etf/en/about.html
- https://indexes.nasdaq.com/Index/Overview/NDX
- https://docs.alpaca.markets/us/docs/market-data-faq
- https://docs.alpaca.markets/us/reference/stockbars

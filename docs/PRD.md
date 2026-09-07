# TraFriend Product Requirements Document

## 1. Document status

- Product: TraFriend
- Release: MVP
- Audience: product, design, frontend, backend, data, and QA contributors
- Status: searchable/watchlist calculator and real September-to-date Top-100 are implemented; public data licensing remains pending
- Last updated: 2026-09-06

This document defines product behavior and release boundaries. Technical design lives in `ARCHITECTURE.md`, HTTP contracts in `API_SPEC.md`, and persistence design in `DATA_MODEL.md`.

## 2. Product summary

TraFriend is a user-facing U.S. stock market analytics website. It turns specialized calculations and market indicators into focused, understandable tools. The MVP contains two product areas:

1. A leveraged ETF price calculator based on immutable Daily Close Anchors.
2. Profit Ratio analytics for current and historical analysis.

TraFriend is an informational and research product. It does not provide investment advice, execution, brokerage, portfolio custody, or guaranteed predictions.

## 3. Problem statement

Investors frequently want to answer questions such as:

- If an underlying stock or ETF reaches a target price today, what price would a related leveraged ETF theoretically reach?
- If a leveraged ETF reaches a target price today, what underlying price does that imply?
- Which leveraged products, including inverse products, are associated with an underlying?
- What proportion of a stock's estimated holders or cost basis is currently profitable, and how has that value changed over time?

Existing answers are often scattered across platforms, calculated from inconsistent anchors, or presented without enough context about daily leverage reset behavior. TraFriend should make the reference point, assumptions, provenance, and limitations visible.

## 4. Product principles

- **Explain the anchor.** Every calculator result shows the underlying and leveraged ETF regular-session closes, the effective trading date, and capture time.
- **Describe, do not predict.** Calculator output is a single-day theoretical relationship, never a multi-day forecast or promised market price.
- **Make direction explicit.** Positive and inverse leverage factors are displayed with a sign, such as `+2x` or `-3x`.
- **Preserve provenance.** Market-derived values retain provider, timestamp, and methodology metadata.
- **Fail visibly.** Missing, stale, partial, or invalid data must not silently produce a result.
- **Design for more tools.** New analytics tools should be addable without coupling them to calculator screens or a specific data vendor.

## 5. Target users and primary journeys

### 5.1 Target users

- U.S. equity and ETF investors researching same-session price scenarios.
- Users comparing long and inverse leveraged products tied to one underlying.
- Users studying Profit Ratio trends alongside stock prices.

The MVP does not require user accounts or personalized portfolios.

### 5.2 Leveraged ETF calculator journey

1. The user searches by ticker or name.
2. TraFriend identifies whether the result is an underlying asset, an ordinary ETF, or a leveraged ETF.
3. If the user selected a leveraged ETF, TraFriend identifies its underlying.
4. TraFriend lists associated leveraged ETFs and their signed target leverage factors.
5. The user selects a relationship and sees the latest complete Daily Close Anchor.
6. The user enters either an underlying target price or a leveraged ETF target price.
7. TraFriend returns the theoretical corresponding target price, percentage changes, assumptions, and warnings.

### 5.3 Profit Ratio journey

1. The user searches for a supported stock.
2. TraFriend shows the current Profit Ratio, observation time, data source, and methodology label.
3. The user selects a historical range.
4. TraFriend shows Profit Ratio history and a synchronized stock-price comparison.
5. The user can inspect values at a point in time.

## 6. MVP functional requirements

### 6.1 Instrument search and relationships

The system must:

- Search supported U.S. stocks, ordinary ETFs, and leveraged ETFs by ticker or name.
- Return canonical ticker, display name, instrument type, exchange, and data availability.
- Identify a selected leveraged ETF's underlying asset.
- List all active leveraged ETF relationships for a selected underlying.
- Represent target daily leverage as a signed numeric factor, initially supporting at least `+2`, `+3`, `-1`, `-2`, and `-3`.
- Avoid inferring relationships from ticker naming conventions. Relationships come from curated or provider-backed metadata.
- Support relationship effective dates so historical changes do not overwrite prior facts.

### 6.2 Daily Close Anchors

The calculator's authoritative reference is `DAILY_CLOSE_ANCHOR`: the underlying and leveraged ETF closing prices from the same latest completed U.S. regular trading session. For every supported relationship, the system must:

- Ask an injected exchange calendar for the latest completed session. Never infer completion from wall-clock time, weekdays, a hardcoded UTC offset, or server `CURRENT_DATE`.
- Request provider daily bars for exactly that expected trading date and use each bar's close.
- Accept the pair only when both values are finite, positive, from the configured provider/feed, and assigned to the same expected trading date.
- Reject provider lag, a missing member, mixed dates, stale/unavailable quality, malformed values, and future timestamps. Never substitute a prior session or a zero.
- Persist each `COMPLETE` pair as an immutable version. `PARTIAL` and `UNAVAILABLE` remain explicit operational outcomes but are not inserted into the calculator-anchor table; the read service independently rejects an older row when its date is not the calendar-derived latest completed session.
- Return provider, feed, market timestamps, observation timestamps, expected session close, capture time, and trading date so the result can be reproduced.
- Keep calculator reads independent of live provider requests by loading a server-owned stored anchor version.

The existing `OVERNIGHT_OPEN` and `OVERNIGHT_SNAPSHOT` implementations are retained only as isolated market-data research and diagnostics. They are not calculator anchors, do not define the daily-reset boundary, and must not be silently substituted for `DAILY_CLOSE_ANCHOR`. Overnight session boundaries continue to use `America/New_York` and their established policies remain unchanged.

This choice follows geared-product definitions: most daily-reset products measure their objective close-to-close, while SNXX's prospectus defines a trading day from one NAV calculation to the next and describes daily rebalancing. Therefore, the conclusion that 20:00 ET is not a reset boundary is an inference from those stated close/NAV-to-close/NAV periods; neither source defines an overnight opening as the reset. See the [SNXX Summary Prospectus](https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm) and [FINRA's geared ETP explanation](https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products).

### 6.3 Calculation behavior

Given:

- `U0`: positive underlying Daily Close Anchor value
- `L0`: positive leveraged ETF Daily Close Anchor value
- `m`: non-zero signed daily leverage factor
- `Ut`: positive underlying target price
- `Lt`: positive leveraged ETF target price

Forward calculation is:

```text
underlying_return = Ut / U0 - 1
leveraged_return  = m * underlying_return
Lt                = L0 * (1 + leveraged_return)
```

Reverse calculation is:

```text
leveraged_return  = Lt / L0 - 1
underlying_return = leveraged_return / m
Ut                = U0 * (1 + underlying_return)
```

The system must:

- Use the signed factor directly, so the same formulas support long and inverse ETFs.
- Calculate on the backend from server-selected anchor data and relationship metadata; clients must not be trusted to supply leverage or close prices.
- Use decimal arithmetic with an explicitly documented precision and rounding policy.
- Preserve full internal precision and round only display values or serialized values defined by the API contract.
- Reject non-positive input prices, zero leverage, missing/incomplete anchors, mixed trading dates, mismatched relationships, and non-finite values.
- Refuse to present a non-positive theoretical output as a valid market price. It must return an out-of-model-domain error and explain the single-day linear model's boundary.
- Return both percentage changes and all reference metadata needed to reproduce the result.
- Apply no volatility decay, fees, financing, distributions, tracking error, compounding, or multi-day path assumptions in the MVP formula.

All formula branches, leverage signs, boundary behavior, and rounding behavior require automated unit tests.

### 6.4 Profit Ratio analytics

For supported stocks, the MVP must provide:

- The latest available Profit Ratio as a value from `0` to `1` and a percentage for display.
- Observation time, provider, methodology/version label, and freshness status.
- Historical Profit Ratio points over supported date ranges.
- Historical stock prices aligned by timestamp or trading period for comparison.
- A trend visualization with accessible tabular or textual values.

Profit Ratio is not a universally standardized metric. Before a real provider is integrated, the team must approve a precise product definition, update frequency, eligible instrument set, corporate-action treatment, and provider methodology. Values from different methodologies must not be combined into one continuous series without explicit normalization and versioning.

Profit Ratio OHLC/candlestick data is a post-MVP option. It may enter the MVP only if the chosen provider supplies sufficiently frequent observations or the system deliberately samples them. OHLC must never be fabricated from one daily point.

### 6.4a Search, popular universe, and watchlist

- Present separate underlying and leveraged-product searches. Both read the local
  provider-independent catalog by ticker or name and never call a market provider on
  each keystroke.
- Selecting a supported underlying or leveraged ETF resolves the canonical underlying, checks every active relationship for the latest completed-session anchor, and captures only missing pairs on demand.
- A leveraged-product selection preselects that product in reverse-calculation mode
  while retaining every sibling product for the underlying.
- On-demand capture retrieves only the latest completed regular-session daily close;
  it never substitutes an intraday, overnight, or previous-session price.
- One underlying target calculates every available mapped leveraged ETF. Missing child anchors remain visible as `Unavailable` without invalidating siblings.
- Reverse mode accepts one leveraged ETF target at a time and calculates its implied underlying target.
- The browser watchlist stores underlying symbols in `localStorage`; no user account is required.
- Popular rankings are a separate dataset. The approved September 2026 metric is `SUM(daily VWAP * daily share volume)` across every completed exchange-calendar session. September 2026 is `SEPTEMBER_TO_DATE` until the month is complete.
- Build candidates from Alpaca's active listed U.S.-equity assets, batch raw SIP daily-bar requests, and require one authoritative VWAP/volume bar per completed session. Missing VWAP makes that symbol incomplete; do not mix a close-price fallback into selected rows.
- Exclude reliably identified leveraged/inverse products, ETFs/ETNs, warrants, rights, units, preferred shares, OTC issues, and blank-check vehicles. Document that Alpaca asset metadata does not provide a comprehensive security-type classification.
- Treat leveraged-product coverage as a dated catalog snapshot. Refresh it against
  active assets and authoritative issuer catalogs; never infer a new relationship
  solely from a product ticker or name. Option-income, different-index/basket, and
  non-daily-reset products are outside this calculator's relationship set.

### 6.5 Disclosures and user communication

Every result view must communicate that:

- The calculator is a single-day theoretical estimate anchored to the displayed regular-session closes.
- Leveraged ETFs target daily performance and actual prices may differ because of bid/ask spreads, premium/discount to NAV, tracking error, financing and fees, liquidity, market conditions, distributions, and corporate actions.
- Daily-reset compounding means multiplying a multi-day cumulative underlying return by the leverage factor is not a valid forecast. FINRA provides a two-day example where daily `2x` results do not equal `2x` of the cumulative return.
- Profit Ratio is an estimate whose meaning depends on the displayed methodology.
- TraFriend provides information, not investment advice.

Disclosures must be readable without blocking normal use and must not be hidden only in a general terms page.

## 7. Quality attributes

### 7.1 Correctness

- Financial domain logic is independent of React/UI components, HTTP handlers, database models, and provider SDKs.
- Formula code has deterministic unit and property/boundary tests.
- Daily Close Anchor selection is deterministic and auditable.
- Time handling uses timezone-aware timestamps and an exchange calendar.

### 7.2 Security and privacy

- Market data credentials exist only in backend runtime configuration or a deployment secret manager.
- No provider credentials, provider SDK secrets, or privileged endpoints are shipped to browser bundles or exposed through `NEXT_PUBLIC_*` variables.
- Public inputs are validated, length-limited, and rate-limited as appropriate.
- The MVP stores no brokerage credentials, holdings, trades, or payment data.

### 7.3 Reliability and observability

- Daily Close Anchor capture reports success, partial failure, validation failure, and provider failure separately.
- Logs use correlation IDs and exclude secrets.
- Metrics cover capture freshness, capture failure rate, provider latency/errors, calculation error rate, and API latency.
- The public UI shows a clear unavailable/stale state rather than silently falling back to an old day.

### 7.4 Performance and accessibility

- Common search and calculation interactions should feel immediate on typical consumer connections.
- Initial service targets: p95 cached search under 500 ms and p95 calculation API latency under 300 ms, excluding exceptional provider work. Calculation requests should not call a live provider.
- Core journeys support keyboard navigation, visible focus, semantic labels, screen readers, and WCAG 2.2 AA color contrast.
- Layouts support mobile and desktop widths.
- The public web interface supports English and Simplified Chinese. A language control remains available in the global header, persists the user's preference, updates the document language, and localizes page copy, metadata, accessibility labels, disclosures, and application-owned error states. Market symbols, canonical identifiers, provider labels, and formula versions are not translated.

## 8. MVP scope boundaries

### 8.1 In scope

- Public, read-only instrument search.
- Curated underlying-to-leveraged ETF relationships.
- Daily, versioned regular-close anchor capture through a provider abstraction.
- Forward and reverse single-day theoretical calculations.
- Long and inverse leverage factors.
- Current and historical Profit Ratio with a price comparison when a defined data source is available.
- Mock providers and deterministic fixtures for local development and CI.
- Basic operational health, data freshness, error states, and disclosures.
- Searchable leveraged-product universe, multi-product calculation, local watchlist, and a source-attributed popular-ranking import path.

### 8.2 Out of scope

- Multi-day leveraged ETF prediction or backtesting.
- Intraday continuous recalculation of Daily Close Anchors.
- Trade execution, brokerage connectivity, personalized advice, portfolios, alerts, and accounts.
- Options, non-U.S. markets, tax analysis, or currency conversion.
- User-edited leverage factors or anchor prices in authoritative calculations.
- Automatic discovery of ETF relationships solely from ticker names.
- Guaranteed Profit Ratio OHLC/candlesticks.
- A microservice decomposition for the initial release.

## 9. Acceptance criteria

The calculator area is MVP-ready when:

- A user can search from either side of a supported relationship and reach the same canonical pair.
- At least one fixture exists for every initially supported leverage sign/magnitude.
- Forward and reverse calculations reproduce each other within the documented rounding tolerance.
- The API and UI show the exact Daily Close Anchor and formula inputs used.
- Missing, stale, partial, and out-of-domain cases have tested, user-understandable states.
- Unit, integration, and provider contract tests pass without network access using the Mock provider.
- A cached symbol selection and every normal calculation make zero market-data-provider calls.
- Re-running the popular daily-close command returns existing immutable rows and does not duplicate anchors.

The Profit Ratio area is MVP-ready when:

- The metric definition and methodology are approved and documented.
- A supported stock has a latest value and a historical series with provenance.
- Price and ratio series use explicit timestamps and alignment rules.
- Missing periods and methodology changes are visible rather than interpolated without notice.
- Automated tests cover range validation, chronological ordering, ratio bounds, and empty/partial series.

The overall MVP is ready when:

- No browser-delivered artifact contains market data credentials.
- API contracts are versioned and documented.
- Capture job alerts and data freshness dashboards exist for the live environment.
- Legal/disclosure text receives product review.

## 10. Success measures

Initial product measures:

- Search-to-valid-calculation completion rate.
- Percentage of active trading days with a complete same-date Daily Close Anchor.
- Calculator error rate by error class.
- Profit Ratio chart load success and supported-symbol coverage.
- Repeat usage of either tool without counting automated traffic.

Correctness and data freshness take priority over maximizing calculation volume.

## 11. Delivery phases

1. **Foundation:** approve contracts, formula policy, trading calendar/session rules, Profit Ratio definition, provider ports, and fixtures.
2. **Calculator vertical slice:** implement pure domain calculations and tests, Mock provider, reference capture workflow, read APIs, then the web UI.
3. **Profit Ratio vertical slice:** implement the approved metric/provider adapter, history storage and APIs, then trend and price-comparison UI.
4. **Production integration:** manually validate a licensed provider through the provider-independent daily-close service, then add persistence, scheduling/monitoring, security, and release checks. Overnight diagnostics remain a separate evidence stream.
5. **Post-MVP:** evaluate OHLC Profit Ratio, comparison tools, accounts, alerts, and additional financial tools from evidence and user feedback.

## 12. Open product decisions

These decisions must be resolved before their affected feature ships:

- Production provider and completed-daily-bar publication latency for the supported universe.
- Written public-display/redistribution rights for stored close values and derived results.
- Correction policy when a provider later amends or invalidates a quote.
- Authoritative source and methodology for underlying/leveraged ETF relationships.
- Exact Profit Ratio definition, data rights, cadence, supported universe, and corporate-action behavior.
- Public cache duration, rate limits, and supported locales.

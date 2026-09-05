# TraFriend Product Requirements Document

## 1. Document status

- Product: TraFriend
- Release: MVP
- Audience: product, design, frontend, backend, data, and QA contributors
- Status: architecture baseline; implementation has not started
- Last updated: 2026-09-05

This document defines product behavior and release boundaries. Technical design lives in `ARCHITECTURE.md`, HTTP contracts in `API_SPEC.md`, and persistence design in `DATA_MODEL.md`.

## 2. Product summary

TraFriend is a user-facing U.S. stock market analytics website. It turns specialized calculations and market indicators into focused, understandable tools. The MVP contains two product areas:

1. A leveraged ETF price calculator based on immutable Daily Reference Prices.
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

- **Explain the anchor.** Every calculator result shows the underlying and leveraged ETF reference prices, the effective trading date, and capture time.
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
5. The user selects a relationship and sees the Daily Reference Prices and their freshness.
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

### 6.2 Daily Reference Prices

For every supported underlying/leveraged ETF pair, the system must:

- Attempt to capture one fresh quote for both instruments at the configured beginning of each U.S. overnight trading session.
- Assign the pair to an explicit U.S. market trading date using a market calendar, not the server's local calendar date.
- Store the two prices as one immutable, versioned reference set with quote timestamps and provider provenance.
- Publish a reference set for calculations only after both quotes pass validation.
- Keep failed or partial attempts for operations, but never expose them as a valid pair.
- Make retries idempotent. A retry may create a newer version, but must not mutate a reference set already used as an immutable version.
- Select one version as the active Daily Reference Price set for a relationship and trading date.
- Expose freshness and status to the UI. If no valid current reference set exists, disable calculation and explain why.

Two reference methods are supported and must never be mixed inside one reference set:

- `OVERNIGHT_OPEN`: the open price of the first valid one-minute overnight bar at or after 20:00 ET, limited to the configured opening search window. Its actual bar timestamp is retained. A missing 20:00 bar may use the first later bar in that window; a prior-session value may not be used.
- `OVERNIGHT_SNAPSHOT`: a synchronized batch quote capture targeted for 20:05 ET. The initial reference price basis is a documented quote midpoint. Every member retains its market timestamp and backend observation time, and all members must satisfy the configured freshness and timestamp-skew policy.

All overnight session boundaries use `America/New_York`; stored instants use UTC. An evening session is assigned to the next exchange trading date, so Sunday evening belongs to Monday when Monday is an exchange trading day. A market calendar, not weekday logic or a hardcoded UTC offset, determines whether that trading date exists.

Each captured value records symbol, trading date, price when present, reference type, provider source, provider feed, observation time, market/bar time, price basis, quality (`REALTIME`, `DELAYED`, `STALE`, or `UNAVAILABLE`), and status. Delayed values are never relabeled real-time. Stale, missing, out-of-session, out-of-sync, and provider-error values remain auditable but cannot form an active reference pair.

### 6.3 Calculation behavior

Given:

- `U0`: positive underlying Daily Reference Price
- `L0`: positive leveraged ETF Daily Reference Price
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
- Calculate on the backend from server-selected reference data and relationship metadata; clients must not be trusted to supply leverage or reference prices.
- Use decimal arithmetic with an explicitly documented precision and rounding policy.
- Preserve full internal precision and round only display values or serialized values defined by the API contract.
- Reject non-positive input prices, zero leverage, missing references, mismatched relationships, and non-finite values.
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

### 6.5 Disclosures and user communication

Every result view must communicate that:

- The calculator is a single-day theoretical estimate anchored to the displayed Daily Reference Prices.
- Leveraged ETFs target daily performance and actual prices may differ because of tracking, fees, liquidity, spreads, distributions, corporate actions, and session timing.
- Profit Ratio is an estimate whose meaning depends on the displayed methodology.
- TraFriend provides information, not investment advice.

Disclosures must be readable without blocking normal use and must not be hidden only in a general terms page.

## 7. Quality attributes

### 7.1 Correctness

- Financial domain logic is independent of React/UI components, HTTP handlers, database models, and provider SDKs.
- Formula code has deterministic unit and property/boundary tests.
- Reference-set selection is deterministic and auditable.
- Time handling uses timezone-aware timestamps and an exchange calendar.

### 7.2 Security and privacy

- Market data credentials exist only in backend runtime configuration or a deployment secret manager.
- No provider credentials, provider SDK secrets, or privileged endpoints are shipped to browser bundles or exposed through `NEXT_PUBLIC_*` variables.
- Public inputs are validated, length-limited, and rate-limited as appropriate.
- The MVP stores no brokerage credentials, holdings, trades, or payment data.

### 7.3 Reliability and observability

- Reference capture reports success, partial failure, validation failure, and provider failure separately.
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
- Daily, versioned reference capture through a provider abstraction.
- Forward and reverse single-day theoretical calculations.
- Long and inverse leverage factors.
- Current and historical Profit Ratio with a price comparison when a defined data source is available.
- Mock providers and deterministic fixtures for local development and CI.
- Basic operational health, data freshness, error states, and disclosures.

### 8.2 Out of scope

- Multi-day leveraged ETF prediction or backtesting.
- Intraday continuous recalculation of the Daily Reference Prices.
- Trade execution, brokerage connectivity, personalized advice, portfolios, alerts, and accounts.
- Options, non-U.S. markets, tax analysis, or currency conversion.
- User-edited leverage factors or reference prices in authoritative calculations.
- Automatic discovery of ETF relationships solely from ticker names.
- Guaranteed Profit Ratio OHLC/candlesticks.
- A microservice decomposition for the initial release.

## 9. Acceptance criteria

The calculator area is MVP-ready when:

- A user can search from either side of a supported relationship and reach the same canonical pair.
- At least one fixture exists for every initially supported leverage sign/magnitude.
- Forward and reverse calculations reproduce each other within the documented rounding tolerance.
- The API and UI show the exact reference set and formula inputs used.
- Missing, stale, partial, and out-of-domain cases have tested, user-understandable states.
- Unit, integration, and provider contract tests pass without network access using the Mock provider.

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
- Percentage of active trading days with a valid reference set published inside the configured capture window.
- Calculator error rate by error class.
- Profit Ratio chart load success and supported-symbol coverage.
- Repeat usage of either tool without counting automated traffic.

Correctness and data freshness take priority over maximizing calculation volume.

## 11. Delivery phases

1. **Foundation:** approve contracts, formula policy, trading calendar/session rules, Profit Ratio definition, provider ports, and fixtures.
2. **Calculator vertical slice:** implement pure domain calculations and tests, Mock provider, reference capture workflow, read APIs, then the web UI.
3. **Profit Ratio vertical slice:** implement the approved metric/provider adapter, history storage and APIs, then trend and price-comparison UI.
4. **Production integration:** manually validate a licensed provider through the provider-independent overnight capture service, then add persistence, scheduling/monitoring, security, and release checks. Alpaca is the first validation adapter; Futu/OpenD remains a replaceable option.
5. **Post-MVP:** evaluate OHLC Profit Ratio, comparison tools, accounts, alerts, and additional financial tools from evidence and user feedback.

## 12. Open product decisions

These decisions must be resolved before their affected feature ships:

- Production provider and venue coverage after live SNDK/SNXX validation.
- Maximum permitted quote-time difference and capture-time tolerance for production activation. The manual prototype defaults to 5 seconds of pair skew and 90 seconds around 20:05 for real-time values.
- Whether the production snapshot price basis remains quote midpoint or changes through an approved methodology/version.
- Written public-display/redistribution rights for stored reference values and derived results.
- Correction policy when a provider later amends or invalidates a quote.
- Authoritative source and methodology for underlying/leveraged ETF relationships.
- Exact Profit Ratio definition, data rights, cadence, supported universe, and corporate-action behavior.
- Public cache duration, rate limits, and supported locales.

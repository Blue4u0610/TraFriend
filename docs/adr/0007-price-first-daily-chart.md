# ADR 0007: Price-first daily charts with independent optional indicators

Date: 2026-09-08

Status: approved product correction requested by the user; implementation in this round.

## Decision

Selecting a QQQ constituent must not depend on Profit Ratio model inputs. Search
reads stored metadata; the default chart displays genuine completed-session stock
OHLC. Daily return and Profit Ratio are independently selectable panels with separate
scales. A missing ratio displays an explicit unavailable message only in its panel.
No synthetic OHLC, ratio zero, interpolation or previous-session substitution is allowed.

Independent `market_daily_price_bars` preserves completed daily price facts and
provenance. It does not mutate `profit_ratio_capture_prices`, `profit_ratio_observations`
or calculator anchors. Raw OHLC may visibly gap across a stock split; the daily return
uses the exact previous session's close transformed to the current share basis.
It excludes dividend reinvestment and must not be described as total return.

Alpaca SIP daily O/H/L/C obey eligible consolidated trade conditions. Extended-hours
T/U prints can update daily volume without updating those prices. The stored bar
timestamp is New York midnight, not an individual auction execution. Provider bars
are used only after actual calendar session close plus 20 minutes. These are eligible
consolidated prices, not a claim of exact primary-exchange official auction values.

Two real Profit Ratio endpoint observations still cannot establish intraday ratio
highs/lows. Its optional chart remains a two-endpoint body; price candles alone have
genuine wicks. ADR 0006's missing-model-input safeguards remain unchanged.

## Metadata and operations

An empty production catalog previously made every QQQ search return no results even
after a successful code deployment. Bootstrap now initializes it using only the
verified normalized 102-equity identity/name/source/date snapshot effective 2026-09-04,
rechecked against Invesco on 2026-09-08. It includes no fund weights, private identifiers,
prices or raw issuer payload. Existing/newer snapshots are never replaced. The dated
snapshot is not a guarantee of perpetual current membership or historical NDX coverage.

This avoids market-provider calls per keystroke and vendor networking during build
migrations. Explicit `--refresh-universe` updates remain operator-controlled. Separate
bounded OHLC capture persists real data before API reads; it does not generate a new
row for a missing provider day. The existing finite OPEN/CLOSE worker also delegates
completed-price capture so local/external scheduling need not be duplicated.

Public market-data storage/display rights remain an operator prerequisite; successful
API entitlement alone does not establish redistribution permission. Neither this
change nor a user-selected indicator approves a numerical Profit Ratio methodology.

## Validation

Tests cover positive/bounded/ordered OHLC, no incomplete-session candle, explicit gaps,
same-date enforcement, immutable retries/conflicts, provider partial failures, metadata
initialization without price dependencies, DB-only reads, and independently selectable
frontend panels. Real validation must distinguish localhost from the deployed database.

Sources:

- https://docs.alpaca.markets/us/docs/market-data-faq
- https://docs.alpaca.markets/us/reference/stockbars
- https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
- https://www.invesco.com/qqq-etf/en/about.html

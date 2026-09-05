# U.S. Overnight Market-Data Provider Research

## 1. Decision status

- Researched: 2026-09-05
- Required session: 20:00-04:00 `America/New_York`, Sunday evening through Friday morning
- Scope: U.S.-listed stocks and ETFs, including leveraged ETFs
- Phase decision: implement Alpaca as the first real **manual-validation** adapter; retain Mock as the default
- Production decision: blocked on live-symbol validation and written public-display/redistribution permission
- Validation status on 2026-09-05: Mock and mocked Alpaca HTTP payloads verified. Credentialed historical `boats` results demonstrate real overnight bars for SNDK, QQQ, and TQQQ. SNXX returned no bar across the complete 20:00-04:00 ET session and no valid two-sided BOATS quote in a bounded 20:04-20:06 ET query. Live snapshot behavior remains unverified.

“Extended hours” is not treated as proof of overnight coverage. A provider qualifies only when its current official documentation explicitly covers the 20:00-04:00 ET session or identifies a venue/feed that does.

## 2. Executive conclusion

Alpaca is the best first integration for TraFriend's current engineering phase. It has a documented HTTP API, comma-separated batch symbols, true overnight `boats` and derived `overnight` feeds, latest quotes, snapshots, and historical 1-minute bars. Its free plan can validate a 20:05 snapshot using real-time **indicative** overnight quotes. Its free historical BOATS data is delayed by 15 minutes, so an exact 20:00 opening bar is not available immediately; immediate source-native BOATS access requires the $99/month Algo Trader Plus plan. See Alpaca's [24/5 feed matrix](https://docs.alpaca.markets/us/docs/245-trading-for-trading-api), [latest quotes endpoint](https://docs.alpaca.markets/us/v1.1/reference/stocklatestquotes-1), [historical bars endpoint](https://docs.alpaca.markets/us/reference/stockbars), and [plan limits](https://docs.alpaca.markets/us/docs/about-market-data-api).

This technical fit does **not** authorize production use on a public website. Alpaca's published support answer says ordinary Alpaca API data cannot be redistributed. TraFriend must obtain written commercial/public-display terms before exposing any Alpaca-derived reference value publicly. See [Alpaca's redistribution answer](https://alpaca.markets/support/redistribute-alpaca-api).

Tiingo is the strongest lower-cost alternative for source-native BOATS validation. Its new BOATS product provides real-time top-of-book, last trade, and intraday OHLC through REST and WebSocket for $39/month for individual internal use. The offering is new/beta, its subset snapshot model is less clearly documented than Alpaca's batch endpoint, and public redistribution starts with a published $500/month Tiingo fee plus a separately applicable BOATS license. See the [Tiingo BOATS product page](https://www.tiingo.com/products/boats-blue-ocean-ats-real-time-overnight-stock-prices) and [overnight API announcement](https://www.tiingo.com/blog/overnight-stock-data-api/).

Databento provides the highest-fidelity developer-accessible direct BOATS feed considered here, including OHLCV-1m and precise event/receive timestamps. It is materially more expensive for live/public use and is unnecessary for a once-daily reference capture. See the [OCEA.MEMOIR dataset](https://databento.com/docs/venues-and-datasets/ocea-memoir) and [venue licensing guide](https://databento.com/docs/api-reference-live/basics/metered-pricing).

## 3. Ranking for TraFriend

| Rank | Provider | True overnight | Best use for TraFriend | Decision |
|---:|---|---|---|---|
| 1 | Alpaca | Yes: BOATS and derived Overnight | Lowest-friction free prototype; mature batch REST; $99 immediate BOATS option | Implement manual adapter now; no public production use without license |
| 2 | Tiingo | Yes: direct BOATS | Lowest published price for internal real-time direct BOATS; simple REST | Validate next if Alpaca indicative pricing is insufficient |
| 3 | Databento | Yes: direct BOATS MEMOIR | Highest-fidelity real-time/historical venue data | Defer because cost and licensing exceed MVP needs |
| 4 | Futu OpenAPI/OpenD | Yes: documented 24H K-lines/snapshots with permissions | Existing Futu account deployments | Keep as a future adapter; do not hardcode |
| 5 | Interactive Brokers | Yes: IBKR Overnight, normally to 03:50 ET | Brokerage-linked fallback | Defer because gateway/session/routing operations are heavier |
| 6 | Direct Blue Ocean ATS | Yes | Institutional direct feed | Not practical for MVP |

Massive/Polygon, Twelve Data, Finnhub, Tiingo's ordinary equity feeds, and Intrinio's documented Nasdaq Basic product do not independently establish true 20:00-04:00 coverage. They are not candidates unless their official contracts and documentation change.

## 4. Detailed evaluation

### 4.1 Alpaca Market Data

1. **True overnight:** Yes. The documented overnight session is 20:00-04:00 ET and is powered by BOATS plus Alpaca's derived `overnight` feed.
2. **Data available:** Bars, quotes, trades, latest endpoints, snapshots, and WebSocket streams.
3. **First 1-minute bar:** Yes. `GET /v2/stocks/bars` accepts `timeframe=1Min`, start/end, and `feed=boats`. Select the first returned bar at or after session open.
4. **Batch symbols:** Yes. Bars and latest quotes accept comma-separated symbols. This is a strong fit for one underlying plus all associated leveraged ETFs.
5. **Latency:** Free `overnight` latest quotes are real-time indicative; free latest trades are 15-minute delayed. Free historical `boats` bars/trades/quotes are 15-minute delayed. Paid `boats` is real-time.
6. **Free tier:** $0; 200 historical API calls/minute; 30 WebSocket symbols; historical requests cannot include the most recent 15 minutes. Enough for a once-per-session 20:05 indicative-quote snapshot and a delayed opening-bar verification.
7. **Likely paid tier:** Algo Trader Plus, $99/month, for immediate source-native BOATS quotes/trades/bars and no recent-data restriction. A public/business product requires separate commercial permission regardless of this individual plan price.
8. **Rate limits:** 200 historical calls/minute free; 10,000/minute on Algo Trader Plus. TraFriend should normally use one batch request per capture method.
9. **Authentication:** Backend-only `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY` headers.
10. **Local gateway:** No. HTTPS REST and WebSocket endpoints are hosted by Alpaca.
11. **Cloud deployment:** Easy. Stateless outbound HTTPS; credentials live only in the backend secret store.
12. **History:** Alpaca's stock history generally starts in 2016, but overnight availability depends on when the BOATS/overnight feed began and the selected entitlement. Exact overnight history must be probed for each required symbol/date.
13. **Reliability/docs:** Good documentation, explicit feed values, payload schemas, HTTP status behavior, and an official status page. The derived `overnight` feed is documented as cheaper and slightly less accurate than original BOATS.
14. **Public display/redistribution:** Not included by default. Alpaca explicitly says API data cannot be redistributed. Obtain written terms before production display.
15. **Implementation complexity:** Low. A small `httpx` adapter can normalize REST payloads without an SDK.

Important interpretation:

- `OVERNIGHT_SNAPSHOT` on the free plan uses the bid/ask midpoint from the batch latest-quote endpoint with `feed=overnight`. It is marked `REALTIME`, while provenance says `source_feed=overnight` and `price_basis=QUOTE_MIDPOINT`; it must not be described as a BOATS last trade.
- `OVERNIGHT_OPEN` uses `feed=boats` 1-minute bars. With free access it is marked `DELAYED` and can only be retrieved once the requested end time is at least 15 minutes old.
- Paid `boats` access can make both methods source-native and real-time. Exact entitlement behavior must still be verified with the actual account.
- Alpaca's Assets API exposes `overnight_tradable`; the supported universe should be checked shortly before a capture, but provider eligibility must not replace TraFriend's curated underlying/ETF relationship universe.

### 4.2 Tiingo BOATS

1. **True overnight:** Yes, direct Blue Ocean ATS from 20:00-04:00 ET.
2. **Data available:** Top-of-book bid/ask/mid, last trade price/size, real-time WebSocket updates, REST snapshots, and overnight intraday OHLC.
3. **First 1-minute bar:** The historical `/boats/{ticker}/prices` endpoint supplies overnight OHLC intervals; exact 1-minute interval and opening-boundary behavior must be confirmed against the authenticated API schema during a trial.
4. **Batch symbols:** `/boats` returns a snapshot of every overnight symbol in one request. Per-ticker latest and historical routes are documented. A filtered batch subset is not clearly documented in the public overview.
5. **Latency:** Real-time direct BOATS.
6. **Free tier:** BOATS is not available on Free.
7. **Likely paid tier:** Individual Power $30/month plus BOATS $9/month, total $39/month, for internal use. Commercial internal is $50+$9. Redistribution lists a $500/month Tiingo fee plus a BOATS license fee.
8. **Rate limits:** Power: 10,000 requests/hour, 100,000/day, 40 GB/month. Commercial: 20,000/hour, 150,000/day, 100 GB/month.
9. **Authentication:** HTTPS `Authorization: Token ...`.
10. **Local gateway:** No.
11. **Cloud deployment:** Easy for REST; a WebSocket is unnecessary for TraFriend's once-daily capture.
12. **History:** Overnight intraday OHLC is advertised, but retention depth and corrections need authenticated validation.
13. **Reliability/docs:** Tiingo has a long-running API platform, but the BOATS product itself launched in 2026 and is identified as a new/beta feature in its changelog. Public endpoint overviews are clear; exact payload/version guarantees need trial validation.
14. **Public display/redistribution:** Individual and commercial self-service tiers are internal-use only. Public use requires the redistribution tier and BOATS licensing.
15. **Implementation complexity:** Low to medium. REST is simple; consuming the all-symbol snapshot efficiently and confirming its schema/retention are the main unknowns.

### 4.3 Databento OCEA.MEMOIR

1. **True overnight:** Yes, directly captured Blue Ocean ATS MEMOIR from 20:00-04:00 ET.
2. **Data available:** MBO/L3, MBP-1/L1, MBP-10, trades, BBO, OHLCV-1s, OHLCV-1m, status, and definitions.
3. **First 1-minute bar:** Yes, OHLCV-1m is a native documented schema.
4. **Batch symbols:** Historical API supports up to 2,000 symbols and merges results by time. Live supports broad subscriptions.
5. **Latency:** Live is real-time; historical is available after a 15-minute delay and next-day releases are also documented.
6. **Free tier:** New accounts receive $125 in historical credits; there is no equivalent free live BOATS tier.
7. **Likely paid tier:** Historical is usage-based from $0.40/GB. Live BOATS requires a Plus or Unlimited U.S. Equities subscription; current pricing and venue licenses must be quoted/confirmed in the portal. Public use also incurs venue fees.
8. **Rate limits:** Historical: 100 time-series requests/sec, 100 concurrent connections, and 2,000 symbols per batch request. Live is streaming rather than polling.
9. **Authentication:** API key.
10. **Local gateway:** No. Official client libraries or HTTP historical API; live uses Databento's streaming protocol/client.
11. **Cloud deployment:** Good, but operationally more elaborate than one REST snapshot because its strengths are streaming and full-depth data.
12. **History:** BOATS coverage begins 2025-08-24.
13. **Reliability/docs:** Excellent feed provenance and nanosecond event/receive timestamps; direct capture in NY4; thorough schema and licensing documentation.
14. **Public display/redistribution:** Explicit venue licenses apply. Databento lists Blue Ocean commercial fees such as $1,500/firm display and separate distribution/user fees; confirm the exact use case with sales.
15. **Implementation complexity:** Medium. High data fidelity, but overpowered and costly for two reference points per symbol per day.

### 4.4 Futu OpenAPI / OpenD

1. **True overnight:** Yes, subject to version and quote rights. Historical U.S. K-lines support `session=ALL` for 24H data; overnight-only is not an allowed historical-session selector.
2. **Data available:** Real-time quotes, snapshots, K-lines, and subscriptions. Snapshot fields include overnight session information.
3. **First 1-minute bar:** Yes, request U.S. 1-minute historical K-lines with `session=ALL`, then filter the 20:00-04:00 ET window inside TraFriend.
4. **Batch symbols:** Snapshot requests support up to 400 symbols. Historical K-line calls are primarily per security.
5. **Latency:** Depends on the account's U.S. quote entitlement and subscription level; do not label data real-time without reading OpenD's quote-right result.
6. **Free tier:** There is no provider-independent free guarantee. Availability depends on region, account, holdings/activity, and quote permissions.
7. **Likely paid tier:** Account/market-data permissions rather than a simple universal API price. Must be verified on the intended Futu/moomoo account.
8. **Rate limits:** Historical K-lines: 60 requests/30 seconds, plus rolling quota based on unique securities. Snapshots: 60 requests/30 seconds and up to 400 securities/request.
9. **Authentication:** OpenD login plus local socket client; quote subscriptions and rights are account-bound.
10. **Local gateway:** Yes. OpenD is mandatory and must remain logged in/running.
11. **Cloud deployment:** Medium to high complexity. Requires a persistent supported OS host, OpenD process lifecycle, secure login/bootstrap, health monitoring, and reconnect handling.
12. **History:** 1-minute overnight history is documented, potentially for less than two years depending on data availability and quota.
13. **Reliability/docs:** Detailed official protocol/API docs, but more operational states and permissions than REST.
14. **Public display/redistribution:** Quote rights are subscriber/account-specific. Public web redistribution needs separate written permission; do not infer it from brokerage access.
15. **Implementation complexity:** High relative to Alpaca/Tiingo. Keep as a replaceable future adapter.

Sources: [OpenD overview](https://openapi.futunn.com/futu-api-doc/en/opend/opend-intro.html), [historical K-line](https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html), [market snapshot](https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html), [quote permissions](https://openapi.futunn.com/futu-api-doc/en/intro/authority.html), and [subscriptions](https://openapi.futunn.com/futu-api-doc/en/quote/sub.html).

### 4.5 Interactive Brokers

1. **True overnight:** Yes. IBKR documents U.S. stock/ETF trading and data from 20:00 to 03:50 ET, with a ten-minute break before 04:00.
2. **Data available:** Streaming quotes/ticks and historical OHLC through TWS/Client Portal APIs; overnight data must be requested from the overnight exchange rather than assumed from SMART routing.
3. **First 1-minute bar:** Technically possible through historical market data with the overnight exchange/outside-RTH settings; exact venue selection needs contract-level tests.
4. **Batch symbols:** Snapshot endpoints can take multiple conids, but historical bars are one conid per request and limited in concurrency.
5. **Latency:** Real-time with U.S. trading permission; delayed modes exist for other entitlements.
6. **Free tier:** IBKR says overnight U.S. stock market data is free with the relevant trading permission.
7. **Likely paid tier:** No separate advertised overnight data fee, but a brokerage account and market/trading permissions are required.
8. **Rate limits:** Client Portal Web API generally limits requests and historical concurrency; current endpoint-specific limits must be honored. Historical requests are constrained more tightly than Alpaca batch bars.
9. **Authentication:** Authenticated brokerage session; Client Portal/TWS session lifecycle.
10. **Local gateway:** Yes for individual Client Portal use, or TWS/IB Gateway for socket API workflows.
11. **Cloud deployment:** High operational complexity because sessions must be kept alive, periodically reauthenticated, and survive maintenance windows.
12. **History:** Available, but duration and bar limits vary by endpoint/instrument.
13. **Reliability/docs:** Mature broker APIs, but market-data routing/session behavior is less direct than a purpose-built REST token API.
14. **Public display/redistribution:** Brokerage market-data access is not a public redistribution license. Written approval is required.
15. **Implementation complexity:** High.

Sources: [IBKR overnight session](https://www.interactivebrokers.com/en/trading/us-overnight-trading.php), [IBKR API overnight routing note](https://ibkrcampus.com/campus/ibkr-quant-news/api-overnight-trading/), [historical data endpoint](https://ibkrcampus.com/docs/web-api/api-reference/trading/trading-market-data/get-md-history), and [authentication FAQ](https://ibkrcampus.com/docs/web-api/authentication/faq).

### 4.6 Direct Blue Ocean ATS

1. **True overnight:** Yes; it is the venue source.
2. **Data available:** Direct depth/order and trade feeds, depending on agreement.
3. **First 1-minute bar:** Must be built from direct events or obtained through a redistributor; the venue does not advertise a simple developer bar REST endpoint.
4. **Batch symbols:** Feed subscription model, not a lightweight batch REST request.
5. **Latency:** Real-time direct feed.
6. **Free tier:** None documented.
7. **Likely paid tier:** Institutional, contact sales, data-license and connectivity costs.
8. **Rate limits:** Protocol/subscription limits rather than retail HTTP quotas.
9. **Authentication:** Contracted technical connectivity.
10. **Local gateway:** Specialized feed handler/connectivity required.
11. **Cloud deployment:** High complexity.
12. **History:** Depends on the chosen redistributor/contract.
13. **Reliability/docs:** Venue-grade, but not packaged as the simple documented HTTP API preferred by TraFriend.
14. **Public display/redistribution:** Explicit BOATS license required.
15. **Implementation complexity:** Very high for the MVP.

Sources: [Blue Ocean trading updates](https://www.blueocean-tech.io/trading-updates/) and [Blue Ocean FAQ](https://my.blueocean-tech.io/faq/boats-offering).

## 5. Providers that do not currently qualify

| Provider | Officially documented coverage | Why it is rejected for this phase |
|---|---|---|
| Massive / Polygon | 04:00-20:00 ET pre-market, regular, and after-hours | Official docs do not include 20:00-04:00; [hours documentation](https://massive.com/knowledge-base/article/market-data-outside-of-normal-hours) |
| Twelve Data | Real-time extended hours 07:00-20:00 and historical 04:00-20:00 | Not true overnight; [pre/post-market documentation](https://support.twelvedata.com/en/articles/5195429-pre-post-market-data) |
| Intrinio Nasdaq Basic | Pre/post market via Nasdaq Basic | No official BOATS/20:00-04:00 entitlement found; [product page](https://intrinio.com/financial-market-data/nasdaq-basic) says pre/post, not overnight |
| Finnhub | Generic quote/candle/stream APIs | No official public documentation found that identifies BOATS or guarantees 20:00-04:00 U.S. equity coverage; do not infer it from “real-time” |
| Tiingo ordinary stock APIs | IEX/EOD/general equity products | Only the separate BOATS add-on qualifies; ordinary Tiingo plans alone do not |

These providers can be reconsidered only after an official feed/venue document and redistribution terms explicitly cover the required overnight window.

## 6. Unofficial/private endpoints

No unofficial endpoint is selected. Broker web/mobile endpoints may display overnight prices, but automating them would introduce:

- high stability risk because payloads and authentication can change without notice;
- Terms of Service and redistribution risk;
- session-cookie, MFA, and credential-handling risk;
- undocumented throttling and blocking risk;
- ambiguous data provenance, timestamp, and delay semantics.

Web scraping or private endpoints require explicit product, legal, and security approval and are not a fallback in this architecture.

## 7. Manual validation gates before scheduling

### 7.1 Credentialed historical evidence

Credentialed Alpaca `boats` checks for trading date 2026-09-04 produced the following real historical results:

- SNDK was available at 20:00 ET with an opening price of `1551`; SNXX returned no valid one-minute bar during the configured 20:00-20:15 ET `OVERNIGHT_OPEN` search window, so the pair was `PARTIAL`.
- QQQ's first valid bar was at 20:02 ET with an opening price of `717.41`; TQQQ's first valid bar was at 20:00 ET with an opening price of `71.88`. Both were available, so the capture was `VALID`, but their first-trade timestamps differed by 120 seconds.

These initial opening-window results demonstrated that the historical Alpaca BOATS path works and that leveraged ETFs are not systematically absent from the feed. At that point, they did not establish whether SNXX had no BOATS data during the entire session or merely had no trade in the first 15 minutes.

A follow-up credentialed full-session query resolved that question for the same trading date:

- SNDK returned `231` one-minute bars. Its first bar was 20:00 ET with OHLC `1551/1551/1551/1551` and volume `137`; its last bar was 03:54 ET with close `1580.3`.
- SNXX returned `0` one-minute bars from 20:00 through 04:00 ET. Its classification is therefore `NO OVERNIGHT TRADE DATA`, not merely a later first trade outside the opening window.
- A historical `feed=boats` quote query bounded to 20:04-20:06 ET returned `2241` valid two-sided SNDK quotes and no valid two-sided SNXX quote. The nearest SNDK quote to 20:05 was timestamped 20:05:00.016402 ET, with bid `1550.55`, ask `1553.85`, and midpoint `1552.20`; it was labeled `DELAYED` under the free-plan configuration.
- Because SNXX had no valid quote in that window, a SNDK/SNXX timestamp difference could not be calculated and a synchronized quote-based reference was not feasible for this historical session.

This negative result means the historical SNDK/SNXX evidence does not yet support adopting `OVERNIGHT_SNAPSHOT` as TraFriend's calculator reference method. It still supports a real live batch snapshot test: historical BOATS query availability is not equivalent to what the documented derived `overnight` latest-quote feed may return at 20:05.

The QQQ/TQQQ result also shows that independently selected first-trade opens are not inherently synchronized: a complete pair can represent market events two minutes apart. That timing mismatch can distort a leveraged relationship calculation during a moving market. It is evidence for evaluating a synchronized `OVERNIGHT_SNAPSHOT` as the eventual calculator default; it does not change the current `OVERNIGHT_OPEN` policy.

Alpaca's documented historical quotes endpoint supports `feed=boats`, bounded `start`/`end` timestamps, and both single-symbol and batch queries. The credentialed result above confirms the endpoint works for SNDK but returned no valid SNXX bid/ask around 20:05 ET for this session. See Alpaca's [historical quotes endpoint](https://docs.alpaca.markets/us/reference/stockquotes-1) and [24/5 feed matrix](https://docs.alpaca.markets/us/docs/245-trading-for-trading-api).

### 7.2 Remaining validation gates

Do not implement a production scheduler until all of these pass on the intended account:

1. Confirm `SNDK` and `SNXX` are returned and marked overnight eligible.
2. At approximately 20:05 ET, capture both in one batch and compare their provider timestamps and the midpoint against the provider UI/another licensed source.
3. Verify whether `feed=overnight` timestamps represent a synchronized indicative quote for both symbols.
4. After 20:15 ET on the free plan, request `feed=boats` 1-minute bars starting at 20:00 ET and confirm the first bar/open semantics.
5. On a paid trial, repeat the bar request immediately after 20:00 and confirm no 15-minute restriction.
6. Test a no-trade-at-20:00 symbol and confirm the first later bar is used without prior-session fallback.
7. Test a missing leveraged ETF and confirm the pair remains partial/unpublished.
8. Obtain written provider/venue terms for public display of stored reference prices and derived calculations.
9. Record any correction policy, historical retention, corporate-action adjustment, and outage behavior observed in the trial.

Until these gates pass, Alpaca is a validation adapter, Mock remains the default, and no captured real-provider value should be published to end users.

## 8. SNDK / SNXX relationship verification

The curated supported universe maps SNDK to SNXX at `+2x`. This was rechecked against the current SEC summary prospectus for the **Tradr 2X Long SNDK Daily ETF**, ticker SNXX. The filing states that the fund seeks 200% of the daily performance of Sandisk common shares. The relationship is therefore correct as of this research date. It is not inferred from ticker text, and the issuer is Tradr/AXS rather than GraniteShares. See the [SEC summary prospectus](https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm).

The fund completed an 8-for-1 forward split in June 2026. That changes the ETF's per-share price but not its `+2x` daily objective; reference prices must come from same-session post-corporate-action market data. See the [SEC split supplement](https://www.sec.gov/Archives/edgar/data/1587982/000121390026057930/ea0291169-05_497.htm).

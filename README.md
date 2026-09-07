# TraFriend

TraFriend 是一个面向美股投资者的市场分析工具。当前产品聚焦于：

- 正股 / 普通 ETF 与杠杆 ETF 的单日理论价格换算
- 当前及历史获利比（Profit Ratio）分析

TraFriend 仅用于信息、教育与研究，不提供投资建议、交易执行、券商服务或收益保证。

---

## 中文

### 杠杆 ETF 单日价格计算器

计算器根据一只正股或普通 ETF 与对应杠杆 ETF 的每日收益目标，进行双向理论换算。例如：

- SNDK ↔ SNXX（`+2x`）
- NVDA ↔ NVDL（`+2x`）
- TSLA ↔ TSLL（`+2x`）
- QQQ ↔ QLD（`+2x`）、TQQQ（`+3x`）、SQQQ（`-3x`）
- SOXX ↔ SOXL（`+3x`）、SOXS（`-3x`）

这些关系来自明确配置，不会根据 ticker 名称自动猜测。

### 2026 年 9 月热门股票

热门列表使用已完成交易日的 Alpaca SIP 每日数据，按 `每日 VWAP × 每日成交量` 求和后生成 9 月月初至今美元成交额 Top 100。排名通过交易所日历确定覆盖日期，并与杠杆 ETF 关系和每日收盘锚点分开存储。没有经核验杠杆产品的股票仍可显示，但会明确标记为 0 个支持产品。

### 每日收盘锚点

计算器使用 `DAILY_CLOSE_ANCHOR`：两只产品在最近一个已完成的美国常规交易时段、同一交易日的收盘价。

例如，假设同一交易日的锚点是：

```text
NVDA 收盘价：$170.00
NVDL 收盘价：$80.00
```

用户输入 NVDA 目标价 `$180.00` 时：

```text
NVDA 理论涨幅 = 180 / 170 - 1 ≈ 5.88%
NVDL 理论涨幅 = 2 × 5.88% ≈ 11.76%
NVDL 理论目标价 ≈ $89.41
```

反向计算使用相同锚点与相同的有符号杠杆倍数，从杠杆 ETF 目标价反推标的资产理论目标价。

系统通过交易所日历判断“最近一个已完成交易时段”，包括收盘前后、周末、节假日和提前收盘日。只有两项数据都属于预期的同一交易日且有效时，才允许计算；不会静默使用前一交易日数据、缺失值或零值。

### 为什么使用常规交易时段收盘价？

大多数杠杆及反向 ETP 的目标是单日收益倍数，并每日重置风险敞口；FINRA 将该目标通常描述为从一个交易日收盘到下一交易日收盘。SNXX 的发行文件将单个交易日描述为从一次 NAV 计算到下一次 NAV 计算，并说明基金预计每日再平衡。

因此，TraFriend 把最近一个已完成常规交易时段的收盘价作为计算锚点。这里“20:00 夜盘开盘不是重置点”是根据上述 NAV-to-NAV、close-to-close 与每日再平衡定义得出的结论；相关资料并未把 20:00 定义为重置时点。

- [SNXX Summary Prospectus（SEC）](https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm)
- [FINRA：Leveraged and Inverse ETPs](https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products)

### 如何理解结果

计算公式是单日线性理论关系：

```text
标的收益率 = 标的目标价 / 标的收盘锚点 - 1
杠杆收益率 = 有符号杠杆倍数 × 标的收益率
杠杆 ETF 理论目标价 = 杠杆 ETF 收盘锚点 × (1 + 杠杆收益率)
```

这不是实际成交价保证，也不是多日预测。实际 ETF 价格可能因买卖价差、相对 NAV 的溢价或折价、跟踪误差、融资与费用、流动性、市场状况、分红及公司行为而不同。

杠杆 ETF 每日重置，因此多日收益具有路径依赖和复利效应。不能把标的资产的多日累计收益率简单乘以杠杆倍数来预测 ETF 的多日收益。

### 隔夜市场诊断

TraFriend 保留 Alpaca BOATS 隔夜开盘、快照与历史数据诊断能力，用于研究数据覆盖、流动性和时间同步。这些诊断不属于计算器的 `DAILY_CLOSE_ANCHOR`，也不会改变计算公式的锚点。

### 获利比

TraFriend 计划展示当前与历史获利比，并配合价格序列观察变化。获利比取决于具体数据提供方和计算方法；在正式采用真实数据前，必须明确并展示 methodology、版本、时间、交易日与质量状态。系统不会猜测定义、填补缺失值或混合不兼容的方法版本。

---

## English

### Single-day leveraged ETF calculator

The calculator translates a theoretical single-day target in either direction between an underlying stock or ordinary ETF and a configured leveraged ETF. Supported relationships are curated metadata—not inferred from ticker names—and include SNDK/SNXX, NVDA/NVDL, TSLA/TSLL, QQQ/QLD/TQQQ/SQQQ, and SOXX/SOXL/SOXS with their signed daily leverage factors.

### September 2026 popular stocks

The Popular list is a September-to-date Top 100 calculated from completed-session Alpaca SIP daily data using `SUM(daily VWAP × daily share volume)`. Exchange-calendar dates, source, coverage, and calculation time are persisted separately from leveraged-product relationships and Daily Close Anchors. A ranked stock with no verified TraFriend leveraged product remains visible with a supported-product count of zero.

### Daily Close Anchor

The calculator uses `DAILY_CLOSE_ANCHOR`: the closing prices of both instruments from the same latest completed U.S. regular trading session.

For example, with same-date closes of NVDA `$170.00` and NVDL `$80.00`, an NVDA target of `$180.00` represents a theoretical `5.88%` underlying move. At a `+2x` daily objective, the theoretical NVDL move is `11.76%`, producing a target near `$89.41`.

An exchange calendar determines the latest completed session across before/after-close times, weekends, holidays, and early closes. Calculation is enabled only for a valid pair on the exact expected trading date. Missing, mixed-date, lagging, stale, and zero values are never silently substituted.

### Why the regular-session close?

Most geared ETPs seek a daily return multiple and reset exposure each day. FINRA describes that daily objective as generally measured close-to-close. SNXX's issuer filing defines one trading day from one NAV calculation to the next and describes daily rebalancing.

TraFriend therefore uses the completed regular-session close as its calculator anchor. The conclusion that 20:00 ET is not a reset boundary is an inference from those NAV-to-NAV, close-to-close, and daily-rebalancing definitions; the cited sources do not define an overnight opening as the reset.

- [SNXX Summary Prospectus (SEC)](https://www.sec.gov/Archives/edgar/data/1587982/000121390026008044/ea0273211-04_497k.htm)
- [FINRA on leveraged and inverse ETPs](https://www.finra.org/investors/insights/lowdown-leveraged-and-inverse-exchange-traded-products)

### Formula and limitations

```text
underlying_return = underlying_target / underlying_close_anchor - 1
leveraged_return  = signed_leverage_factor × underlying_return
leveraged_target  = leveraged_close_anchor × (1 + leveraged_return)
```

The reverse direction uses the same anchors and divides the leveraged return by the signed leverage factor.

This is a single-day theoretical estimate, not a guaranteed traded price or a multi-day forecast. Actual prices may differ because of bid/ask spreads, premium or discount to NAV, tracking error, financing and fees, liquidity, market conditions, distributions, and corporate actions.

Daily reset makes multi-day performance path-dependent. A leverage factor multiplied by the underlying's cumulative multi-day return is not a valid forecast; daily returns compound from changing bases.

### Overnight diagnostics

TraFriend retains Alpaca BOATS overnight-open, snapshot, and historical diagnostic capabilities for data-coverage, liquidity, and synchronization research. They are separate from `DAILY_CLOSE_ANCHOR` and are not calculator inputs.

### Profit Ratio

TraFriend plans to show current and historical Profit Ratio observations alongside prices. Profit Ratio is provider- and methodology-dependent. A real implementation must display methodology/version, observation time, trading date, provenance, and quality; it must not guess definitions, fill gaps silently, or merge incompatible methodologies.

## Disclaimer

TraFriend is for informational, analytical, educational, and research purposes only. It does not provide investment advice, brokerage services, trade execution, or guarantees about data, calculations, or market outcomes.

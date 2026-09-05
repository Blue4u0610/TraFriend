# TraFriend

TraFriend 是一个面向美股投资者的轻量化金融分析工具，旨在把一些常用但分散、计算繁琐或不够直观的市场数据整理成简单易用的网页工具。

目前 TraFriend 主要聚焦于两个方向：

* **正股 / ETF 与杠杆 ETF 价格换算**
* **获利比（Profit Ratio）历史分析**

后续将持续加入更多实用的美股分析工具。

---

# 中文

## 主要功能

### 1. 正股 / ETF 与杠杆 ETF 价格换算

TraFriend 可以根据每天获取的市场参考价格以及杠杆 ETF 的目标杠杆倍数，估算正股、普通 ETF 与对应杠杆 ETF 之间的理论价格关系。

例如：

* NVDA ↔ NVDL
* QQQ ↔ TQQQ
* QQQ ↔ SQQQ
* SOXX ↔ SOXL
* TSLA ↔ TSLL

用户可以：

* 输入正股或普通 ETF 的目标价格，估算对应杠杆 ETF 的理论价格
* 输入杠杆 ETF 的目标价格，反推正股或普通 ETF 需要达到的价格
* 输入目标涨跌幅进行换算
* 查看正股与杠杆 ETF 对应的理论涨跌幅
* 在同一标的存在多个杠杆 ETF 时进行切换和比较
* 支持多头、反向以及不同杠杆倍数的 ETF

---

## 每日参考价格机制

为了让每天的价格换算尽可能贴近实际市场情况，TraFriend 不会长期使用一组固定价格作为计算基础。

系统计划在：

> **每天美股夜盘开始时获取一次最新市场价格**

并同时记录正股 / 普通 ETF 与对应杠杆 ETF 的价格，作为当天价格换算的 **每日参考价格（Daily Reference Price）**。

例如，当天系统记录：

```text
NVDA 每日参考价：$170.00
NVDL 每日参考价：$80.00
```

如果用户输入：

```text
NVDA 目标价格：$180.00
```

TraFriend 会首先计算 NVDA 相对于当天参考价格的变化：

```text
170 → 180

涨幅约 +5.88%
```

如果 NVDL 的目标日杠杆为 `+2x`，则理论涨幅约为：

```text
+11.76%
```

从而得到：

```text
NVDL 理论价格 ≈ $89.41
```

也就是说，TraFriend 的换算并不是根据正股与杠杆 ETF 的绝对价格比例进行计算，而是：

> **以每天重新获取的市场价格作为基准，根据标的价格变化幅度和 ETF 的目标日杠杆倍数进行估算。**

---

## 为什么每天重新获取参考价格？

杠杆 ETF 并不是简单地维持：

```text
ETF 价格 = 正股价格 × 杠杆倍数
```

它们通常追踪的是标的资产的 **每日收益率倍数**。

因此随着市场每天波动，正股与杠杆 ETF 之间的绝对价格关系也会不断发生变化。

例如，即使 NVDA 后来再次回到某个历史价格，NVDL 也不一定回到之前对应的价格。

原因可能包括：

* 每日杠杆重置
* 复利效应
* 波动损耗
* ETF 管理费用
* 跟踪误差
* 分红与公司行为
* 不同交易时段的市场变化

因此，TraFriend 会每天重新获取一组最新价格作为新的计算起点。

这可以降低长期使用旧价格所产生的换算误差。

---

## 如何理解换算结果？

TraFriend 的杠杆 ETF 换算结果属于：

> **基于当日参考价格的单日理论估算**

而不是对未来 ETF 价格的预测。

例如：

```text
今日参考价格

NVDA    $170
NVDL     $80
```

用户输入：

```text
NVDA → $180
```

得到：

```text
NVDL → ≈ $89.41
```

表示的是：

> 如果从当前每日参考价格出发，NVDA 在相同的日度计算区间内上涨至 $180，并且 NVDL 大致实现其目标 `2x` 日收益，那么 NVDL 的理论价格约为 $89.41。

如果跨越多个交易日，实际结果可能明显不同。

因此换算结果应该理解为一个 **价格关系参考工具**，而不是长期价格预测模型。

---

## 每日价格更新时间

TraFriend 会显示当前使用的参考价格以及最近一次更新时间，例如：

```text
NVDA
Reference Price
$170.00

NVDL
Reference Price
$80.00

Updated
Sep 5, 2026 · Overnight Session
```

这样用户可以清楚知道当前换算使用的是哪一天的市场基准价格。

当新的交易日参考价格更新后，当天所有目标价格换算都会自动基于新的参考价格重新计算。

---

# 2. 获利比分析

TraFriend 计划提供美股的 **获利比（Profit Ratio）** 查询和历史趋势分析。

获利比可以简单理解为：

> 在当前股票价格下，估算处于盈利状态的筹码占全部筹码的比例。

例如：

```text
NVDA

当前获利比
82.6%
```

相比单独查看某一天的获利比，TraFriend 更希望帮助用户观察：

> **获利比是如何随时间变化的。**

---

## 历史获利比

TraFriend 计划记录并展示历史获利比数据，例如：

```text
日期            获利比

Sep 1           65.2%
Sep 2           71.8%
Sep 3           68.4%
Sep 4           77.1%
Sep 5           82.6%
```

用户可以通过图表观察：

* 当前获利比
* 历史获利比走势
* 不同时间周期的变化
* 股价与获利比之间的关系
* 市场筹码盈利状态的变化

---

## 获利比图表

TraFriend 计划提供多种方式展示获利比，包括：

* 历史趋势图
* 股价与获利比组合图
* 不同时间范围切换
* OHLC / K 线形式的获利比展示

例如：

```text
Stock Price
──────────────────────────

          ╭─────╮
     ╭────╯     ╰───
─────╯

Profit Ratio
──────────────────────────

       ╭────╮       ╭────
───────╯    ╰───────╯
```

这样用户不仅能看到：

```text
当前获利比 = 82.6%
```

还能够判断：

```text
过去一段时间获利比是在持续上升，
还是从高位快速下降。
```

---

# TraFriend 想解决什么问题？

很多美股分析中经常出现这样的实际问题：

```text
“NVDA 涨到 $200，NVDL 大概是多少？”

“TQQQ 到 $100，QQQ 大概需要到多少？”

“今天这个换算应该以什么价格为基准？”

“NVDA 现在有多少筹码处于盈利状态？”

“过去几个月获利比是怎么变化的？”
```

这些问题本身并不一定复杂，但相关数据和工具往往分散在不同的平台里。

TraFriend 希望把它们变成更加简单的流程：

> **搜索标的 → 输入目标 → 直接获得结果**

以及：

> **搜索股票 → 查看指标 → 观察历史变化**

减少重复计算以及在多个金融平台之间切换的成本。

---

# 未来计划

TraFriend 并不会只做两个工具。

未来计划逐步加入更多美股分析功能，例如：

* 更多正股与杠杆 ETF 对应关系
* 多个杠杆 ETF 同时比较
* 历史获利比
* 筹码分布分析
* 资金流分析
* 波动率工具
* 仓位计算
* 风险收益计算
* 做空数据
* 更多市场指标
* 历史回测工具

TraFriend 希望最终发展成为一个：

> **简单、直观、实用的美股分析工具箱。**

---

# 项目状态

TraFriend 目前仍处于早期开发阶段。

当前开发顺序主要为：

```text
杠杆 ETF 价格换算
        ↓
每日市场参考价格
        ↓
更多正股 / ETF 映射
        ↓
获利比查询
        ↓
历史获利比
        ↓
更多市场分析工具
```

功能、数据来源、计算方式以及用户界面仍会持续优化。

---

# 风险提示

TraFriend 提供的所有数据、计算结果和分析工具仅用于信息展示、学习和研究用途。

杠杆 ETF 的目标价格属于基于每日参考价格及目标日杠杆倍数计算出的 **理论估算值**，不代表未来实际成交价格。

实际市场表现可能受到以下因素影响：

* 市场波动
* 每日杠杆重置
* 复利效应
* 波动损耗
* ETF 费用
* 跟踪误差
* 流动性
* 买卖价差
* 公司行为
* 市场交易时段差异

TraFriend 不提供投资建议，也不保证任何数据、计算结果或分析结果的完整性、实时性或准确性。

任何投资决策均应由用户自行判断，并自行承担相应风险。

---

# English

TraFriend is a lightweight financial analytics platform designed for U.S. stock market investors.

It aims to turn commonly used but scattered market calculations and indicators into simple and intuitive web-based tools.

TraFriend currently focuses on:

* **Underlying / Leveraged ETF Price Estimation**
* **Profit Ratio Analytics**

More market tools will be added over time.

---

# Features

## 1. Leveraged ETF Price Calculator

TraFriend estimates the theoretical price relationship between an underlying stock or ETF and its associated leveraged ETFs.

Examples include:

* NVDA ↔ NVDL
* QQQ ↔ TQQQ
* QQQ ↔ SQQQ
* SOXX ↔ SOXL
* TSLA ↔ TSLL

Users can:

* Enter an underlying target price and estimate the corresponding leveraged ETF price
* Enter a leveraged ETF target price and reverse-calculate the required underlying price
* Enter a target percentage move
* Compare theoretical percentage changes
* Switch between multiple leveraged products associated with the same underlying
* Work with long, inverse, and different leverage ratios

---

## Daily Reference Prices

To keep price estimates as closely aligned with current market conditions as possible, TraFriend does not rely on a permanently fixed pair of reference prices.

The system is designed to:

> **Capture the latest market prices once at the beginning of each U.S. overnight trading session.**

The prices of both the underlying asset and its leveraged ETF are recorded as the **Daily Reference Prices** used for that day's calculations.

For example:

```text
NVDA Daily Reference Price: $170.00
NVDL Daily Reference Price: $80.00
```

If the user enters:

```text
NVDA Target Price: $180.00
```

the underlying move is approximately:

```text
$170 → $180

+5.88%
```

For a `+2x` leveraged ETF, the theoretical daily move would be approximately:

```text
+11.76%
```

resulting in an estimated price of:

```text
NVDL ≈ $89.41
```

TraFriend therefore does not calculate leveraged ETF prices using a fixed absolute price ratio.

Instead, it uses:

> **A daily market reference point combined with the underlying percentage move and the ETF's target daily leverage.**

---

## Why are reference prices refreshed every day?

Leveraged ETFs generally target a multiple of the **daily return** of their underlying assets.

They do not maintain a permanent relationship such as:

```text
ETF Price = Underlying Price × Leverage
```

As markets move from day to day, the absolute relationship between an underlying asset and its leveraged ETF changes.

This can be affected by:

* Daily leverage resets
* Compounding
* Volatility drag
* Fund expenses
* Tracking differences
* Dividends and corporate actions
* Changes across trading sessions

For this reason, TraFriend refreshes its reference prices each trading day rather than continuing to calculate from old reference prices.

This helps reduce the error that could accumulate when outdated price anchors are used.

---

## Understanding the Estimate

TraFriend's leveraged ETF calculator should be interpreted as:

> **A single-day theoretical estimate based on the current daily reference prices.**

For example:

```text
Reference Prices

NVDA    $170
NVDL     $80
```

If the user enters:

```text
NVDA → $180
```

TraFriend may estimate:

```text
NVDL → ≈ $89.41
```

This means that if NVDA moves from the current daily reference price to $180 within the relevant daily calculation period, and NVDL approximately achieves its targeted `2x` daily exposure, its theoretical price would be around $89.41.

This should not be interpreted as a multi-day price prediction.

Actual results across multiple trading days can differ significantly because leveraged ETFs reset their exposure daily.

---

## Reference Price Timestamp

TraFriend will display the reference prices currently being used together with their most recent update time.

For example:

```text
NVDA
Reference Price
$170.00

NVDL
Reference Price
$80.00

Updated
Sep 5, 2026 · Overnight Session
```

When a new trading day's reference prices are captured, calculations will automatically use the new reference values.

---

# 2. Profit Ratio Analytics

TraFriend plans to provide **Profit Ratio** data and historical trend analysis for U.S. stocks.

Profit Ratio can be understood as:

> The estimated percentage of market holdings that are currently profitable at the current stock price.

Example:

```text
NVDA

Current Profit Ratio
82.6%
```

Rather than only showing the latest number, TraFriend aims to help users understand how Profit Ratio changes over time.

---

## Historical Profit Ratio

TraFriend plans to provide historical Profit Ratio data such as:

```text
Date             Profit Ratio

Sep 1            65.2%
Sep 2            71.8%
Sep 3            68.4%
Sep 4            77.1%
Sep 5            82.6%
```

This can help users explore:

* Current Profit Ratio
* Historical Profit Ratio trends
* Changes across different periods
* Relationships between stock prices and Profit Ratio
* Changes in the profitability of market holdings

---

## Profit Ratio Charts

Planned visualizations include:

* Historical trend charts
* Combined stock-price and Profit-Ratio views
* Multiple selectable time ranges
* OHLC / candlestick-style Profit Ratio charts

The goal is to make it easier to understand not only the current Profit Ratio, but also how quickly and in what direction it has been changing.

---

# What is TraFriend trying to solve?

U.S. stock investors frequently encounter questions such as:

```text
“If NVDA reaches $200, what could NVDL be worth?”

“If TQQQ reaches $100, where might QQQ need to trade?”

“What reference prices should today's calculation use?”

“What percentage of NVDA holdings are currently profitable?”

“How has the Profit Ratio changed over the past several months?”
```

The calculations may not always be complicated, but the necessary information is often scattered across multiple platforms.

TraFriend aims to simplify these workflows into:

> **Search → Enter a target → Get the result**

and:

> **Search → View an indicator → Explore its history**

---

# Future Plans

TraFriend is intended to grow beyond its initial two tools.

Future features may include:

* More leveraged ETF mappings
* Multi-ETF comparison
* Historical Profit Ratio data
* Cost-distribution analytics
* Capital-flow indicators
* Volatility tools
* Position sizing
* Risk/reward calculators
* Short-interest analytics
* Additional market indicators
* Backtesting tools

The long-term goal is to build TraFriend into:

> **A simple, intuitive, and practical toolkit for U.S. stock market analysis.**

---

# Project Status

TraFriend is currently in early development.

The current roadmap is:

```text
Leveraged ETF Calculator
        ↓
Daily Market Reference Prices
        ↓
More Underlying / ETF Mappings
        ↓
Profit Ratio
        ↓
Historical Profit Ratio
        ↓
More Market Tools
```

Features, data sources, calculations, and the overall user experience will continue to evolve.

---

# Disclaimer

TraFriend is intended for informational, analytical, educational, and research purposes only.

Leveraged ETF target prices are **theoretical estimates** calculated using daily reference prices and target daily leverage. They do not represent guaranteed future market prices.

Actual market performance may differ due to factors including:

* Market volatility
* Daily leverage resets
* Compounding
* Volatility drag
* Fund expenses
* Tracking differences
* Liquidity
* Bid-ask spreads
* Corporate actions
* Differences between trading sessions

TraFriend does not provide investment advice and does not guarantee the completeness, timeliness, or accuracy of any data, calculation, or analysis.

Users are solely responsible for their own investment decisions and associated risks.

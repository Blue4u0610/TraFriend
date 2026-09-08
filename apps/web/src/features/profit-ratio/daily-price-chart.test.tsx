// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/locale-provider";
import type { ProfitRatioDailyRow } from "@/lib/api/generated/profit-ratio";

import { CombinedDailyChart, DailyPriceChart, DailyReturnChart } from "./daily-price-chart";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const row: ProfitRatioDailyRow = {
  trading_date: "2026-09-04", open_ratio: null, close_ratio: null, ratio_change: null,
  open_observed_at: null, close_observed_at: null, open_market_timestamp: null, close_market_timestamp: null,
  open_reason_code: "VALIDATED_PRIOR_DISTRIBUTION_MISSING", close_reason_code: "VALIDATED_PRIOR_DISTRIBUTION_MISSING",
  quality: "UNAVAILABLE", status: "DATA_INSUFFICIENT",
  open_price: "150.005", high_price: "160", low_price: "140", close_price: "155.00", price_change_return: "0.02",
  price_status: "COMPLETE", price_quality: "MOCK", price_provider: "mock", price_source_feed: "mock-daily",
  price_adjustment: "raw", price_scope: "CONSOLIDATED_DAILY_ELIGIBLE_TRADES",
  price_observed_at: "2026-09-04T20:25:00Z", price_market_timestamp: "2026-09-04T04:00:00Z",
};

afterEach(cleanup);

describe("independent genuine daily price charts", () => {
  it("overlays selected candles, return trend and Profit Ratio trend in one synchronized SVG", () => {
    const next = {
      ...row,
      trading_date: "2026-09-08",
      open_ratio: "0.40",
      close_ratio: "0.45",
      price_change_return: "-0.01",
    };
    const view = render(<LocaleProvider initialLocale="en"><CombinedDailyChart
      rows={[{ ...row, open_ratio: "0.35", close_ratio: "0.42" }, next]}
      layers={{ price: true, returns: true, ratio: true }}
    /></LocaleProvider>);
    expect(screen.getAllByRole("img", { name: /Synchronized daily chart/ })).toHaveLength(1);
    expect(view.container.querySelectorAll("svg")).toHaveLength(1);
    expect(view.container.querySelectorAll("[data-price-candle]")).toHaveLength(2);
    expect(view.container.querySelectorAll("[data-daily-return]")).toHaveLength(2);
    expect(view.container.querySelectorAll("[data-daily-return-line]")).toHaveLength(1);
    expect(view.container.querySelectorAll("[data-ratio-body]")).toHaveLength(2);
    expect(view.container.querySelectorAll("[data-ratio-line]")).toHaveLength(1);
  });

  it("keeps price candles visible and explains unavailable Profit Ratio in the same chart", () => {
    const view = render(<LocaleProvider initialLocale="en"><CombinedDailyChart
      rows={[row]}
      layers={{ price: true, returns: false, ratio: true }}
    /></LocaleProvider>);
    expect(screen.getByRole("img", { name: /Synchronized daily chart/ })).toBeTruthy();
    expect(view.container.querySelectorAll("[data-price-candle]")).toHaveLength(1);
    expect(
      view.container.querySelectorAll("[data-ratio-body], [data-ratio-line], [data-ratio-point]"),
    ).toHaveLength(0);
    expect(screen.getByText(/Profit Ratio is unavailable/)).toBeTruthy();
  });

  it("draws genuine high / low wicks even when every Profit Ratio is unavailable", async () => {
    const user = userEvent.setup();
    const view = render(<LocaleProvider initialLocale="en"><DailyPriceChart rows={[row]} /></LocaleProvider>);
    const candle = view.container.querySelector("[data-price-candle]")!;
    const wick = view.container.querySelector("[data-price-wick]")!;
    expect(candle).toBeTruthy();
    expect(Number(wick.getAttribute("y1"))).toBeLessThan(Number(candle.getAttribute("y")));
    expect(Number(wick.getAttribute("y2"))).toBeGreaterThan(Number(candle.getAttribute("y")) + Number(candle.getAttribute("height")));
    expect(screen.getByRole("button", { name: /Opening price: \$150.01.*High price: \$160.00.*Low price: \$140.00/ })).toBeTruthy();
    await user.tab(); await user.keyboard("{Enter}");
    expect(view.container.querySelector("[aria-live='polite']")?.textContent).toContain("2026-09-04");
  });

  it("keeps gaps without inferring highs / lows from opening and closing prices", () => {
    const view = render(<LocaleProvider initialLocale="en"><DailyPriceChart rows={[
      row, { ...row, trading_date: "2026-09-08", high_price: null, low_price: null, price_status: "PARTIAL" },
      { ...row, trading_date: "2026-09-09" },
    ]} /></LocaleProvider>);
    const candles = view.container.querySelectorAll("[data-price-candle]");
    expect(candles).toHaveLength(2);
    expect(view.container.querySelectorAll("[data-price-wick]")).toHaveLength(2);
    expect(Number(candles[1].getAttribute("x")) - Number(candles[0].getAttribute("x"))).toBeCloseTo(628 * 2 / 3);
    expect(screen.getByText(/Dates without a complete daily OHLC bar remain blank/)).toBeTruthy();
    expect(view.container.querySelectorAll("path")).toHaveLength(0);
  });

  it("does not publish an incomplete, pending or stale bar as a completed candle", () => {
    const view = render(<LocaleProvider initialLocale="en"><DailyPriceChart rows={[
      { ...row, price_status: "PARTIAL" }, { ...row, trading_date: "2026-09-08", price_status: "NOT_DUE" },
      { ...row, trading_date: "2026-09-09", price_status: "STALE" },
      { ...row, trading_date: "2026-09-10", price_quality: "STALE" },
    ]} /></LocaleProvider>);
    expect(view.container.querySelectorAll("[data-price-candle], [data-price-wick]")).toHaveLength(0);
    expect(screen.getByText(/Complete daily price OHLC is not available/)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("does not let ratio provenance mismatch suppress an independently valid price bar", () => {
    const view = render(<LocaleProvider initialLocale="en"><DailyPriceChart rows={[{ ...row, status: "PROVENANCE_MISMATCH", quality: "MIXED" }]} /></LocaleProvider>);
    expect(view.container.querySelectorAll("[data-price-candle]")).toHaveLength(1);
  });

  it("displays supplied daily returns including zero on their own percent axis without filling gaps", () => {
    const view = render(<LocaleProvider initialLocale="en"><DailyReturnChart rows={[
      row, { ...row, trading_date: "2026-09-08", price_change_return: null },
      { ...row, trading_date: "2026-09-09", price_change_return: "0" },
      { ...row, trading_date: "2026-09-10", price_change_return: "-0.012345" },
    ]} /></LocaleProvider>);
    expect(screen.getByRole("img", { name: /separate percentage axis/ })).toBeTruthy();
    expect(view.container.querySelectorAll("[data-daily-return]")).toHaveLength(3);
    const titles = [...view.container.querySelectorAll("title")].map((item) => item.textContent);
    expect(titles).toEqual(["2026-09-04 · Stock daily change: +2.00%", "2026-09-09 · Stock daily change: 0.00%", "2026-09-10 · Stock daily change: -1.23%"]);
    expect(view.container.querySelectorAll("[data-price-candle], [data-ratio-body]")).toHaveLength(0);
  });

  it("localizes the missing return state instead of inventing zeroes", () => {
    render(<LocaleProvider initialLocale="zh-CN"><DailyReturnChart rows={[{ ...row, price_change_return: null }]} /></LocaleProvider>);
    expect(screen.getByText(/缺失值不会被替换为零/)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

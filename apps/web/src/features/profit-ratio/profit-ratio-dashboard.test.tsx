// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/locale-provider";
import { getProfitRatioDaily, searchProfitRatioUniverse } from "@/lib/api/client";
import type { ProfitRatioConstituent, ProfitRatioDailyHistory, ProfitRatioDailyRow } from "@/lib/api/generated/profit-ratio";

import { DailyRatioChart } from "./daily-ratio-chart";
import { ProfitRatioDashboard } from "./profit-ratio-dashboard";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("@/lib/api/client", () => ({ getProfitRatioDaily: vi.fn(), searchProfitRatioUniverse: vi.fn() }));

const member = (symbol = "NVDA"): ProfitRatioConstituent => ({ instrument_id: `ins_${symbol.toLowerCase()}_xnas`, symbol, name: symbol === "NVDA" ? "NVIDIA Corporation" : "Apple Inc.", as_of: "2026-09-08", source: "mock-qqq-holdings" });
const row: ProfitRatioDailyRow = {
  trading_date: "2026-09-08", open_ratio: "0.6000", close_ratio: "0.6600",
  open_price: "150.005", close_price: "153.00", price_change_return: "0.0200", ratio_change: "0.06",
  open_observed_at: "2026-09-08T13:50:00Z", close_observed_at: "2026-09-08T20:20:00Z",
  open_market_timestamp: "2026-09-08T13:30:00Z", close_market_timestamp: "2026-09-08T20:00:00Z",
  open_reason_code: null, close_reason_code: null, quality: "MOCK", status: "COMPLETE",
};
const history = (overrides: Partial<ProfitRatioDailyHistory> = {}): ProfitRatioDailyHistory => ({
  symbol: "NVDA", instrument_id: "ins_nvda_xnas", methodology: { id: "CHIP_TURNOVER", version: "1", display_name: "Mock turnover estimate" },
  provider: "mock", timezone: "America/New_York", as_of: "2026-09-08T20:25:00Z", status: "COMPLETE", rows: [row], gaps: [], ...overrides,
});
const envelope = <T,>(data: T) => ({ data, meta: { request_id: "req_test" } });
const search = vi.mocked(searchProfitRatioUniverse);
const daily = vi.mocked(getProfitRatioDaily);

function renderDashboard(locale: "en" | "zh-CN" = "en") {
  return render(<LocaleProvider initialLocale={locale}><ProfitRatioDashboard initialRange={{ start: "2026-06-08", end: "2026-09-08" }} /></LocaleProvider>);
}

async function selectStock(symbol = "NVDA") {
  fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: symbol } });
  fireEvent.click(await screen.findByRole("button", { name: new RegExp(`${symbol}.*${symbol === "NVDA" ? "NVIDIA" : "Apple"}`) }));
}

beforeEach(() => {
  vi.clearAllMocks();
  search.mockImplementation(async (query) => envelope([member(query.toUpperCase())]));
  daily.mockResolvedValue(envelope(history()));
});
afterEach(cleanup);

describe("QQQ daily Profit Ratio dashboard", () => {
  it("only searches metadata until selection, then reads the chosen symbol and dates", async () => {
    renderDashboard();
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(search).not.toHaveBeenCalled();
    expect(daily).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: "NVDA" } });
    const choice = await screen.findByRole("button", { name: /NVDA.*NVIDIA/ });
    expect(daily).not.toHaveBeenCalled();
    fireEvent.click(choice);
    const table = await screen.findByRole("table");
    expect(daily).toHaveBeenCalledWith("NVDA", "2026-06-08", "2026-09-08", expect.any(AbortSignal));
    expect(within(table).getByText("60.00%")).toBeTruthy();
    expect(within(table).getByText("66.00%")).toBeTruthy();
    expect(within(table).getByText("+2.00%")).toBeTruthy();
    expect(within(table).getByText("$150.01")).toBeTruthy();
    expect(screen.getByText(/DEMO \/ MOCK/)).toBeTruthy();
  });

  it("shows a scoped empty search without inventing a symbol", async () => {
    search.mockResolvedValue(envelope([]));
    renderDashboard();
    fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: "NOTQQQ" } });
    expect(await screen.findByText("No matching stock in the stored QQQ holdings list.")).toBeTruthy();
    expect(daily).not.toHaveBeenCalled();
  });

  it("shows a safe search failure without displaying vendor errors", async () => {
    search.mockRejectedValue(new Error("private provider error"));
    renderDashboard();
    fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: "NVDA" } });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("private provider error")).toBeNull();
  });

  it("ignores an older search response after the query changes", async () => {
    let finishOld: (value: ReturnType<typeof envelope<ProfitRatioConstituent[]>>) => void = () => {};
    search.mockImplementation((query) => query === "N" ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve(envelope([member("AAPL")])));
    renderDashboard();
    fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: "N" } });
    await waitFor(() => expect(search).toHaveBeenCalledWith("N", expect.any(AbortSignal)));
    fireEvent.change(screen.getByLabelText("Search QQQ constituent stocks"), { target: { value: "AAPL" } });
    expect(await screen.findByRole("button", { name: /AAPL.*Apple/ })).toBeTruthy();
    await act(async () => finishOld(envelope([member()])));
    expect(screen.queryByRole("button", { name: /NVDA.*NVIDIA/ })).toBeNull();
  });

  it("ignores a slow previous-symbol history response", async () => {
    let finishOld: (value: ReturnType<typeof envelope<ProfitRatioDailyHistory>>) => void = () => {};
    daily.mockImplementation((symbol) => symbol === "NVDA" ? new Promise((resolve) => { finishOld = resolve; }) : Promise.resolve(envelope(history({ symbol: "AAPL", instrument_id: "ins_aapl_xnas", rows: [{ ...row, close_ratio: "0.1234" }] }))));
    renderDashboard();
    await selectStock();
    expect(screen.getByRole("status", { name: /Loading stored/ })).toBeTruthy();
    await selectStock("AAPL");
    expect(within(await screen.findByRole("table")).getByText("12.34%")).toBeTruthy();
    await act(async () => finishOld(envelope(history())));
    expect(within(screen.getByRole("table")).queryByText("66.00%")).toBeNull();
    expect(screen.getByRole("heading", { name: "AAPL" })).toBeTruthy();
  });

  it("keeps real price data visible when model inputs are missing", async () => {
    daily.mockResolvedValue(envelope(history({ provider: "alpaca:sip", status: "DATA_INSUFFICIENT", rows: [{ ...row, open_ratio: null, close_ratio: null, ratio_change: null, quality: "DELAYED", status: "DATA_INSUFFICIENT" }], gaps: [{ trading_date: "2026-09-08", phase: "OPEN", reason_code: "VALIDATED_PRIOR_DISTRIBUTION_MISSING" }] })));
    renderDashboard(); await selectStock();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("—")).toHaveLength(2);
    expect(within(table).getByText("+2.00%")).toBeTruthy();
    expect(screen.getByText(/Price data is available, but the model/)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText(/DEMO \/ MOCK/)).toBeNull();
    expect(screen.getByText(/VALIDATED_PRIOR_DISTRIBUTION_MISSING/)).toBeTruthy();
  });

  it("suppresses incompatible open / close chart marks while retaining table context", async () => {
    daily.mockResolvedValue(envelope(history({ provider: "mixed", status: "PARTIAL", rows: [{ ...row, status: "PROVENANCE_MISMATCH", quality: "MIXED" }] })));
    const view = renderDashboard(); await selectStock();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("60.00%")).toBeTruthy();
    expect(within(table).getByText("66.00%")).toBeTruthy();
    expect(within(table).getByText(/Incompatible observations/)).toBeTruthy();
    expect(screen.getByText(/No chart mark is drawn/)).toBeTruthy();
    expect(view.container.querySelectorAll("[data-ratio-body], [data-ratio-point]")).toHaveLength(0);
  });

  it("preserves a zero opening observation and pending close without creating a close", async () => {
    daily.mockResolvedValue(envelope(history({ status: "PARTIAL", rows: [{ ...row, open_ratio: "0", close_ratio: null, close_price: null, price_change_return: null, close_observed_at: null, status: "PARTIAL" }], gaps: [{ trading_date: "2026-09-08", phase: "CLOSE", reason_code: "NOT_DUE" }] })));
    const view = renderDashboard(); await selectStock();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("0.00%")).toBeTruthy();
    expect(within(table).getAllByText("—")).toHaveLength(3);
    expect(view.container.querySelectorAll("[data-ratio-body]")).toHaveLength(0);
    expect(view.container.querySelectorAll("[data-ratio-point]")).toHaveLength(1);
    expect(screen.getByText(/Pending/)).toBeTruthy();
  });

  it("has an explicit empty history state", async () => {
    daily.mockResolvedValue(envelope(history({ status: "EMPTY", rows: [] })));
    renderDashboard(); await selectStock();
    expect(await screen.findByText(/No stored observations exist/)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("retries a read failure without losing the selected stock", async () => {
    daily.mockRejectedValueOnce(new Error("secret vendor reason"));
    renderDashboard(); await selectStock();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("secret vendor reason")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table")).toBeTruthy();
    expect(daily).toHaveBeenCalledTimes(2);
  });

  it("only fetches an edited date range after Apply and prevents reversed dates", async () => {
    renderDashboard(); await selectStock(); await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-08-01" } });
    expect(daily).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Apply dates" }));
    await waitFor(() => expect(daily).toHaveBeenCalledWith("NVDA", "2026-08-01", "2026-09-08", expect.any(AbortSignal)));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-08" } });
    fireEvent.change(screen.getByLabelText("Through"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply dates" }));
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(daily).toHaveBeenCalledTimes(2);
  });

  it("localizes the new search, chart and table in Chinese", async () => {
    renderDashboard("zh-CN");
    fireEvent.change(screen.getByLabelText("搜索 QQQ 成分股票"), { target: { value: "NVDA" } });
    fireEvent.click(await screen.findByRole("button", { name: /NVDA.*NVIDIA/ }));
    expect(await screen.findByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "开盘获利比" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "股票当日涨跌幅" })).toBeTruthy();
    expect(screen.getByText(/没有上下影线/)).toBeTruthy();
  });
});

describe("open / close bodies", () => {
  it("defends against mixed-quality rows even before a backend mismatch status is applied", () => {
    const view = render(<LocaleProvider initialLocale="zh-CN"><DailyRatioChart rows={[{ ...row, status: "COMPLETE", quality: "MIXED" }]} /></LocaleProvider>);
    expect(view.container.querySelectorAll("[data-ratio-body], [data-ratio-point]")).toHaveLength(0);
    expect(screen.getByText(/来源不兼容，因此不绘制图形/)).toBeTruthy();
  });

  it("draws only bodies and single points, never wicks or interpolating paths", async () => {
    const user = userEvent.setup();
    const view = render(<LocaleProvider initialLocale="en"><DailyRatioChart rows={[
      row, { ...row, trading_date: "2026-09-09", open_ratio: "0.66", close_ratio: "0.60" },
      { ...row, trading_date: "2026-09-10", open_ratio: null, close_ratio: null },
      { ...row, trading_date: "2026-09-11", open_ratio: "0", close_ratio: null },
    ]} /></LocaleProvider>);
    expect(view.container.querySelectorAll("[data-ratio-body]")).toHaveLength(2);
    expect(view.container.querySelectorAll("[data-ratio-point]")).toHaveLength(1);
    expect(view.container.querySelectorAll("path")).toHaveLength(0);
    for (const line of view.container.querySelectorAll("line")) expect(line.getAttribute("y1")).toBe(line.getAttribute("y2"));
    await user.tab();
    expect(document.activeElement?.getAttribute("aria-label")).toContain("2026-09-08");
    await user.keyboard("{Enter}");
    expect(view.container.querySelector("[aria-live='polite']")?.textContent).toContain("2026-09-08");
  });
});

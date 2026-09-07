// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/locale-provider";
import type { MultiCalculation, UnderlyingWorkspace } from "@/lib/api/types";

import { LeverageCalculator } from "./leverage-calculator";

const apiMocks = vi.hoisted(() => ({
  calculateAllProducts: vi.fn(),
  calculateTarget: vi.fn(),
  getPopularUniverse: vi.fn(),
  resolveUnderlyingWorkspace: vi.fn(),
  searchLeveragedProducts: vi.fn(),
  searchUnderlyings: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return { ...actual, ...apiMocks };
});

const workspace = {
  underlying: {
    id: "ins_sndk_xnas",
    symbol: "SNDK",
    name: "Sandisk Corporation",
    instrument_type: "stock",
    exchange_mic: "XNAS",
    currency: "USD",
    status: "active",
    capabilities: { leveraged_relationships: true, profit_ratio: false },
  },
  rows: [
    {
      relationship: {
        id: "rel_sndk_snxx_2x",
        underlying: { symbol: "SNDK" },
        leveraged_product: { symbol: "SNXX" },
        leverage_factor: "2.0000",
        direction: "LONG",
      },
      status: "AVAILABLE",
      anchor_source: "CACHE",
      anchor: {
        id: "anchor_sndk_snxx",
        trading_date: "2026-09-04",
        underlying: { close: "1740.00000000" },
        leveraged_product: { close: "17.36000000" },
      },
    },
  ],
} as UnderlyingWorkspace;

const calculation = {
  underlying: workspace.underlying,
  target_price: "1653.00",
  rows: [
    {
      relationship: workspace.rows[0].relationship,
      status: "AVAILABLE",
      anchor: workspace.rows[0].anchor,
      theoretical_target_price: "15.624",
      underlying_return: "-0.05",
      leveraged_return: "-0.10",
      message: "available",
    },
  ],
  formula_version: "leveraged-daily-close-linear/v2",
} as MultiCalculation;

describe("LeverageCalculator price controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    apiMocks.resolveUnderlyingWorkspace.mockResolvedValue({
      data: workspace,
      meta: { request_id: "req_workspace" },
    });
    apiMocks.getPopularUniverse.mockResolvedValue({
      data: {
        ranking_period: "2026-09",
        period_status: "SEPTEMBER_TO_DATE",
        ranking_type: "DOLLAR_TRADING_VOLUME",
        population_status: "NOT_POPULATED",
        rows: [],
      },
      meta: { request_id: "req_popular" },
    });
    apiMocks.calculateAllProducts.mockResolvedValue({
      data: calculation,
      meta: { request_id: "req_calculation" },
    });
  });

  afterEach(cleanup);

  it("formats anchor inputs to two decimals and recalculates from a shortcut", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider initialLocale="en">
        <LeverageCalculator />
      </LocaleProvider>,
    );

    const target = await screen.findByRole("textbox", { name: "SNDK target price" });
    expect((target as HTMLInputElement).value).toBe("1740.00");

    await user.click(
      screen.getByRole("button", { name: "Set target to regular close -5%" }),
    );
    expect((target as HTMLInputElement).value).toBe("1653.00");
    await waitFor(() =>
      expect(apiMocks.calculateAllProducts).toHaveBeenLastCalledWith("SNDK", "1653.00"),
    );

    await user.type(
      screen.getByRole("textbox", { name: "Custom plus or minus percentage" }),
      "2.5",
    );
    expect((target as HTMLInputElement).value).toBe("1783.50");
    await waitFor(() =>
      expect(apiMocks.calculateAllProducts).toHaveBeenLastCalledWith("SNDK", "1783.50"),
    );
  });

  it("shows the ETF ticker instead of the relationship id in reverse mode", async () => {
    const user = userEvent.setup();
    render(
      <LocaleProvider initialLocale="en">
        <LeverageCalculator />
      </LocaleProvider>,
    );

    await screen.findByRole("textbox", { name: "SNDK target price" });
    await user.click(screen.getByRole("tab", { name: "ETF → underlying" }));

    const productSelect = screen.getByRole("combobox", { name: "Leveraged ETF" });
    expect(productSelect.textContent).toContain("SNXX");
    expect(productSelect.textContent).not.toContain("rel_sndk_snxx_2x");
    expect(
      (screen.getByRole("textbox", { name: "SNXX target price" }) as HTMLInputElement)
        .value,
    ).toBe("17.36");
  });
});

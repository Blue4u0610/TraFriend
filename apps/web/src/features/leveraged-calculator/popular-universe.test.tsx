// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/locale-provider";
import type { PopularDataset } from "@/lib/api/types";

import { PopularUniverse } from "./popular-universe";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const dataset: PopularDataset = {
  ranking_period: "2026-09",
  period_status: "SEPTEMBER_TO_DATE",
  ranking_type: "DOLLAR_TRADING_VOLUME",
  population_status: "COMPLETE",
  rows: [
    {
      rank: 1,
      symbol: "NVDA",
      name: "NVIDIA Corporation",
      trading_metric: "123456789012.3400",
      calculated_at: "2026-09-06T12:00:00Z",
      source: "alpaca:sip:daily_vwap_x_volume",
      completeness_status: "COMPLETE",
      sessions_observed: 4,
      sessions_expected: 4,
      supported_leveraged_products: 1,
    },
    {
      rank: 2,
      symbol: "AAPL",
      name: "Apple Inc.",
      trading_metric: "100000000000.0000",
      calculated_at: "2026-09-06T12:00:00Z",
      source: "alpaca:sip:daily_vwap_x_volume",
      completeness_status: "COMPLETE",
      sessions_observed: 4,
      sessions_expected: 4,
      supported_leveraged_products: 0,
    },
  ],
};

function renderPopular(
  props: Partial<React.ComponentProps<typeof PopularUniverse>> = {},
) {
  const onSelect = vi.fn();
  const onAdd = vi.fn();
  const onRetry = vi.fn();
  const view = render(
    <LocaleProvider initialLocale="en">
      <PopularUniverse
        dataset={dataset}
        error={null}
        watchlist={[]}
        onSelect={onSelect}
        onAdd={onAdd}
        onRetry={onRetry}
        {...props}
      />
    </LocaleProvider>,
  );
  return { onSelect, onAdd, onRetry, rerender: view.rerender };
}

describe("PopularUniverse", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("renders API ranking rows and selects a supported workspace", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderPopular();

    expect(screen.getByText("NVIDIA Corporation")).toBeTruthy();
    expect(screen.getByText("$123,456,789,012")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /NVDA/ }));

    expect(onSelect).toHaveBeenCalledWith(dataset.rows[0]);
    expect(
      screen.getByText("The supported calculator workspace has been selected above."),
    ).toBeTruthy();
  });

  it("adds a supported underlying to the watchlist from Popular", async () => {
    const user = userEvent.setup();
    const { onAdd } = renderPopular();

    await user.click(screen.getAllByRole("button", { name: "Add to Watchlist" })[0]);

    expect(onAdd).toHaveBeenCalledWith("NVDA");
  });

  it("keeps no-product, filtered-empty, and load-error states safe", async () => {
    const user = userEvent.setup();
    const { onRetry, rerender } = renderPopular();

    await user.click(screen.getByRole("button", { name: /AAPL/ }));
    expect(screen.getByText(/0 supported leveraged products/)).toBeTruthy();
    await user.type(
      screen.getByPlaceholderText("Filter the Top 100 by symbol or company…"),
      "ZZZZ",
    );
    expect(screen.getByText("No Top-100 rows match this filter.")).toBeTruthy();

    rerender(
      <LocaleProvider initialLocale="en">
        <PopularUniverse
          dataset={null}
          error="unavailable"
          watchlist={[]}
          onSelect={vi.fn()}
          onAdd={vi.fn()}
          onRetry={onRetry}
        />
      </LocaleProvider>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Retry data" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

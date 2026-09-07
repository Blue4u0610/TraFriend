// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InstrumentSearch } from "./universe-search";

afterEach(cleanup);

describe("InstrumentSearch", () => {
  it("searches metadata and opens the selected instrument", async () => {
    const user = userEvent.setup();
    const search = vi.fn().mockResolvedValue({
      data: [
        {
          id: "ins_mu_xnas",
          symbol: "MU",
          name: "Micron Technology, Inc.",
          instrument_type: "stock",
          exchange_mic: "XNAS",
          currency: "USD",
          status: "active",
          capabilities: {
            leveraged_relationships: true,
            profit_ratio: false,
          },
        },
      ],
      meta: { request_id: "req_test" },
    });
    const onSelect = vi.fn();

    render(
      <InstrumentSearch
        id="underlying-search"
        title="Search underlyings"
        label="Search supported underlyings"
        placeholder="Underlying ticker or name"
        loadingText="Searching"
        noMatchesText="No matches"
        search={search}
        errorMessage={() => "Failed"}
        onSelect={onSelect}
      />,
    );

    await user.type(screen.getByLabelText("Search supported underlyings"), "mu");
    expect(await screen.findByRole("button", { name: /MU.*Micron/ })).toBeTruthy();
    expect(search).toHaveBeenCalledWith("mu");

    await user.click(screen.getByRole("button", { name: /MU.*Micron/ }));
    expect(onSelect).toHaveBeenCalledWith("MU");
  });
});

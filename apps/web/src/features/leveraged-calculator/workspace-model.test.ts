import { describe, expect, it } from "vitest";

import type { MultiCalculation, UnderlyingWorkspace } from "@/lib/api/types";

import { buildProductViewRows, normalizedSearchQuery } from "./workspace-model";

const workspace = {
  underlying: { symbol: "QQQ" },
  rows: [
    {
      relationship: {
        id: "qld",
        leverage_factor: "2",
        direction: "LONG",
        leveraged_product: { symbol: "QLD" },
      },
      status: "AVAILABLE",
      anchor: { leveraged_product: { close: "90.68" } },
    },
    {
      relationship: {
        id: "tqqq",
        leverage_factor: "3",
        direction: "LONG",
        leveraged_product: { symbol: "TQQQ" },
      },
      status: "AVAILABLE",
      anchor: { leveraged_product: { close: "72.37" } },
    },
    {
      relationship: {
        id: "sqqq",
        leverage_factor: "-3",
        direction: "INVERSE",
        leveraged_product: { symbol: "SQQQ" },
      },
      status: "UNAVAILABLE",
      anchor: null,
    },
  ],
} as UnderlyingWorkspace;

const calculation = {
  rows: [
    {
      relationship: { id: "qld" },
      status: "AVAILABLE",
      theoretical_target_price: "94.20",
    },
    {
      relationship: { id: "tqqq" },
      status: "AVAILABLE",
      theoretical_target_price: "76.71",
    },
    {
      relationship: { id: "sqqq" },
      status: "UNAVAILABLE",
      theoretical_target_price: null,
    },
  ],
} as MultiCalculation;

describe("calculator workspace presentation model", () => {
  it("maps one underlying calculation to every ETF row", () => {
    const rows = buildProductViewRows(workspace, calculation);

    expect(rows.map((row) => row.symbol)).toEqual(["QLD", "TQQQ", "SQQQ"]);
    expect(rows[0].theoreticalTarget).toBe("94.20");
    expect(rows[1].theoreticalTarget).toBe("76.71");
  });

  it("marks inverse and unavailable rows without inventing a result", () => {
    const row = buildProductViewRows(workspace, calculation)[2];

    expect(row.inverse).toBe(true);
    expect(row.status).toBe("UNAVAILABLE");
    expect(row.theoreticalTarget).toBeNull();
  });

  it("normalizes metadata-search input without invoking market data", () => {
    expect(normalizedSearchQuery("  QQQ  ")).toBe("QQQ");
    expect(normalizedSearchQuery("x".repeat(80))).toHaveLength(64);
  });
});

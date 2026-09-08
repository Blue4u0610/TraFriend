import { describe, expect, it } from "vitest";

import { defaultProfitRatioRange, formatRatioPrice, formatRatioValue } from "./display";

describe("Profit Ratio display", () => {
  it("formats fractional decimal strings without binary-price rounding", () => {
    expect(formatRatioValue("0.12345")).toBe("12.35%");
    expect(formatRatioValue("0")).toBe("0.00%");
    expect(formatRatioValue("1")).toBe("100.00%");
    expect(formatRatioValue("0E-12")).toBe("0.00%");
    expect(formatRatioValue("-0.00001", true)).toBe("0.00%");
    expect(formatRatioValue("0.01365", true)).toBe("+1.37%");
    expect(formatRatioValue("-0.02345", true)).toBe("-2.35%");
    expect(formatRatioPrice("1.005")).toBe("$1.01");
    expect(formatRatioPrice("123456789012345678.005")).toBe("$123456789012345678.01");
  });

  it("never converts missing or invalid data into zero", () => {
    for (const value of [null, undefined, "", "NaN", "Infinity", "bad", "1e999"]) {
      expect(formatRatioValue(value)).toBe("—");
      expect(formatRatioPrice(value)).toBe("—");
    }
  });

  it("uses New York today and clamps three-month ranges at month end", () => {
    expect(defaultProfitRatioRange(new Date("2026-09-09T01:00:00Z"))).toEqual({ start: "2026-06-08", end: "2026-09-08" });
    expect(defaultProfitRatioRange(new Date("2026-05-31T20:00:00Z"))).toEqual({ start: "2026-02-28", end: "2026-05-31" });
    expect(defaultProfitRatioRange(new Date("2026-01-15T20:00:00Z"))).toEqual({ start: "2025-10-15", end: "2026-01-15" });
  });
});

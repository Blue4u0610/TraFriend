import { describe, expect, it } from "vitest";

import { adjustPriceByPercent, formatPriceInput } from "./price-input";

describe("calculator price input formatting", () => {
  it("shows persisted decimal prices with exactly two fractional digits", () => {
    expect(formatPriceInput("1016.59000000")).toBe("1016.59");
    expect(formatPriceInput("142.8")).toBe("142.80");
    expect(formatPriceInput("1.235")).toBe("1.24");
  });

  it("applies preset and custom percentages from the anchor without floats", () => {
    expect(adjustPriceByPercent("718.96000000", "-5")).toBe("683.01");
    expect(adjustPriceByPercent("718.96000000", "+3")).toBe("740.53");
    expect(adjustPriceByPercent("718.96000000", "1.25")).toBe("727.95");
  });

  it("rejects invalid or non-positive adjusted prices", () => {
    expect(adjustPriceByPercent("718.96", "custom")).toBeNull();
    expect(adjustPriceByPercent("718.96", "-100")).toBeNull();
    expect(adjustPriceByPercent("0", "5")).toBeNull();
  });
});

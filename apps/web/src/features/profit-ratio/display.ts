/** Decimal-string formatting only; market returns and ratios are calculated by the API. */
export function formatRatioValue(value: string | null | undefined, signed = false) {
  const display = formatDecimal(value, 100);
  if (display === null) return "—";
  return `${signed && !display.startsWith("-") && display !== "0.00" ? "+" : ""}${display}%`;
}

export function formatRatioPrice(value: string | null | undefined) {
  const display = formatDecimal(value, 1);
  return display === null ? "—" : `$${display}`;
}

function formatDecimal(value: string | null | undefined, multiplier: number) {
  if (value === null || value === undefined) return null;
  const match = value.match(/^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/);
  if (!match || value.length > 128) return null;
  const [, sign, whole, fraction = "", exponent = "0"] = match;
  const decimalExponent = Number(exponent);
  if (!Number.isInteger(decimalExponent) || Math.abs(decimalExponent) > 30) return null;
  const scale = fraction.length - decimalExponent;
  const units = BigInt(`${whole}${fraction}`) * BigInt(multiplier);
  const divisor = BigInt(10) ** BigInt(Math.max(scale - 2, 0));
  const rounded = scale > 2
    ? (units + divisor / BigInt(2)) / divisor
    : units * BigInt(10) ** BigInt(2 - scale);
  const prefix = sign === "-" && rounded !== BigInt(0) ? "-" : "";
  return `${prefix}${rounded / BigInt(100)}.${(rounded % BigInt(100)).toString().padStart(2, "0")}`;
}

export type ProfitRatioDateRange = { start: string; end: string };

export function defaultProfitRatioRange(now: Date = new Date()): ProfitRatioDateRange {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (type: string) => Number(parts.find((item) => item.type === type)?.value);
  const year = part("year");
  const month = part("month");
  const day = part("day");
  const end = new Date(Date.UTC(year, month - 1, day));
  const previousMonthLastDay = new Date(Date.UTC(year, month - 3, 0)).getUTCDate();
  const start = new Date(Date.UTC(year, month - 4, Math.min(day, previousMonthLastDay)));
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

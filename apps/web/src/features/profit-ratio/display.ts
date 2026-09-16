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
  const prefix = `${year}-${month.toString().padStart(2, "0")}`;
  return { start: `${prefix}-01`, end: `${prefix}-${day.toString().padStart(2, "0")}` };
}

export function profitRatioMonthRange(month: string, maximumEnd: string): ProfitRatioDateRange | null {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return null;
  const year = Number(match[1]);
  const monthNumber = Number(match[2]);
  if (year < 1970 || monthNumber < 1 || monthNumber > 12) return null;
  const start = `${month}-01`;
  const lastDay = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  const naturalEnd = `${month}-${lastDay.toString().padStart(2, "0")}`;
  if (start > maximumEnd) return null;
  return { start, end: naturalEnd > maximumEnd ? maximumEnd : naturalEnd };
}

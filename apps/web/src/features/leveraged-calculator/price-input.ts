type ParsedDecimal = {
  units: bigint;
  scale: number;
};

function parseDecimal(value: string): ParsedDecimal | null {
  const match = value.trim().match(/^([+-]?)(\d+)(?:\.(\d*))?$/);
  if (!match) return null;

  const [, sign, whole, fraction = ""] = match;
  const absoluteUnits = BigInt(`${whole}${fraction}`);
  return {
    units: sign === "-" ? -absoluteUnits : absoluteUnits,
    scale: fraction.length,
  };
}

function formatScaled(units: bigint, sourceScale: number, places: number) {
  const negative = units < BigInt(0);
  const absoluteUnits = negative ? -units : units;
  let rounded: bigint;

  if (sourceScale <= places) {
    rounded = absoluteUnits * BigInt(10) ** BigInt(places - sourceScale);
  } else {
    const divisor = BigInt(10) ** BigInt(sourceScale - places);
    const quotient = absoluteUnits / divisor;
    const remainder = absoluteUnits % divisor;
    rounded = quotient + (remainder * BigInt(2) >= divisor ? BigInt(1) : BigInt(0));
  }

  const placeScale = BigInt(10) ** BigInt(places);
  const sign = negative && rounded !== BigInt(0) ? "-" : "";
  return `${sign}${rounded / placeScale}.${(rounded % placeScale)
    .toString()
    .padStart(places, "0")}`;
}

export function formatPriceInput(value: string | null | undefined) {
  if (!value) return "";
  const parsed = parseDecimal(value);
  return parsed ? formatScaled(parsed.units, parsed.scale, 2) : value;
}

export function adjustPriceByPercent(price: string, percent: string) {
  const parsedPrice = parseDecimal(price);
  const parsedPercent = parseDecimal(percent);
  if (!parsedPrice || !parsedPercent || parsedPrice.units <= BigInt(0)) return null;

  const percentScale = BigInt(10) ** BigInt(parsedPercent.scale);
  const factorUnits = BigInt(100) * percentScale + parsedPercent.units;
  if (factorUnits <= BigInt(0)) return null;

  return formatScaled(
    parsedPrice.units * factorUnits,
    parsedPrice.scale + parsedPercent.scale + 2,
    2,
  );
}

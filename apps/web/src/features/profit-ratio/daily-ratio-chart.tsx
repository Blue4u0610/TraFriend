"use client";

import { useId, useState } from "react";

import { useLocale } from "@/i18n/locale-provider";
import type { ProfitRatioDailyHistory } from "@/lib/api/generated/profit-ratio";

import { formatRatioValue } from "./display";

type DailyRow = ProfitRatioDailyHistory["rows"][number];
type RatioRow = DailyRow & { profit_ratio: string };

function hasRatio(row: DailyRow): row is RatioRow {
  return row.profit_ratio !== null && row.profit_ratio !== undefined;
}

/** One genuine daily value per date; missing values remain gaps. */
export function DailyRatioChart({ rows }: { rows: DailyRow[] }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const chartDescriptionId = useId();
  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const available = rows.filter(hasRatio);
  const selected = available.find((row) => row.trading_date === focusedDate) ?? available.at(-1);
  const left = 54;
  const plotWidth = 650;
  const top = 18;
  const plotHeight = 220;
  const slot = plotWidth / Math.max(rows.length, 1);
  const y = (value: string) => top + (1 - Number(value)) * plotHeight;
  const x = (index: number) => left + slot * (index + 0.5);
  const describe = (row: RatioRow) => `${row.trading_date} · ${t.dailyProfitRatio}: ${formatRatioValue(row.profit_ratio)} · ${row.profit_ratio_time_basis === "CLOSE" ? t.closeTimeBasis : t.unverifiedDailyTimeBasis}`;

  if (available.length === 0) return <p role="status">{t.ratiosNotCaptured}</p>;
  return <div>
    <p id={chartDescriptionId} className="mb-4 text-sm leading-6 text-muted-foreground">{t.chartExplanation}</p>
    <div className="overflow-x-auto rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
      <svg viewBox="0 0 730 266" className="h-auto min-w-[520px] w-full" role="img" aria-label={t.chartAria} aria-describedby={chartDescriptionId}>
        {[0, 25, 50, 75, 100].map((percent) => {
          const gridY = top + (1 - percent / 100) * plotHeight;
          return <g key={percent} aria-hidden="true">
            <line x1={left} x2={left + plotWidth} y1={gridY} y2={gridY} stroke="currentColor" strokeOpacity="0.12" strokeDasharray="4 6" />
            <text x={left - 8} y={gridY + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">{percent}%</text>
          </g>;
        })}
        {rows.slice(1).map((row, offset) => {
          const previous = rows[offset];
          if (!hasRatio(previous) || !hasRatio(row)) return null;
          return <line key={`line-${row.trading_date}`} data-ratio-line="true" x1={x(offset)} y1={y(previous.profit_ratio)} x2={x(offset + 1)} y2={y(row.profit_ratio)} stroke="#fbbf24" strokeWidth={2} />;
        })}
        {rows.map((row, index) => !hasRatio(row) ? null : <circle key={row.trading_date} data-ratio-point="true" role="button" tabIndex={0} aria-label={describe(row)} cx={x(index)} cy={y(row.profit_ratio)} r={3.5} fill="#fbbf24" className="cursor-pointer outline-none focus:stroke-foreground" onFocus={() => setFocusedDate(row.trading_date)} onMouseEnter={() => setFocusedDate(row.trading_date)} onClick={() => setFocusedDate(row.trading_date)} onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setFocusedDate(row.trading_date); }
        }} />)}
        <text x={left} y={260} className="fill-muted-foreground text-[10px]">{rows[0]?.trading_date}</text>
        <text x={left + plotWidth} y={260} textAnchor="end" className="fill-muted-foreground text-[10px]">{rows.at(-1)?.trading_date}</text>
      </svg>
    </div>
    <div className="mt-3 text-xs text-muted-foreground"><span className="mr-1 text-amber-300">●━</span>{t.ratioLegend}</div>
    {selected && <p className="mt-4 min-h-10 font-mono text-sm leading-6" aria-live="polite">{describe(selected)}</p>}
  </div>;
}

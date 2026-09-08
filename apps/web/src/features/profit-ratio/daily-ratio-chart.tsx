"use client";

import { useId, useState } from "react";

import { useLocale } from "@/i18n/locale-provider";
import type { ProfitRatioDailyHistory } from "@/lib/api/generated/profit-ratio";

import { formatRatioValue } from "./display";

type DailyRow = ProfitRatioDailyHistory["rows"][number];

export function hasRatioProvenanceMismatch(row: DailyRow) {
  return row.status === "PROVENANCE_MISMATCH" || row.quality === "MIXED"
    || row.open_reason_code === "PROVENANCE_MISMATCH"
    || row.close_reason_code === "PROVENANCE_MISMATCH";
}

export function DailyRatioChart({ rows }: { rows: DailyRow[] }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const chartDescriptionId = useId();
  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const selected = rows.find((row) => row.trading_date === focusedDate) ?? rows.at(-1);
  const left = 54;
  const plotWidth = 650;
  const top = 18;
  const plotHeight = 220;
  const slot = plotWidth / Math.max(rows.length, 1);
  const width = Math.min(18, slot * 0.65);
  // Number conversion is restricted to SVG geometry, never displayed financial values.
  const y = (value: string) => top + (1 - Number(value)) * plotHeight;
  const mismatchedDates = rows.filter(hasRatioProvenanceMismatch).map((row) => row.trading_date);
  const describe = (row: DailyRow) => hasRatioProvenanceMismatch(row)
    ? `${row.trading_date} · ${t.provenanceMismatch}`
    : `${row.trading_date} · ${t.openRatio}: ${formatRatioValue(row.open_ratio)} · ${t.closeRatio}: ${formatRatioValue(row.close_ratio)} · ${t.dailyReturn}: ${formatRatioValue(row.price_change_return, true)}`;

  return (
    <div>
      <p id={chartDescriptionId} className="mb-4 text-sm leading-6 text-muted-foreground">{t.chartExplanation}</p>
      {mismatchedDates.length > 0 && <p role="status" className="mb-4 rounded-lg border border-amber-400/20 p-3 text-sm leading-6 text-amber-200">{t.provenanceMismatchNotice} {mismatchedDates.join(", ")}</p>}
      <div className="overflow-x-auto rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
        <svg viewBox="0 0 730 266" className="h-auto min-w-[520px] w-full" role="img" aria-label={t.chartAria} aria-describedby={chartDescriptionId}>
          {[0, 25, 50, 75, 100].map((percent) => {
            const gridY = top + (1 - percent / 100) * plotHeight;
            return <g key={percent} aria-hidden="true">
              <line x1={left} x2={left + plotWidth} y1={gridY} y2={gridY} stroke="currentColor" strokeOpacity="0.12" strokeDasharray="4 6" />
              <text x={left - 8} y={gridY + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">{percent}%</text>
            </g>;
          })}
          {rows.map((row, index) => {
            // Incompatible observations must never imply a comparable daily movement.
            if (hasRatioProvenanceMismatch(row)) return null;
            const x = left + slot * (index + 0.5);
            const openY = row.open_ratio === null ? null : y(row.open_ratio);
            const closeY = row.close_ratio === null ? null : y(row.close_ratio);
            if (openY === null && closeY === null) return null;
            const complete = openY !== null && closeY !== null;
            const increasing = complete && closeY <= openY;
            return <g key={row.trading_date} role="button" tabIndex={0} aria-label={describe(row)}
              className="cursor-pointer outline-none focus:stroke-foreground"
              onFocus={() => setFocusedDate(row.trading_date)} onMouseEnter={() => setFocusedDate(row.trading_date)}
              onClick={() => setFocusedDate(row.trading_date)} onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setFocusedDate(row.trading_date); }
              }}>
              <title>{describe(row)}</title>
              {complete ? <rect data-ratio-body="true" x={x - width / 2} y={Math.min(openY, closeY)} width={width} height={Math.max(Math.abs(openY - closeY), 1.5)} rx={1}
                fill={increasing ? "var(--primary)" : "#fb7185"} fillOpacity={increasing ? 0.9 : 0.8} stroke="currentColor" strokeWidth={focusedDate === row.trading_date ? 1.5 : 0} />
                : <circle data-ratio-point="true" cx={x} cy={openY ?? closeY ?? 0} r={3} fill="#fbbf24" />}
            </g>;
          })}
          <text x={left} y={260} className="fill-muted-foreground text-[10px]">{rows[0]?.trading_date}</text>
          <text x={left + plotWidth} y={260} textAnchor="end" className="fill-muted-foreground text-[10px]">{rows.at(-1)?.trading_date}</text>
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
        <span><span className="mr-1 text-primary">■</span>{t.increase}</span>
        <span><span className="mr-1 text-rose-400">■</span>{t.decrease}</span>
        <span><span className="mr-1 text-amber-300">●</span>{t.oneObservation}</span>
      </div>
      {selected && <p className="mt-4 min-h-10 font-mono text-sm leading-6" aria-live="polite">{describe(selected)}</p>}
    </div>
  );
}

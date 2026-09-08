"use client";

import { useId, useState } from "react";

import { useLocale } from "@/i18n/locale-provider";
import type { ProfitRatioDailyRow } from "@/lib/api/generated/profit-ratio";

import { formatRatioPrice, formatRatioValue } from "./display";

type CandleRow = ProfitRatioDailyRow & { open_price: string; high_price: string; low_price: string; close_price: string };

export function hasDailyPriceCandle(row: ProfitRatioDailyRow): row is CandleRow {
  return row.price_status === "COMPLETE" && row.price_quality !== "STALE" && row.open_price !== null && row.close_price !== null
    && row.high_price != null && row.low_price != null;
}

/** These are provider OHLC prices, not highs/lows inferred from endpoint observations. */
export function DailyPriceChart({ rows }: { rows: ProfitRatioDailyRow[] }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const descriptionId = useId();
  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const candles = rows.filter(hasDailyPriceCandle);
  if (candles.length === 0) return <p role="status" className="rounded-lg border border-white/[0.08] p-5 text-sm leading-6 text-muted-foreground">{t.pricesUnavailable}</p>;

  // Number is used only for SVG geometry. All visible values retain decimal-string formatting.
  const lowest = candles.reduce((best, item) => Number(item.low_price) < Number(best.low_price) ? item : best);
  const highest = candles.reduce((best, item) => Number(item.high_price) > Number(best.high_price) ? item : best);
  const minimum = Number(lowest.low_price);
  const maximum = Number(highest.high_price);
  const extent = Math.max(maximum - minimum, maximum * 0.01, 0.01);
  const left = 76;
  const plotWidth = 628;
  const top = 20;
  const plotHeight = 224;
  const slot = plotWidth / Math.max(rows.length, 1);
  const width = Math.min(18, slot * 0.65);
  const y = (value: string) => top + 8 + (maximum - Number(value)) / extent * (plotHeight - 16);
  const selected = candles.find((item) => item.trading_date === focusedDate) ?? candles.at(-1)!;
  const describe = (item: CandleRow) => `${item.trading_date} · ${t.openPrice}: ${formatRatioPrice(item.open_price)} · ${t.highPrice}: ${formatRatioPrice(item.high_price)} · ${t.lowPrice}: ${formatRatioPrice(item.low_price)} · ${t.closingPrice}: ${formatRatioPrice(item.close_price)}`;
  return <div>
    <p id={descriptionId} className="mb-4 text-sm leading-6 text-muted-foreground">{t.priceChartExplanation}</p>
    <div className="overflow-x-auto rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
      <svg viewBox="0 0 730 276" className="h-auto min-w-[520px] w-full" role="img" aria-label={t.priceChartAria} aria-describedby={descriptionId}>
        {[highest.high_price, ...(maximum === minimum ? [] : [lowest.low_price])].map((value, index) => <g key={index} aria-hidden="true">
          <line x1={left} x2={left + plotWidth} y1={y(value)} y2={y(value)} stroke="currentColor" strokeOpacity="0.12" strokeDasharray="4 6" />
          <text x={left - 8} y={y(value) + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">{formatRatioPrice(value)}</text>
        </g>)}
        {rows.map((item, index) => {
          // Incomplete price days keep their own empty slot, regardless of available ratios.
          if (!hasDailyPriceCandle(item)) return null;
          const x = left + slot * (index + 0.5);
          const openY = y(item.open_price);
          const closeY = y(item.close_price);
          const color = closeY <= openY ? "var(--primary)" : "#fb7185";
          return <g key={item.trading_date} role="button" tabIndex={0} aria-label={describe(item)}
            className="cursor-pointer outline-none focus:stroke-foreground"
            onFocus={() => setFocusedDate(item.trading_date)} onMouseEnter={() => setFocusedDate(item.trading_date)}
            onClick={() => setFocusedDate(item.trading_date)} onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setFocusedDate(item.trading_date); }
            }}>
            <title>{describe(item)}</title>
            <line data-price-wick="true" x1={x} x2={x} y1={y(item.high_price)} y2={y(item.low_price)} stroke={color} strokeWidth={1.5} />
            <rect data-price-candle="true" x={x - width / 2} y={Math.min(openY, closeY)} width={width} height={Math.max(Math.abs(openY - closeY), 1.5)} rx={1}
              fill={color} fillOpacity={0.9} stroke="currentColor" strokeWidth={focusedDate === item.trading_date ? 1.5 : 0} />
          </g>;
        })}
        <text x={left} y={268} className="fill-muted-foreground text-[10px]">{rows[0]?.trading_date}</text>
        <text x={left + plotWidth} y={268} textAnchor="end" className="fill-muted-foreground text-[10px]">{rows.at(-1)?.trading_date}</text>
      </svg>
    </div>
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground"><span><span className="mr-1 text-primary">■</span>{t.increase}</span><span><span className="mr-1 text-rose-400">■</span>{t.decrease}</span></div>
    {candles.length < rows.length && <p role="status" className="mt-3 text-sm text-amber-200">{t.priceGaps}</p>}
    <p className="mt-4 min-h-10 font-mono text-sm leading-6" aria-live="polite">{describe(selected)}</p>
    <p className="mt-2 break-words text-xs leading-6 text-muted-foreground">{t.source}: {selected.price_provider ?? "—"} / {selected.price_source_feed ?? "—"}<br />{t.priceBarTimestamp}: {selected.price_market_timestamp ?? "—"} · {t.priceCaptureTimestamp}: {selected.price_observed_at ?? "—"}</p>
  </div>;
}

/** Independent percent axis; use the supplied price return, never recalculate it in the browser. */
export function DailyReturnChart({ rows }: { rows: ProfitRatioDailyRow[] }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const descriptionId = useId();
  const available = rows.filter((item) => item.price_change_return !== null && item.price_status !== "STALE" && item.price_quality !== "STALE");
  if (available.length === 0) return <p role="status" className="rounded-lg border border-white/[0.08] p-5 text-sm leading-6 text-muted-foreground">{t.returnsUnavailable}</p>;
  const largest = available.reduce((best, item) => Math.abs(Number(item.price_change_return)) > Math.abs(Number(best.price_change_return)) ? item : best);
  const magnitude = Math.abs(Number(largest.price_change_return));
  const extent = magnitude || 0.01;
  const axisValue = largest.price_change_return!.replace(/^[+-]/, "");
  const left = 76;
  const plotWidth = 628;
  const slot = plotWidth / Math.max(rows.length, 1);
  const width = Math.min(18, slot * 0.65);
  const baseline = 98;
  const y = (value: string) => baseline - Number(value) / extent * 72;
  return <div>
    <p id={descriptionId} className="mb-4 text-sm leading-6 text-muted-foreground">{t.returnExplanation}</p>
    <div className="overflow-x-auto rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
      <svg viewBox="0 0 730 204" className="h-auto min-w-[520px] w-full" role="img" aria-label={t.returnChartAria} aria-describedby={descriptionId}>
        {(magnitude === 0 ? ["0"] : [axisValue, "0", `-${axisValue}`]).map((value) => <g key={value} aria-hidden="true">
          <line x1={left} x2={left + plotWidth} y1={y(value)} y2={y(value)} stroke="currentColor" strokeOpacity={value === "0" ? 0.3 : 0.12} strokeDasharray={value === "0" ? undefined : "4 6"} />
          <text x={left - 8} y={y(value) + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">{formatRatioValue(value, true)}</text>
        </g>)}
        {rows.map((item, index) => {
          if (item.price_change_return === null || item.price_status === "STALE" || item.price_quality === "STALE") return null;
          const x = left + slot * (index + 0.5);
          const valueY = y(item.price_change_return);
          return <g key={item.trading_date}>
            <title>{item.trading_date} · {t.dailyReturn}: {formatRatioValue(item.price_change_return, true)}</title>
            <rect data-daily-return="true" x={x - width / 2} y={Math.min(valueY, baseline)} width={width} height={Math.max(Math.abs(valueY - baseline), 1.5)} rx={1} fill={valueY <= baseline ? "var(--primary)" : "#fb7185"} fillOpacity={0.85} />
          </g>;
        })}
        <text x={left} y={198} className="fill-muted-foreground text-[10px]">{rows[0]?.trading_date}</text>
        <text x={left + plotWidth} y={198} textAnchor="end" className="fill-muted-foreground text-[10px]">{rows.at(-1)?.trading_date}</text>
      </svg>
    </div>
  </div>;
}

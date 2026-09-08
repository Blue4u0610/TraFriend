"use client";

import { useId, useState } from "react";

import { useLocale } from "@/i18n/locale-provider";
import type { ProfitRatioDailyRow } from "@/lib/api/generated/profit-ratio";

import { formatRatioPrice, formatRatioValue } from "./display";
import { hasRatioProvenanceMismatch } from "./daily-ratio-chart";

type CandleRow = ProfitRatioDailyRow & { open_price: string; high_price: string; low_price: string; close_price: string };
type ReturnRow = ProfitRatioDailyRow & { price_change_return: string };
export type DailyChartLayers = { price: boolean; returns: boolean; ratio: boolean };

export function hasDailyPriceCandle(row: ProfitRatioDailyRow): row is CandleRow {
  return row.price_status === "COMPLETE" && row.price_quality !== "STALE" && row.open_price !== null && row.close_price !== null
    && row.high_price != null && row.low_price != null;
}

function hasDailyReturn(row: ProfitRatioDailyRow): row is ReturnRow {
  return row.price_change_return !== null && row.price_status !== "STALE" && row.price_quality !== "STALE";
}

function hasProfitRatio(row: ProfitRatioDailyRow) {
  return !hasRatioProvenanceMismatch(row) && (row.open_ratio !== null || row.close_ratio !== null);
}

/** One synchronized time plot with independent USD, return and ratio scales. */
export function CombinedDailyChart({ rows, layers }: { rows: ProfitRatioDailyRow[]; layers: DailyChartLayers }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const descriptionId = useId();
  const [focusedDate, setFocusedDate] = useState<string | null>(null);
  const candles = layers.price ? rows.filter(hasDailyPriceCandle) : [];
  const returns = layers.returns ? rows.filter(hasDailyReturn) : [];
  const ratios = layers.ratio ? rows.filter(hasProfitRatio) : [];
  const mismatchedDates = layers.ratio
    ? rows.filter(hasRatioProvenanceMismatch).map((row) => row.trading_date)
    : [];
  const hasPlot = candles.length > 0 || returns.length > 0 || ratios.length > 0;
  const selectedRows = rows.filter((row) =>
    (layers.price && hasDailyPriceCandle(row))
    || (layers.returns && hasDailyReturn(row))
    || (layers.ratio && hasProfitRatio(row)));
  const selected = rows.find((row) => row.trading_date === focusedDate) ?? selectedRows.at(-1);

  const left = 78;
  const plotWidth = 606;
  const top = 24;
  const plotHeight = 246;
  const slot = plotWidth / Math.max(rows.length, 1);
  const candleWidth = Math.min(16, slot * 0.58);
  const priceMinimum = candles.length > 0 ? Math.min(...candles.map((row) => Number(row.low_price))) : 0;
  const priceMaximum = candles.length > 0 ? Math.max(...candles.map((row) => Number(row.high_price))) : 1;
  const priceExtent = Math.max(priceMaximum - priceMinimum, priceMaximum * 0.01, 0.01);
  const returnExtent = Math.max(
    0.01,
    ...returns.map((row) => Math.abs(Number(row.price_change_return))),
  );
  const priceY = (value: string) => top + 8 + (priceMaximum - Number(value)) / priceExtent * (plotHeight - 16);
  const returnY = (value: string) => top + plotHeight / 2 - Number(value) / returnExtent * (plotHeight / 2 - 10);
  const ratioY = (value: string) => top + (1 - Number(value)) * plotHeight;
  const x = (index: number) => left + slot * (index + 0.5);
  const describe = (row: ProfitRatioDailyRow) => [
    row.trading_date,
    layers.price && hasDailyPriceCandle(row)
      ? `${t.openPrice}: ${formatRatioPrice(row.open_price)} · ${t.highPrice}: ${formatRatioPrice(row.high_price)} · ${t.lowPrice}: ${formatRatioPrice(row.low_price)} · ${t.closingPrice}: ${formatRatioPrice(row.close_price)}`
      : null,
    layers.returns && hasDailyReturn(row)
      ? `${t.dailyReturn}: ${formatRatioValue(row.price_change_return, true)}`
      : null,
    layers.ratio && hasProfitRatio(row)
      ? `${t.openRatio}: ${formatRatioValue(row.open_ratio)} · ${t.closeRatio}: ${formatRatioValue(row.close_ratio)}`
      : null,
  ].filter(Boolean).join(" · ");

  return <div>
    <p id={descriptionId} className="mb-4 text-sm leading-6 text-muted-foreground">{t.combinedChartExplanation}</p>
    {mismatchedDates.length > 0 && <p role="status" className="mb-4 rounded-lg border border-amber-400/20 p-3 text-sm leading-6 text-amber-200">{t.provenanceMismatchNotice} {mismatchedDates.join(", ")}</p>}
    {hasPlot ? <div className="overflow-x-auto rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
      <svg viewBox="0 0 820 318" className="h-auto min-w-[600px] w-full" role="img" aria-label={t.combinedChartAria} aria-describedby={descriptionId}>
        {layers.price && candles.length > 0 && [priceMaximum.toString(), priceMinimum.toString()].map((value) => <g key={`price-${value}`} aria-hidden="true">
          <line x1={left} x2={left + plotWidth} y1={priceY(value)} y2={priceY(value)} stroke="currentColor" strokeOpacity="0.1" strokeDasharray="4 6" />
          <text x={left - 8} y={priceY(value) + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">{formatRatioPrice(value)}</text>
        </g>)}
        {layers.returns && returns.length > 0 && <g aria-hidden="true">
          <line x1={left} x2={left + plotWidth} y1={returnY("0")} y2={returnY("0")} stroke="#38bdf8" strokeOpacity="0.35" strokeDasharray="3 5" />
          <text x={left + plotWidth + 8} y={returnY(returnExtent.toString()) + 4} className="fill-sky-400 text-[10px]">{formatRatioValue(returnExtent.toString(), true)}</text>
          <text x={left + plotWidth + 8} y={returnY("0") + 4} className="fill-sky-400 text-[10px]">0%</text>
          <text x={left + plotWidth + 8} y={returnY((-returnExtent).toString()) + 4} className="fill-sky-400 text-[10px]">{formatRatioValue((-returnExtent).toString(), true)}</text>
        </g>}
        {layers.ratio && ratios.length > 0 && [100, 50, 0].map((percent) => <text key={percent} x={784} y={ratioY((percent / 100).toString()) + 4} textAnchor="end" className="fill-amber-300 text-[10px]" aria-hidden="true">{percent}%</text>)}

        {layers.price && rows.map((row, index) => {
          if (!hasDailyPriceCandle(row)) return null;
          const center = x(index);
          const openY = priceY(row.open_price);
          const closeY = priceY(row.close_price);
          const color = closeY <= openY ? "var(--primary)" : "#fb7185";
          return <g key={`price-${row.trading_date}`}>
            <line data-price-wick="true" x1={center} x2={center} y1={priceY(row.high_price)} y2={priceY(row.low_price)} stroke={color} strokeWidth={1.5} />
            <rect data-price-candle="true" x={center - candleWidth / 2} y={Math.min(openY, closeY)} width={candleWidth} height={Math.max(Math.abs(openY - closeY), 1.5)} rx={1} fill={color} fillOpacity={0.72} />
          </g>;
        })}

        {layers.returns && rows.slice(1).map((row, offset) => {
          const previous = rows[offset];
          if (!hasDailyReturn(previous) || !hasDailyReturn(row)) return null;
          return <line key={`return-line-${row.trading_date}`} data-daily-return-line="true" x1={x(offset)} y1={returnY(previous.price_change_return)} x2={x(offset + 1)} y2={returnY(row.price_change_return)} stroke="#38bdf8" strokeWidth={2} strokeOpacity={0.9} />;
        })}
        {layers.returns && rows.map((row, index) => hasDailyReturn(row)
          ? <circle key={`return-point-${row.trading_date}`} data-daily-return="true" cx={x(index)} cy={returnY(row.price_change_return)} r={2.8} fill="#38bdf8" />
          : null)}

        {layers.ratio && rows.slice(1).map((row, offset) => {
          const previous = rows[offset];
          if (!hasProfitRatio(previous) || !hasProfitRatio(row) || previous.close_ratio === null || row.close_ratio === null) return null;
          return <line key={`ratio-line-${row.trading_date}`} data-ratio-line="true" x1={x(offset)} y1={ratioY(previous.close_ratio)} x2={x(offset + 1)} y2={ratioY(row.close_ratio)} stroke="#fbbf24" strokeWidth={2} strokeOpacity={0.9} />;
        })}
        {layers.ratio && rows.map((row, index) => {
          if (!hasProfitRatio(row)) return null;
          const center = x(index);
          return <g key={`ratio-${row.trading_date}`}>
            {row.open_ratio !== null && row.close_ratio !== null && <line data-ratio-body="true" x1={center} x2={center} y1={ratioY(row.open_ratio)} y2={ratioY(row.close_ratio)} stroke="#fbbf24" strokeWidth={3} strokeOpacity={0.55} />}
            {row.open_ratio !== null && <circle data-ratio-open="true" data-ratio-point={row.close_ratio === null ? "true" : undefined} cx={center} cy={ratioY(row.open_ratio)} r={3} fill="var(--background)" stroke="#fbbf24" strokeWidth={1.5} />}
            {row.close_ratio !== null && <circle data-ratio-close="true" data-ratio-point={row.open_ratio === null ? "true" : undefined} cx={center} cy={ratioY(row.close_ratio)} r={3.2} fill="#fbbf24" />}
          </g>;
        })}

        {rows.map((row, index) => {
          const available = (layers.price && hasDailyPriceCandle(row)) || (layers.returns && hasDailyReturn(row)) || (layers.ratio && hasProfitRatio(row));
          if (!available) return null;
          return <rect key={`focus-${row.trading_date}`} role="button" tabIndex={0} aria-label={describe(row)} x={left + slot * index} y={top} width={slot} height={plotHeight} fill="transparent" className="cursor-pointer outline-none focus:stroke-foreground" strokeWidth={focusedDate === row.trading_date ? 1.5 : 0}
            onFocus={() => setFocusedDate(row.trading_date)} onMouseEnter={() => setFocusedDate(row.trading_date)} onClick={() => setFocusedDate(row.trading_date)} onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setFocusedDate(row.trading_date); }
            }} />;
        })}
        <text x={left} y={306} className="fill-muted-foreground text-[10px]">{rows[0]?.trading_date}</text>
        <text x={left + plotWidth} y={306} textAnchor="end" className="fill-muted-foreground text-[10px]">{rows.at(-1)?.trading_date}</text>
      </svg>
    </div> : <p role="status" className="rounded-lg border border-white/[0.08] p-5 text-sm leading-6 text-muted-foreground">{t.noSelectedChartData}</p>}
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
      {layers.price && <><span><span className="mr-1 text-primary">■</span>{t.priceIncreaseLegend}</span><span><span className="mr-1 text-rose-400">■</span>{t.priceDecreaseLegend}</span></>}
      {layers.returns && <span><span className="mr-1 text-sky-400">●━</span>{t.returnLegend}</span>}
      {layers.ratio && <span><span className="mr-1 text-amber-300">○●━</span>{t.ratioLegend}</span>}
    </div>
    {layers.price && candles.length === 0 && <p role="status" className="mt-3 text-sm text-amber-200">{t.pricesUnavailable}</p>}
    {layers.price && candles.length > 0 && candles.length < rows.length && <p role="status" className="mt-3 text-sm text-amber-200">{t.priceGaps}</p>}
    {layers.returns && returns.length === 0 && <p role="status" className="mt-3 text-sm text-amber-200">{t.returnsUnavailable}</p>}
    {layers.ratio && ratios.length === 0 && <p role="status" className="mt-3 text-sm text-amber-200">{t.ratiosNotCaptured}</p>}
    {selected && <p className="mt-4 min-h-10 font-mono text-sm leading-6" aria-live="polite">{describe(selected)}</p>}
    {selected && layers.price && hasDailyPriceCandle(selected) && <p className="mt-2 break-words text-xs leading-6 text-muted-foreground">{t.source}: {selected.price_provider ?? "—"} / {selected.price_source_feed ?? "—"}<br />{t.priceBarTimestamp}: {selected.price_market_timestamp ?? "—"} · {t.priceCaptureTimestamp}: {selected.price_observed_at ?? "—"}</p>}
  </div>;
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

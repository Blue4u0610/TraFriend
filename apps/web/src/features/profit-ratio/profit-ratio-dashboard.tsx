"use client";

import { useEffect, useState } from "react";
import { CircleAlert, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { interpolate, type Dictionary } from "@/i18n/dictionaries";
import { useLocale } from "@/i18n/locale-provider";
import { getProfitRatioDaily, searchProfitRatioUniverse } from "@/lib/api/client";
import type { ProfitRatioConstituent, ProfitRatioDailyHistory } from "@/lib/api/generated/profit-ratio";

import { DailyRatioChart, hasRatioProvenanceMismatch } from "./daily-ratio-chart";
import { formatRatioPrice, formatRatioValue, type ProfitRatioDateRange } from "./display";

type Labels = Dictionary["profitRatio"];

function stateLabel(value: string, t: Labels) {
  const key = value.toUpperCase();
  if (key === "COMPLETE" || key === "READY") return t.complete;
  if (key === "PARTIAL") return t.partial;
  if (key === "PENDING" || key === "NOT_DUE") return t.pending;
  if (key === "STALE") return t.stale;
  if (key === "MOCK") return t.mock;
  if (key === "ESTIMATED" || key === "EXPERIMENTAL") return t.estimated;
  if (key === "WARMUP" || key === "DATA_INSUFFICIENT") return t.insufficient;
  if (key === "DELAYED") return t.delayed;
  if (key === "REALTIME") return t.realtime;
  if (key === "MIXED") return t.mixed;
  if (key === "PROVENANCE_MISMATCH") return t.provenanceMismatch;
  if (key === "NOT_CAPTURED" || key === "EMPTY") return t.notCaptured;
  return t.unavailable;
}

function DailyHistory({ symbol, range, onRetry }: { symbol: string; range: ProfitRatioDateRange; onRetry: () => void }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const [result, setResult] = useState<ProfitRatioDailyHistory | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getProfitRatioDaily(symbol, range.start, range.end, controller.signal)
      .then((response) => { if (active) setResult(response.data); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; controller.abort(); };
  }, [symbol, range.start, range.end]);

  if (failed) return <div role="alert" className="rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-5">
    <p className="flex items-center gap-2 font-medium"><CircleAlert className="size-4" aria-hidden="true" />{t.unavailableTitle}</p>
    <p className="my-3 text-sm text-muted-foreground">{t.genericError}</p>
    <Button variant="outline" onClick={onRetry}>{t.retry}</Button>
  </div>;
  if (!result) return <div role="status" aria-label={t.loading}><Skeleton className="h-80 rounded-2xl" /><p className="sr-only">{t.loading}</p></div>;

  const rows = [...result.rows].sort((a, b) => a.trading_date.localeCompare(b.trading_date));
  const hasRatios = rows.some((row) => row.open_ratio !== null || row.close_ratio !== null);
  const hasPrices = rows.some((row) => row.open_price !== null || row.close_price !== null);
  return <div className="space-y-4">
    <Card className="surface-glow border-white/[0.08] bg-card/85">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><CardDescription className="data-label mb-2">{t.dailyChart}</CardDescription><CardTitle role="heading" aria-level={2} className="text-2xl">{symbol}</CardTitle></div>
          <Badge variant="outline" className="border-primary/25 text-primary">{stateLabel(result.status, t)}</Badge>
        </div>
        <p className="text-xs leading-6 text-muted-foreground">{result.methodology.display_name} · {result.methodology.id} / v{result.methodology.version}<br />{t.source}: {result.provider} · {result.timezone} · {t.updated}: {result.as_of}</p>
        {result.provider.toLowerCase().includes("mock") && <p role="status" className="text-sm text-amber-200">{t.mockNotice}</p>}
      </CardHeader>
      <CardContent>
        {hasRatios ? <DailyRatioChart rows={rows} /> : <p role="status" className="rounded-lg border border-white/[0.08] p-5 text-sm leading-6 text-muted-foreground">{hasPrices ? t.ratiosUnavailable : t.emptySeries}</p>}
        {result.gaps.length > 0 && <details className="mt-4 text-sm text-amber-200">
          <summary className="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-primary">{t.gaps} ({result.gaps.length})</summary>
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">{result.gaps.map((gap) => <li key={`${gap.trading_date}:${gap.phase}:${gap.reason_code}`}>
            {gap.trading_date} · {gap.phase === "OPEN" ? t.openRatio : t.closeRatio} · {gap.reason_code === "NOT_DUE" ? t.pending : gap.reason_code === "NOT_CAPTURED" ? t.notCaptured : t.insufficient} <span className="font-mono text-xs">({gap.reason_code})</span>
          </li>)}</ul>
        </details>}
      </CardContent>
    </Card>
    {rows.length > 0 && <Card className="border-white/[0.08] bg-card/85">
      <CardHeader><CardDescription className="data-label">{t.accessibleView}</CardDescription><CardTitle role="heading" aria-level={2}>{t.dailyObservations}</CardTitle></CardHeader>
      <CardContent>
        <Table>
          <caption className="pb-3 text-left text-xs text-muted-foreground">{t.returnExplanation}</caption>
          <TableHeader><TableRow>
            {[t.date, t.openRatio, t.closeRatio, t.openPrice, t.closingPrice, t.dailyReturn, t.quality].map((heading) => <TableHead key={heading}>{heading}</TableHead>)}
          </TableRow></TableHeader>
          <TableBody>{rows.map((row) => <TableRow key={row.trading_date}>
            <TableCell className="font-mono">{row.trading_date}</TableCell>
            <TableCell className="font-mono" title={row.open_observed_at ?? undefined}>{formatRatioValue(row.open_ratio)}</TableCell>
            <TableCell className="font-mono" title={row.close_observed_at ?? undefined}>{formatRatioValue(row.close_ratio)}</TableCell>
            <TableCell className="font-mono">{formatRatioPrice(row.open_price)}</TableCell>
            <TableCell className="font-mono">{formatRatioPrice(row.close_price)}</TableCell>
            <TableCell className="font-mono">{formatRatioValue(row.price_change_return, true)}</TableCell>
            <TableCell className="text-xs text-muted-foreground">{hasRatioProvenanceMismatch(row) ? t.provenanceMismatch : stateLabel(row.status, t)} · {stateLabel(row.quality, t)}</TableCell>
          </TableRow>)}</TableBody>
        </Table>
      </CardContent>
    </Card>}
    <p className="text-sm leading-6 text-muted-foreground">{t.disclosure}</p>
  </div>;
}

export function ProfitRatioDashboard({ initialRange }: { initialRange: ProfitRatioDateRange }) {
  const { dictionary: { profitRatio: t } } = useLocale();
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<{ query: string; rows: ProfitRatioConstituent[]; failed: boolean } | null>(null);
  const [selected, setSelected] = useState<ProfitRatioConstituent | null>(null);
  const [draftRange, setDraftRange] = useState(initialRange);
  const [range, setRange] = useState(initialRange);
  const [rangeError, setRangeError] = useState(false);
  const [retry, setRetry] = useState(0);
  const trimmedQuery = query.trim();

  useEffect(() => {
    if (!trimmedQuery) return;
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => {
      searchProfitRatioUniverse(trimmedQuery, controller.signal)
        .then((response) => { if (active) setSearchResult({ query: trimmedQuery, rows: response.data, failed: false }); })
        .catch(() => { if (active) setSearchResult({ query: trimmedQuery, rows: [], failed: true }); });
    }, 250);
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [trimmedQuery]);

  return <div className="space-y-5">
    <Card className="border-white/[0.08] bg-card/85">
      <CardHeader><CardTitle role="heading" aria-level={2} className="flex items-center gap-2 text-lg"><Search className="size-4 text-primary" aria-hidden="true" />{t.searchTitle}</CardTitle><CardDescription>{t.searchDescription}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <label htmlFor="profit-ratio-stock-search" className="sr-only">{t.searchLabel}</label>
        <Input id="profit-ratio-stock-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t.searchPlaceholder} maxLength={64} autoComplete="off" />
        {trimmedQuery && <div aria-live="polite">
          {searchResult?.query !== trimmedQuery ? <p role="status" className="text-sm text-muted-foreground">{t.searching}</p>
            : searchResult.failed ? <p role="alert" className="text-sm text-amber-200">{t.searchError}</p>
              : searchResult.rows.length === 0 ? <p role="status" className="text-sm text-muted-foreground">{t.noMatches}</p>
                : <ul aria-label={t.searchResults} className="grid gap-2 sm:grid-cols-2">{searchResult.rows.map((item) => <li key={item.instrument_id}>
                  <button type="button" className="flex w-full items-center gap-3 rounded-lg border border-white/[0.08] px-3 py-3 text-left hover:bg-primary/[0.06] focus-visible:outline-2 focus-visible:outline-primary" onClick={() => { setSelected(item); setQuery(""); }}>
                    <span className="font-mono font-medium text-primary">{item.symbol}</span><span className="text-sm text-muted-foreground">{item.name}</span>
                  </button>
                </li>)}</ul>}
        </div>}
        {selected && <p className="text-xs leading-6 text-muted-foreground">{selected.symbol} · {selected.name}<br />{interpolate(t.membership, { date: selected.as_of, source: selected.source })}</p>}
        <form className="flex flex-wrap items-end gap-3 border-t border-white/[0.07] pt-4" onSubmit={(event) => {
          event.preventDefault();
          const days = (Date.parse(draftRange.end) - Date.parse(draftRange.start)) / 86_400_000;
          if (!draftRange.start || !draftRange.end || !Number.isFinite(days) || days < 0 || days > 366 || draftRange.end > initialRange.end) { setRangeError(true); return; }
          setRangeError(false); setRange({ ...draftRange });
        }}>
          <div><label htmlFor="profit-start" className="mb-1 block text-xs text-muted-foreground">{t.startDate}</label><Input id="profit-start" type="date" max={initialRange.end} value={draftRange.start} onChange={(event) => setDraftRange({ ...draftRange, start: event.target.value })} required /></div>
          <div><label htmlFor="profit-end" className="mb-1 block text-xs text-muted-foreground">{t.endDate}</label><Input id="profit-end" type="date" max={initialRange.end} value={draftRange.end} onChange={(event) => setDraftRange({ ...draftRange, end: event.target.value })} required /></div>
          <Button type="submit" variant="outline">{t.applyRange}</Button>
          {selected && <Button type="button" variant="ghost" onClick={() => setRetry((value) => value + 1)}>{t.refresh}</Button>}
          {rangeError && <p role="alert" className="w-full text-sm text-amber-200">{t.invalidRange}</p>}
        </form>
      </CardContent>
    </Card>
    {selected ? <DailyHistory key={`${selected.instrument_id}:${range.start}:${range.end}:${retry}`} symbol={selected.symbol} range={range} onRetry={() => setRetry((value) => value + 1)} />
      : <p className="rounded-xl border border-dashed border-white/[0.12] p-8 text-center text-sm text-muted-foreground">{t.chooseStock}</p>}
  </div>;
}

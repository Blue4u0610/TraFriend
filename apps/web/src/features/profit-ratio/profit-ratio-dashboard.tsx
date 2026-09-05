"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  CalendarDays,
  CircleAlert,
  Database,
  LineChart,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { interpolate } from "@/i18n/dictionaries";
import { useLocale } from "@/i18n/locale-provider";
import { getProfitRatioHistory, getProfitRatioLatest } from "@/lib/api/client";
import type { ProfitRatioHistory, ProfitRatioLatest } from "@/lib/api/types";

function chartPath(values: number[], width: number, height: number, padding: number) {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((value, index) => {
      const x = padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function ProfitRatioChart({ history }: { history: ProfitRatioHistory }) {
  const { dictionary: t } = useLocale();
  const ratioValues = history.profit_ratio_series.map((point) => Number(point.ratio));
  const priceValues = history.price_series.map((point) => Number(point.close));
  const ratioPath = chartPath(ratioValues, 720, 260, 24);
  const pricePath = chartPath(priceValues, 720, 260, 24);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-5 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="size-2 rounded-full bg-primary" />
          {t.profitRatio.profitRatio}
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="size-2 rounded-full bg-violet-300" />
          {t.profitRatio.closingPrice}
        </span>
        <Badge variant="outline" className="ml-auto border-white/[0.1] font-mono text-xs">
          {t.profitRatio.chartBadge}
        </Badge>
      </div>
      <div className="overflow-hidden rounded-xl border border-white/[0.07] bg-background/40 p-2 sm:p-4">
        <svg
          viewBox="0 0 720 260"
          className="h-auto w-full"
          role="img"
          aria-label={t.profitRatio.chartAria}
        >
          <defs>
            <linearGradient id="ratio-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[55, 105, 155, 205].map((y) => (
            <line
              key={y}
              x1="24"
              x2="696"
              y1={y}
              y2={y}
              stroke="currentColor"
              strokeOpacity="0.09"
              strokeDasharray="4 8"
            />
          ))}
          <path
            d={`${ratioPath} L696,236 L24,236 Z`}
            fill="url(#ratio-area)"
            aria-hidden="true"
          />
          <path
            d={pricePath}
            fill="none"
            stroke="oklch(0.72 0.15 265)"
            strokeWidth="2"
            strokeDasharray="5 6"
            vectorEffect="non-scaling-stroke"
            aria-hidden="true"
          />
          <path
            d={ratioPath}
            fill="none"
            stroke="var(--primary)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            aria-hidden="true"
          />
        </svg>
        <div className="flex justify-between px-3 pb-2 font-mono text-xs text-muted-foreground">
          <span>{history.profit_ratio_series[0]?.trading_date}</span>
          <span>{history.profit_ratio_series.at(-1)?.trading_date}</span>
        </div>
      </div>
    </div>
  );
}

export function ProfitRatioDashboard() {
  const { dictionary, locale } = useLocale();
  const t = dictionary.profitRatio;
  const [latest, setLatest] = useState<ProfitRatioLatest | null>(null);
  const [history, setHistory] = useState<ProfitRatioHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      getProfitRatioLatest("ins_nvda_xnas"),
      getProfitRatioHistory("ins_nvda_xnas", "2026-08-27", "2026-09-04"),
    ])
      .then(([latestResponse, historyResponse]) => {
        if (!active) return;
        setLatest(latestResponse.data);
        setHistory(historyResponse.data);
      })
      .catch(() => {
        if (active) setError(t.genericError);
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  const change = useMemo(() => {
    if (!history || history.profit_ratio_series.length < 2) return null;
    const first = Number(history.profit_ratio_series[0].ratio);
    const last = Number(history.profit_ratio_series.at(-1)?.ratio);
    return (last - first) * 100;
  }, [history]);

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-[0.36fr_0.64fr]">
        <Skeleton className="h-72 rounded-2xl" />
        <Skeleton className="h-72 rounded-2xl" />
        <Skeleton className="h-80 rounded-2xl lg:col-span-2" />
      </div>
    );
  }

  if (error || !latest || !history) {
    return (
      <div role="alert" className="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-5 leading-6 text-amber-100">
        <CircleAlert className="mt-0.5 size-5 shrink-0 text-amber-300" aria-hidden="true" />
        <div>
          <h2 className="font-medium">{t.unavailableTitle}</h2>
          <p className="mt-1 text-sm text-amber-100/75">
            {error ?? t.emptySeries}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[0.36fr_0.64fr]">
      <Card className="surface-glow border-white/[0.08] bg-card/85">
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardDescription className="data-label mb-2">{t.currentEstimate}</CardDescription>
              <CardTitle className="flex items-baseline gap-2 text-2xl">
                NVDA <span className="text-sm font-normal text-muted-foreground">XNAS</span>
              </CardTitle>
            </div>
            <Badge variant="outline" className="border-primary/25 text-primary">
              {t.final}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="font-mono text-5xl font-medium tracking-[-0.065em] text-primary sm:text-6xl">
            {(Number(latest.ratio) * 100).toFixed(1)}%
          </p>
          <div className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary/[0.07] px-3 py-2 text-sm text-primary">
            <ArrowUpRight className="size-4" aria-hidden="true" />
            {interpolate(t.sampleChange, { value: change?.toFixed(1) ?? "—" })}
          </div>
          <div className="mt-6 space-y-3 border-t border-white/[0.07] pt-5 text-sm text-muted-foreground">
            <p className="flex items-center gap-2">
              <CalendarDays className="size-4 text-primary" aria-hidden="true" />
              {interpolate(t.observed, { date: latest.trading_date })}
            </p>
            <p className="flex items-center gap-2">
              <Database className="size-4 text-primary" aria-hidden="true" />
              {interpolate(t.methodology, {
                provider: latest.provider,
                version: latest.methodology.version,
              })}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card className="surface-glow border-white/[0.08] bg-card/85">
        <CardHeader>
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardDescription className="data-label mb-2">{t.historicalComparison}</CardDescription>
              <CardTitle className="text-2xl">{t.ratioVsPrice}</CardTitle>
            </div>
            <LineChart className="size-5 text-violet-300" aria-hidden="true" />
          </div>
        </CardHeader>
        <CardContent>
          <ProfitRatioChart history={history} />
        </CardContent>
      </Card>

      <Card className="surface-glow border-white/[0.08] bg-card/85 lg:col-span-2">
        <CardHeader className="border-b border-white/[0.07]">
          <CardDescription className="data-label mb-2">{t.accessibleView}</CardDescription>
          <CardTitle>{t.mockObservations}</CardTitle>
        </CardHeader>
        <CardContent className="pt-2">
          <Table>
            <TableHeader>
              <TableRow className="border-white/[0.07] hover:bg-transparent">
                <TableHead>{t.date}</TableHead>
                <TableHead>{t.profitRatio}</TableHead>
                <TableHead>{t.nvdaClose}</TableHead>
                <TableHead className="text-right">{t.quality}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.profit_ratio_series.map((point, index) => {
                const price = history.price_series[index];
                return (
                  <TableRow key={point.timestamp} className="border-white/[0.06]">
                    <TableCell className="font-medium">
                      {new Intl.DateTimeFormat(locale, {
                        month: "short",
                        day: "numeric",
                        timeZone: "UTC",
                      }).format(new Date(`${point.trading_date}T12:00:00Z`))}
                    </TableCell>
                    <TableCell className="font-mono text-primary">
                      {(Number(point.ratio) * 100).toFixed(1)}%
                    </TableCell>
                    <TableCell className="font-mono">
                      {price
                        ? new Intl.NumberFormat(locale, {
                            style: "currency",
                            currency: "USD",
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          }).format(Number(price.close))
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {point.quality === "final" ? t.final : point.quality}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <p className="text-sm leading-6 text-muted-foreground lg:col-span-2">
        {interpolate(t.disclosure, { methodology: t.methodologyName })}
      </p>
    </div>
  );
}

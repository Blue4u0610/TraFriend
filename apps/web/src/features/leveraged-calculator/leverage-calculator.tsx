"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownUp,
  CalendarClock,
  CircleAlert,
  Database,
  EqualApproximately,
  Heart,
  Plus,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Dictionary } from "@/i18n/dictionaries";
import { interpolate } from "@/i18n/dictionaries";
import { useLocale } from "@/i18n/locale-provider";
import {
  ApiError,
  calculateAllProducts,
  calculateTarget,
  getPopularUniverse,
  resolveUnderlyingWorkspace,
  searchLeveragedProducts,
  searchUnderlyings,
} from "@/lib/api/client";
import type {
  Calculation,
  MultiCalculation,
  PopularDataset,
  UnderlyingWorkspace,
} from "@/lib/api/types";

import {
  addWatchlistSymbol,
  loadWatchlist,
  removeWatchlistSymbol,
  saveWatchlist,
} from "./watchlist";
import { PopularUniverse } from "./popular-universe";
import { InstrumentSearch } from "./universe-search";
import { buildProductViewRows } from "./workspace-model";

type CalculatorMode = "forward" | "reverse";

function quantizeDecimal(value: string, places: number, decimalShift = 0) {
  const match = value.trim().match(/^(-?)(\d+)(?:\.(\d*))?$/);
  if (!match) return null;
  const [, sign, whole, fraction = ""] = match;
  const digits = BigInt(`${whole}${fraction}`);
  const targetScale = places + decimalShift;
  const sourceScale = fraction.length;
  let scaled: bigint;
  if (targetScale >= sourceScale) {
    scaled = digits * BigInt(10) ** BigInt(targetScale - sourceScale);
  } else {
    const divisor = BigInt(10) ** BigInt(sourceScale - targetScale);
    const quotient = digits / divisor;
    const remainder = digits % divisor;
    scaled = quotient + (remainder * BigInt(2) >= divisor ? BigInt(1) : BigInt(0));
  }
  const placeScale = BigInt(10) ** BigInt(places);
  return {
    negative: sign === "-" && scaled !== BigInt(0),
    whole: scaled / placeScale,
    fraction: (scaled % placeScale).toString().padStart(places, "0"),
  };
}

function formatMoney(value: string, locale: string) {
  const rounded = quantizeDecimal(value, 2);
  if (!rounded) return value;
  const formatter = new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
  });
  const parts = formatter.formatToParts(0);
  const symbol = parts.find((part) => part.type === "currency")?.value ?? "$";
  const decimal = parts.find((part) => part.type === "decimal")?.value ?? ".";
  const symbolFirst =
    parts.findIndex((part) => part.type === "currency") <
    parts.findIndex((part) => part.type === "integer");
  const number = `${rounded.negative ? "-" : ""}${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
  }).format(rounded.whole)}${decimal}${rounded.fraction}`;
  return symbolFirst ? `${symbol}${number}` : `${number}${symbol}`;
}

function formatPercent(value: string, locale: string) {
  const rounded = quantizeDecimal(value, 2, 2);
  if (!rounded) return value;
  const decimal =
    new Intl.NumberFormat(locale)
      .formatToParts(1.1)
      .find((part) => part.type === "decimal")?.value ?? ".";
  return `${rounded.negative ? "-" : ""}${new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
  }).format(rounded.whole)}${decimal}${rounded.fraction}%`;
}

function leverageLabel(factor: string) {
  return `${factor.startsWith("-") ? "" : "+"}${factor}x`;
}

function errorMessage(error: unknown, t: Dictionary["calculator"]) {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      API_UNAVAILABLE: t.errors.apiUnavailable,
      RESOURCE_NOT_FOUND: t.errors.notFound,
      ANCHOR_VERSION_INACTIVE: t.errors.anchorChanged,
      ANCHOR_UNAVAILABLE: t.errors.anchorUnavailable,
      CALCULATION_OUT_OF_DOMAIN: t.errors.outOfDomain,
      VALIDATION_ERROR: t.errors.validation,
    };
    return messages[error.code] ?? t.genericError;
  }
  return t.genericError;
}

export function LeverageCalculator() {
  const { dictionary, locale } = useLocale();
  const t = dictionary.calculator;
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [watchlistReady, setWatchlistReady] = useState(false);
  const [workspace, setWorkspace] = useState<UnderlyingWorkspace | null>(null);
  const [popular, setPopular] = useState<PopularDataset | null>(null);
  const [popularError, setPopularError] = useState<string | null>(null);
  const [mode, setMode] = useState<CalculatorMode>("forward");
  const [forwardTarget, setForwardTarget] = useState("");
  const [forwardResult, setForwardResult] = useState<MultiCalculation | null>(null);
  const [reverseRelationshipId, setReverseRelationshipId] = useState("");
  const [reverseTarget, setReverseTarget] = useState("");
  const [reverseResult, setReverseResult] = useState<Calculation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const localizedErrorMessage = useCallback(
    (requestError: unknown) => errorMessage(requestError, t),
    [t],
  );

  const selectSymbol = useCallback(
    async (symbol: string) => {
      setIsLoading(true);
      setError(null);
      setForwardResult(null);
      setReverseResult(null);
      try {
        const { data } = await resolveUnderlyingWorkspace(symbol);
        setWorkspace(data);
        const available = data.rows.find(
          (row) => row.status === "AVAILABLE" && row.anchor?.underlying.close,
        );
        setForwardTarget(available?.anchor?.underlying.close ?? "");
        const selectedRow =
          data.rows.find(
            (row) => row.relationship.leveraged_product.symbol === symbol,
          ) ?? data.rows[0];
        setReverseRelationshipId(selectedRow?.relationship.id ?? "");
        setReverseTarget(selectedRow?.anchor?.leveraged_product.close ?? "");
      } catch (requestError) {
        setError(errorMessage(requestError, t));
      } finally {
        setIsLoading(false);
      }
    },
    [t],
  );

  const loadPopular = useCallback(async () => {
    setPopular(null);
    setPopularError(null);
    try {
      const { data } = await getPopularUniverse();
      setPopular(data);
    } catch (requestError) {
      setPopularError(errorMessage(requestError, t));
    }
  }, [t]);

  useEffect(() => {
    window.queueMicrotask(() => {
      setWatchlist(loadWatchlist(window.localStorage));
      setWatchlistReady(true);
      void selectSymbol("QQQ");
      void loadPopular();
    });
  }, [loadPopular, selectSymbol]);

  useEffect(() => {
    if (watchlistReady) saveWatchlist(window.localStorage, watchlist);
  }, [watchlist, watchlistReady]);

  useEffect(() => {
    if (
      mode !== "forward" ||
      !workspace ||
      !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(forwardTarget) ||
      /^0(?:\.0+)?$/.test(forwardTarget)
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      setIsCalculating(true);
      calculateAllProducts(workspace.underlying.symbol, forwardTarget)
        .then(({ data }) => setForwardResult(data))
        .catch((requestError) => setError(errorMessage(requestError, t)))
        .finally(() => setIsCalculating(false));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [forwardTarget, mode, t, workspace]);

  const selectedReverseRow = useMemo(
    () =>
      workspace?.rows.find(
        (row) => row.relationship.id === reverseRelationshipId,
      ) ?? null,
    [reverseRelationshipId, workspace],
  );
  const productRows = useMemo(
    () => (workspace ? buildProductViewRows(workspace, forwardResult) : []),
    [forwardResult, workspace],
  );
  const firstAnchor = workspace?.rows.find((row) => row.anchor)?.anchor ?? null;
  const isWatched = workspace
    ? watchlist.includes(workspace.underlying.symbol)
    : false;

  function changeReverseRelationship(value: unknown) {
    const id = String(value);
    setReverseRelationshipId(id);
    setReverseResult(null);
    const row = workspace?.rows.find((candidate) => candidate.relationship.id === id);
    setReverseTarget(row?.anchor?.leveraged_product.close ?? "");
  }

  async function submitReverse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedReverseRow?.anchor) return;
    setIsCalculating(true);
    setError(null);
    try {
      const { data } = await calculateTarget({
        relationship_id: selectedReverseRow.relationship.id,
        anchor_version_id: selectedReverseRow.anchor.id,
        input_side: "leveraged_product",
        target_price: reverseTarget,
      });
      setReverseResult(data);
    } catch (requestError) {
      setError(errorMessage(requestError, t));
    } finally {
      setIsCalculating(false);
    }
  }

  function addSelected() {
    if (workspace) {
      setWatchlist((current) =>
        addWatchlistSymbol(current, workspace.underlying.symbol),
      );
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="surface-glow border-white/[0.08] bg-card/85">
          <CardHeader>
            <CardDescription className="data-label">{t.searchEyebrow}</CardDescription>
            <CardTitle>{t.searchTitle}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <InstrumentSearch
              id="underlying-search"
              title={t.underlyingSearchTitle}
              label={t.underlyingSearchLabel}
              placeholder={t.underlyingSearchPlaceholder}
              loadingText={t.searchLoading}
              noMatchesText={t.underlyingSearchNoMatches}
              search={searchUnderlyings}
              errorMessage={localizedErrorMessage}
              onSelect={selectSymbol}
            />
            <InstrumentSearch
              id="leveraged-product-search"
              title={t.productSearchTitle}
              label={t.productSearchLabel}
              placeholder={t.productSearchPlaceholder}
              loadingText={t.searchLoading}
              noMatchesText={t.productSearchNoMatches}
              search={searchLeveragedProducts}
              errorMessage={localizedErrorMessage}
              onSelect={selectSymbol}
            />
          </CardContent>
        </Card>

        <Card className="surface-glow border-white/[0.08] bg-card/85">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardDescription className="data-label">{t.watchlistEyebrow}</CardDescription>
              <CardTitle>{t.watchlistTitle}</CardTitle>
            </div>
            <Heart className="size-5 text-primary" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            {watchlist.length ? (
              <ul className="flex flex-wrap gap-2">
                {watchlist.map((symbol) => (
                  <li key={symbol} className="flex rounded-full border border-white/[0.1] bg-background/45">
                    <button
                      type="button"
                      onClick={() => void selectSymbol(symbol)}
                      className="px-3 py-2 font-mono text-sm hover:text-primary"
                    >
                      {symbol}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setWatchlist((current) => removeWatchlistSymbol(current, symbol))
                      }
                      className="border-l border-white/[0.08] px-2 text-muted-foreground hover:text-rose-300"
                      aria-label={interpolate(t.removeWatchlist, { symbol })}
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm leading-6 text-muted-foreground">{t.watchlistEmpty}</p>
            )}
          </CardContent>
        </Card>
      </div>

      {isLoading && !workspace ? (
        <Skeleton className="h-[38rem] rounded-2xl" />
      ) : workspace ? (
        <Card className="surface-glow border-white/[0.08] bg-card/85">
          <CardHeader className="border-b border-white/[0.07]">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <CardTitle className="font-mono text-3xl">{workspace.underlying.symbol}</CardTitle>
                  <Badge variant="outline">{workspace.rows.length} ETFs</Badge>
                </div>
                <CardDescription className="mt-2">{workspace.underlying.name}</CardDescription>
              </div>
              <Button
                type="button"
                variant={isWatched ? "outline" : "default"}
                onClick={() =>
                  isWatched
                    ? setWatchlist((current) =>
                        removeWatchlistSymbol(current, workspace.underlying.symbol),
                      )
                    : addSelected()
                }
              >
                {isWatched ? <Trash2 className="size-4" /> : <Plus className="size-4" />}
                {isWatched ? t.remove : t.add}
              </Button>
            </div>
            {firstAnchor ? (
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <Database className="size-4 text-primary" />
                  {t.latestClose}: <strong className="font-mono text-foreground">{formatMoney(firstAnchor.underlying.close ?? "", locale)}</strong>
                </span>
                <span className="inline-flex items-center gap-2">
                  <CalendarClock className="size-4 text-primary" />
                  {interpolate(t.anchorDate, { date: firstAnchor.trading_date })}
                </span>
              </div>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-6 pt-6">
            <Tabs
              value={mode}
              onValueChange={(value) => {
                setMode(value as CalculatorMode);
                setForwardResult(null);
                setReverseResult(null);
              }}
            >
              <TabsList className="h-10 w-full max-w-lg bg-background/55 p-1">
                <TabsTrigger value="forward" className="h-full px-4">
                  {t.forwardMode}
                </TabsTrigger>
                <TabsTrigger value="reverse" className="h-full px-4">
                  {t.reverseMode}
                </TabsTrigger>
              </TabsList>
            </Tabs>

            {mode === "forward" ? (
              <div className="space-y-5">
                <div className="max-w-md space-y-2">
                  <label htmlFor="underlying-target" className="text-sm font-medium">
                    {interpolate(t.targetPrice, { symbol: workspace.underlying.symbol })}
                  </label>
                  <div className="relative">
                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center font-mono text-muted-foreground">$</span>
                    <Input
                      id="underlying-target"
                      inputMode="decimal"
                      value={forwardTarget}
                      onChange={(event) => {
                        setForwardTarget(event.target.value);
                        setForwardResult(null);
                      }}
                      className="h-12 border-white/[0.1] bg-background/55 pl-7 font-mono text-lg"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">{t.autoCalculate}</p>
                </div>

                <div className="grid gap-3 xl:grid-cols-3">
                  {productRows.map((row) => (
                    <div
                      key={row.relationshipId}
                      className="rounded-xl border border-white/[0.08] bg-background/45 p-4"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-mono text-lg font-medium">{row.symbol}</span>
                        <Badge
                          variant="outline"
                          className={row.inverse ? "border-amber-300/25 text-amber-200" : "border-primary/25 text-primary"}
                        >
                          {leverageLabel(row.leverageFactor)}
                        </Badge>
                      </div>
                      {row.status === "AVAILABLE" ? (
                        <>
                          <p className="mt-4 text-xs text-muted-foreground">
                            {t.close}: <span className="font-mono text-foreground">{row.close ? formatMoney(row.close, locale) : "—"}</span>
                          </p>
                          <p className="mt-2 data-label">{t.theoreticalTarget}</p>
                          <p className="mt-1 font-mono text-2xl text-primary">
                            {row.theoreticalTarget
                              ? formatMoney(row.theoreticalTarget, locale)
                              : isCalculating
                                ? t.calculating
                                : "—"}
                          </p>
                        </>
                      ) : (
                        <div className="mt-4 rounded-lg border border-amber-300/15 bg-amber-300/[0.045] px-3 py-4 text-sm text-amber-100">
                          {t.unavailable}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <form onSubmit={submitReverse} className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
                <div className="space-y-4">
                  <div className="space-y-2">
                    <label htmlFor="reverse-product" className="text-sm font-medium">{t.reverseProduct}</label>
                    <Select value={reverseRelationshipId} onValueChange={changeReverseRelationship}>
                      <SelectTrigger id="reverse-product" className="h-11 w-full border-white/[0.1] bg-background/55 px-3">
                        <SelectValue placeholder={t.pairPlaceholder} />
                      </SelectTrigger>
                      <SelectContent>
                        {workspace.rows.map((row) => (
                          <SelectItem key={row.relationship.id} value={row.relationship.id} disabled={row.status !== "AVAILABLE"}>
                            <span className="font-mono">{row.relationship.leveraged_product.symbol}</span>
                            <span>{leverageLabel(row.relationship.leverage_factor)}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="reverse-target" className="text-sm font-medium">
                      {interpolate(t.targetPrice, {
                        symbol: selectedReverseRow?.relationship.leveraged_product.symbol ?? "ETF",
                      })}
                    </label>
                    <Input
                      id="reverse-target"
                      inputMode="decimal"
                      value={reverseTarget}
                      onChange={(event) => setReverseTarget(event.target.value)}
                      className="h-12 border-white/[0.1] bg-background/55 font-mono text-lg"
                      required
                    />
                  </div>
                  <Button type="submit" disabled={!selectedReverseRow?.anchor || isCalculating}>
                    <ArrowDownUp className="size-4" />
                    {isCalculating ? t.calculating : t.calculate}
                  </Button>
                </div>
                <div className="grid min-h-56 place-items-center rounded-2xl border border-primary/20 bg-primary/[0.055] p-6 text-center">
                  {reverseResult ? (
                    <div>
                      <p className="data-label">{t.impliedUnderlying}</p>
                      <p className="mt-3 font-mono text-lg text-primary">{reverseResult.output.symbol}</p>
                      <p className="mt-1 font-mono text-4xl font-medium tracking-[-0.05em]">
                        {formatMoney(reverseResult.output.theoretical_target_price, locale)}
                      </p>
                      <p className="mt-3 text-sm text-muted-foreground">
                        {formatPercent(reverseResult.underlying_return, locale)}
                      </p>
                    </div>
                  ) : (
                    <div>
                      <EqualApproximately className="mx-auto size-8 text-primary/60" />
                      <p className="mt-3 text-sm text-muted-foreground">{t.reverseReady}</p>
                    </div>
                  )}
                </div>
              </form>
            )}

            <p className="text-sm leading-6 text-muted-foreground">{t.singleDayWarning}</p>
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
          <span className="flex gap-3">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-300" />
            {error}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => void selectSymbol(workspace?.underlying.symbol ?? "QQQ")}
          >
            {t.retry}
          </Button>
        </div>
      ) : null}

      <Card className="surface-glow border-white/[0.08] bg-card/75">
        <CardHeader>
          <CardDescription className="data-label">{t.popularEyebrow}</CardDescription>
          <CardTitle>{t.popularTitle}</CardTitle>
          <CardDescription>{t.popularDescription}</CardDescription>
        </CardHeader>
        <CardContent>
          <PopularUniverse
            dataset={popular}
            error={popularError}
            watchlist={watchlist}
            onSelect={(row) => void selectSymbol(row.symbol)}
            onAdd={(symbol) =>
              setWatchlist((current) => addWatchlistSymbol(current, symbol))
            }
            onRetry={() => void loadPopular()}
          />
        </CardContent>
      </Card>
    </div>
  );
}

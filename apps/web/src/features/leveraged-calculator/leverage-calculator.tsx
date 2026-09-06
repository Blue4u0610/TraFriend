"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ArrowDownUp,
  ArrowRight,
  CalendarClock,
  CircleAlert,
  Database,
  EqualApproximately,
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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Dictionary } from "@/i18n/dictionaries";
import { interpolate } from "@/i18n/dictionaries";
import { useLocale } from "@/i18n/locale-provider";
import {
  ApiError,
  calculateTarget,
  getDailyCloseAnchor,
  getLeveragedProducts,
} from "@/lib/api/client";
import type {
  Calculation,
  DailyCloseAnchor,
  LeveragedProducts,
  Relationship,
} from "@/lib/api/types";

type InputSide = "underlying" | "leveraged_product";

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
    scaled =
      quotient +
      (remainder * BigInt(2) >= divisor ? BigInt(1) : BigInt(0));
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

function getErrorMessage(
  error: unknown,
  t: Dictionary["calculator"],
) {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
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
  const [products, setProducts] = useState<LeveragedProducts | null>(null);
  const [relationshipId, setRelationshipId] = useState("");
  const [anchor, setAnchor] = useState<DailyCloseAnchor | null>(null);
  const [inputSide, setInputSide] = useState<InputSide>("underlying");
  const [targetPrice, setTargetPrice] = useState("");
  const [result, setResult] = useState<Calculation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCalculating, setIsCalculating] = useState(false);

  useEffect(() => {
    let active = true;
    getLeveragedProducts("ins_qqq_xnas")
      .then(({ data }) => {
        if (!active) return;
        setProducts(data);
        setRelationshipId(data.relationships[0]?.id ?? "");
      })
      .catch((requestError) => {
        if (active) setError(getErrorMessage(requestError, t));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);

  useEffect(() => {
    if (!relationshipId) return;
    let active = true;
    getDailyCloseAnchor(relationshipId)
      .then(({ data }) => {
        if (!active) return;
        if (
          data.status !== "COMPLETE" ||
          data.underlying.close === null ||
          data.leveraged_product.close === null
        ) {
          throw new ApiError(t.errors.anchorUnavailable, "ANCHOR_UNAVAILABLE", 503);
        }
        setAnchor(data);
        setTargetPrice(data.underlying.close);
      })
      .catch((requestError) => {
        if (active) setError(getErrorMessage(requestError, t));
      });
    return () => {
      active = false;
    };
  }, [relationshipId, t]);

  const relationship = useMemo<Relationship | null>(
    () =>
      products?.relationships.find((item) => item.id === relationshipId) ?? null,
    [products, relationshipId],
  );

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool || !relationship || !anchor) return;

    const lifecycle = new AbortController();
    const registration = context.registerTool(
      {
        name: "calculate_leveraged_target",
        title: t.toolTitle,
        description: t.toolDescription,
        inputSchema: {
          type: "object",
          properties: {
            inputSide: {
              type: "string",
              enum: ["underlying", "leveraged_product"],
            },
            targetPrice: {
              type: "string",
              pattern: "^[0-9]+(?:\\.[0-9]+)?$",
            },
          },
          required: ["inputSide", "targetPrice"],
          additionalProperties: false,
        },
        annotations: { readOnlyHint: true, untrustedContentHint: false },
        async execute(input) {
          if (!input || typeof input !== "object") {
            throw new Error(t.invalidToolObject);
          }
          const candidate = input as Record<string, unknown>;
          const nextSide = candidate.inputSide;
          const nextPrice = candidate.targetPrice;
          if (
            (nextSide !== "underlying" && nextSide !== "leveraged_product") ||
            typeof nextPrice !== "string" ||
            !/^[0-9]+(?:\.[0-9]+)?$/.test(nextPrice)
          ) {
            throw new Error(t.invalidToolInput);
          }

          setInputSide(nextSide);
          setTargetPrice(nextPrice);
          setResult(null);
          setError(null);
          const response = await calculateTarget({
            relationship_id: relationship.id,
            anchor_version_id: anchor.id,
            input_side: nextSide,
            target_price: nextPrice,
          });
          setResult(response.data);
          return {
            symbol: response.data.output.symbol,
            theoreticalTargetPrice:
              response.data.output.theoretical_target_price,
            formulaVersion: response.data.formula_version,
            anchorVersionId: response.data.anchor.id,
          };
        },
      },
      { signal: lifecycle.signal },
    );
    void Promise.resolve(registration).catch(() => undefined);
    return () => lifecycle.abort();
  }, [anchor, relationship, t]);

  function handleRelationshipChange(value: unknown) {
    setRelationshipId(String(value));
    setInputSide("underlying");
    setAnchor(null);
    setResult(null);
    setError(null);
  }

  function handleInputSideChange(value: unknown) {
    const nextSide = value as InputSide;
    setInputSide(nextSide);
    setResult(null);
    setError(null);
    if (anchor) {
      const nextValue =
        nextSide === "underlying"
          ? anchor.underlying.close
          : anchor.leveraged_product.close;
      setTargetPrice(nextValue ?? "");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!relationship || !anchor) return;

    setIsCalculating(true);
    setError(null);
    setResult(null);
    try {
      const response = await calculateTarget({
        relationship_id: relationship.id,
        anchor_version_id: anchor.id,
        input_side: inputSide,
        target_price: targetPrice,
      });
      setResult(response.data);
    } catch (requestError) {
      setError(getErrorMessage(requestError, t));
    } finally {
      setIsCalculating(false);
    }
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <Skeleton className="h-[34rem] rounded-2xl" />
        <Skeleton className="h-[34rem] rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
      <Card className="surface-glow border-white/[0.08] bg-card/85">
        <CardHeader className="border-b border-white/[0.07]">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardDescription className="data-label mb-2">{t.relationship}</CardDescription>
              <CardTitle className="text-2xl">{t.selectProduct}</CardTitle>
            </div>
            <Badge variant="outline" className="w-fit border-primary/25 text-primary">
              {t.mockReference}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 pt-6">
          <div className="space-y-2">
            <label htmlFor="relationship" className="text-sm font-medium">
              {t.pairLabel}
            </label>
            <Select value={relationshipId} onValueChange={handleRelationshipChange}>
              <SelectTrigger id="relationship" className="h-11 w-full border-white/[0.1] bg-background/50 px-3">
                <SelectValue placeholder={t.pairPlaceholder}>
                  {relationship ? (
                    <>
                      <span className="font-mono">{relationship.underlying.symbol}</span>
                      <ArrowRight className="size-3.5 text-muted-foreground" />
                      <span className="font-mono">
                        {relationship.leveraged_product.symbol}
                      </span>
                      <span
                        className={
                          !relationship.leverage_factor.startsWith("-")
                            ? "text-primary"
                            : "text-amber-300"
                        }
                      >
                        {leverageLabel(relationship.leverage_factor)}
                      </span>
                    </>
                  ) : null}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {products?.relationships.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    <span className="font-mono">{item.underlying.symbol}</span>
                    <ArrowRight className="size-3.5 text-muted-foreground" />
                    <span className="font-mono">{item.leveraged_product.symbol}</span>
                    <span className={!item.leverage_factor.startsWith("-") ? "text-primary" : "text-amber-300"}>
                      {leverageLabel(item.leverage_factor)}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {anchor && relationship ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  {
                    label: t.underlyingClose,
                    symbol: anchor.underlying.symbol,
                    price: anchor.underlying.close,
                  },
                  {
                    label: interpolate(t.etfClose, {
                      leverage: leverageLabel(relationship.leverage_factor),
                    }),
                    symbol: anchor.leveraged_product.symbol,
                    price: anchor.leveraged_product.close,
                  },
                ].map((item) => item.price !== null && (
                  <div key={item.symbol} className="rounded-xl border border-white/[0.08] bg-background/45 p-4">
                    <p className="data-label">{item.label}</p>
                    <div className="mt-3 flex items-end justify-between gap-3">
                      <span className="font-mono text-sm text-muted-foreground">{item.symbol}</span>
                      <span className="font-mono text-2xl tracking-tight">
                        {formatMoney(item.price, locale)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-2">
                  <CalendarClock className="size-4 text-primary" aria-hidden="true" />
                  {interpolate(t.tradingDate, { date: anchor.trading_date })}
                </span>
                <span className="inline-flex items-center gap-2">
                  <Database className="size-4 text-primary" aria-hidden="true" />
                  {interpolate(t.provider, { provider: anchor.provider })}
                </span>
              </div>

              <Separator />

              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="space-y-2">
                  <span className="text-sm font-medium">{t.calculateFrom}</span>
                  <Tabs
                    value={inputSide}
                    onValueChange={handleInputSideChange}
                  >
                    <TabsList className="h-10 w-full bg-background/55 p-1">
                      <TabsTrigger value="underlying" className="h-full px-3">
                        {interpolate(t.targetTab, {
                          symbol: relationship.underlying.symbol,
                        })}
                      </TabsTrigger>
                      <TabsTrigger value="leveraged_product" className="h-full px-3">
                        {interpolate(t.targetTab, {
                          symbol: relationship.leveraged_product.symbol,
                        })}
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                <div className="space-y-2">
                  <label htmlFor="target-price" className="text-sm font-medium">
                    {interpolate(t.targetPrice, {
                      symbol:
                        inputSide === "underlying"
                          ? relationship.underlying.symbol
                          : relationship.leveraged_product.symbol,
                    })}
                  </label>
                  <div className="relative">
                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center font-mono text-muted-foreground">
                      $
                    </span>
                    <Input
                      id="target-price"
                      name="target-price"
                      inputMode="decimal"
                      value={targetPrice}
                      onChange={(event) => setTargetPrice(event.target.value)}
                      className="h-12 border-white/[0.1] bg-background/55 pl-7 font-mono text-lg"
                      aria-describedby="target-help"
                      required
                    />
                  </div>
                  <p id="target-help" className="text-sm leading-6 text-muted-foreground">
                    {interpolate(t.anchorHelp, { version: anchor.version })}
                  </p>
                </div>

                <Button type="submit" size="lg" className="h-11 w-full" disabled={isCalculating}>
                  <ArrowDownUp className="size-4" aria-hidden="true" />
                  {isCalculating ? t.calculating : t.calculate}
                </Button>
              </form>
            </>
          ) : (
            <Skeleton className="h-80 rounded-xl" />
          )}

          {error ? (
            <div role="alert" className="flex gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm leading-6 text-amber-100">
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
              {error}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="surface-glow border-white/[0.08] bg-card/85">
        <CardHeader className="border-b border-white/[0.07]">
          <CardDescription className="data-label mb-2">{t.output}</CardDescription>
          <CardTitle className="text-2xl">{t.resultTitle}</CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-[28rem] flex-col pt-6">
          {result ? (
            <div className="flex h-full flex-1 flex-col">
              <div className="rounded-2xl border border-primary/20 bg-primary/[0.055] p-5 sm:p-6">
                <div className="flex items-center justify-between gap-4">
                  <p className="data-label">{t.estimatedTarget}</p>
                  <Badge className="bg-primary/10 text-primary hover:bg-primary/10">
                    {interpolate(t.dailyLeverage, {
                      leverage: leverageLabel(result.leverage_factor),
                    })}
                  </Badge>
                </div>
                <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="font-mono text-lg text-primary">{result.output.symbol}</p>
                    <p className="mt-1 font-mono text-4xl font-medium tracking-[-0.06em] sm:text-5xl">
                      {formatMoney(result.output.theoretical_target_price, locale)}
                    </p>
                  </div>
                  <EqualApproximately className="size-8 text-primary/60" aria-hidden="true" />
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl border border-white/[0.08] bg-background/45 p-4">
                  <p className="data-label">{t.underlyingMove}</p>
                  <p className={`mt-2 font-mono text-xl ${result.underlying_return.startsWith("-") ? "text-rose-300" : "text-primary"}`}>
                    {formatPercent(result.underlying_return, locale)}
                  </p>
                </div>
                <div className="rounded-xl border border-white/[0.08] bg-background/45 p-4">
                  <p className="data-label">{t.leveragedMove}</p>
                  <p className={`mt-2 font-mono text-xl ${result.leveraged_return.startsWith("-") ? "text-rose-300" : "text-primary"}`}>
                    {formatPercent(result.leveraged_return, locale)}
                  </p>
                </div>
              </div>

              <div className="mt-auto pt-6">
                <p className="text-sm leading-6 text-muted-foreground">
                  {t.singleDayWarning}
                </p>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  {result.formula_version} · {result.anchor.id}
                </p>
              </div>
            </div>
          ) : (
            <div className="grid flex-1 place-items-center rounded-2xl border border-dashed border-white/[0.1] bg-background/25 p-8 text-center">
              <div className="max-w-sm">
                <span className="mx-auto grid size-12 place-items-center rounded-full border border-white/[0.1] bg-white/[0.035] text-muted-foreground">
                  <EqualApproximately className="size-5" aria-hidden="true" />
                </span>
                <h3 className="mt-4 font-medium">{t.readyTitle}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {t.readyDescription}
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

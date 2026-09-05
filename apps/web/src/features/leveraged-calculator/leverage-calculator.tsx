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
import { ApiError, calculateTarget, getLeveragedProducts, getReference } from "@/lib/api/client";
import type {
  Calculation,
  DailyReference,
  LeveragedProducts,
  Relationship,
} from "@/lib/api/types";

type InputSide = "underlying" | "leveraged_product";

function formatMoney(value: string, locale: string) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

function formatPercent(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function leverageLabel(factor: string) {
  const value = Number(factor);
  return `${value > 0 ? "+" : ""}${value}x`;
}

function getErrorMessage(
  error: unknown,
  t: Dictionary["calculator"],
) {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      RESOURCE_NOT_FOUND: t.errors.notFound,
      REFERENCE_VERSION_INACTIVE: t.errors.referenceChanged,
      REFERENCE_UNAVAILABLE: t.errors.referenceUnavailable,
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
  const [reference, setReference] = useState<DailyReference | null>(null);
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
    getReference(relationshipId)
      .then(({ data }) => {
        if (!active) return;
        setReference(data);
        setTargetPrice(Number(data.underlying.price).toFixed(2));
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
    if (!context?.registerTool || !relationship || !reference) return;

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
            reference_version_id: reference.id,
            input_side: nextSide,
            target_price: nextPrice,
          });
          setResult(response.data);
          return {
            symbol: response.data.output.symbol,
            theoreticalTargetPrice:
              response.data.output.theoretical_target_price,
            formulaVersion: response.data.formula_version,
            referenceVersionId: response.data.reference.id,
          };
        },
      },
      { signal: lifecycle.signal },
    );
    void Promise.resolve(registration).catch(() => undefined);
    return () => lifecycle.abort();
  }, [reference, relationship, t]);

  function handleRelationshipChange(value: unknown) {
    setRelationshipId(String(value));
    setInputSide("underlying");
    setReference(null);
    setResult(null);
    setError(null);
  }

  function handleInputSideChange(value: unknown) {
    const nextSide = value as InputSide;
    setInputSide(nextSide);
    setResult(null);
    setError(null);
    if (reference) {
      const nextValue =
        nextSide === "underlying"
          ? reference.underlying.price
          : reference.leveraged_product.price;
      setTargetPrice(Number(nextValue).toFixed(2));
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!relationship || !reference) return;

    setIsCalculating(true);
    setError(null);
    setResult(null);
    try {
      const response = await calculateTarget({
        relationship_id: relationship.id,
        reference_version_id: reference.id,
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
                          Number(relationship.leverage_factor) > 0
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
                    <span className={Number(item.leverage_factor) > 0 ? "text-primary" : "text-amber-300"}>
                      {leverageLabel(item.leverage_factor)}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {reference && relationship ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  {
                    label: t.underlyingReference,
                    symbol: reference.underlying.symbol,
                    price: reference.underlying.price,
                  },
                  {
                    label: interpolate(t.etfReference, {
                      leverage: leverageLabel(relationship.leverage_factor),
                    }),
                    symbol: reference.leveraged_product.symbol,
                    price: reference.leveraged_product.price,
                  },
                ].map((item) => (
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
                  {interpolate(t.tradingDate, { date: reference.trading_date })}
                </span>
                <span className="inline-flex items-center gap-2">
                  <Database className="size-4 text-primary" aria-hidden="true" />
                  {interpolate(t.provider, { provider: reference.provider })}
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
                    {interpolate(t.referenceHelp, { version: reference.version })}
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
                  <p className={`mt-2 font-mono text-xl ${Number(result.underlying_return) >= 0 ? "text-primary" : "text-rose-300"}`}>
                    {formatPercent(result.underlying_return)}
                  </p>
                </div>
                <div className="rounded-xl border border-white/[0.08] bg-background/45 p-4">
                  <p className="data-label">{t.leveragedMove}</p>
                  <p className={`mt-2 font-mono text-xl ${Number(result.leveraged_return) >= 0 ? "text-primary" : "text-rose-300"}`}>
                    {formatPercent(result.leveraged_return)}
                  </p>
                </div>
              </div>

              <div className="mt-auto pt-6">
                <p className="text-sm leading-6 text-muted-foreground">
                  {t.singleDayWarning}
                </p>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  {result.formula_version} · {result.reference.id}
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

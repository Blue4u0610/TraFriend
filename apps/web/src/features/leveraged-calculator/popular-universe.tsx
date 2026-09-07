"use client";

import { Fragment, useMemo, useState } from "react";
import { CircleAlert, Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useLocale } from "@/i18n/locale-provider";
import type { PopularDataset, PopularRow } from "@/lib/api/types";

function formatDollarVolume(value: string, locale: string) {
  const [whole] = value.split(".");
  if (!/^\d+$/.test(whole)) return value;
  const formatted = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
  }).format(BigInt(whole));
  return `$${formatted}`;
}

export function PopularUniverse({
  dataset,
  error,
  watchlist,
  onSelect,
  onAdd,
  onRetry,
}: {
  dataset: PopularDataset | null;
  error: string | null;
  watchlist: readonly string[];
  onSelect: (row: PopularRow) => void;
  onAdd: (symbol: string) => void;
  onRetry: () => void;
}) {
  const { dictionary, locale } = useLocale();
  const t = dictionary.calculator;
  const [query, setQuery] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const rows = useMemo(() => {
    const normalized = query.trim().toUpperCase();
    if (!normalized) return dataset?.rows ?? [];
    return (dataset?.rows ?? []).filter(
      (row) =>
        row.symbol.includes(normalized) ||
        (row.name ?? "").toUpperCase().includes(normalized),
    );
  }, [dataset, query]);

  if (error) {
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm text-amber-100 sm:flex-row sm:items-center sm:justify-between"
      >
        <span className="flex gap-3">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {t.popularLoadError}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          {t.retry}
        </Button>
      </div>
    );
  }
  if (!dataset) return <Skeleton className="h-28 rounded-xl" />;
  if (dataset.population_status === "NOT_POPULATED") {
    return (
      <div className="rounded-xl border border-dashed border-white/[0.1] bg-background/25 p-6">
        <p className="font-medium">{t.popularNotPopulated}</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {t.popularNotPopulatedDetail}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <label htmlFor="popular-filter" className="sr-only">
        {t.popularFilter}
      </label>
      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input
          id="popular-filter"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t.popularFilter}
          className="h-10 bg-background/55 pl-10"
        />
      </div>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-white/[0.1] p-6 text-sm text-muted-foreground">
          {t.popularNoMatches}
        </p>
      ) : (
        <div className="max-h-[42rem] overflow-auto rounded-xl border border-white/[0.08]">
          <table className="w-full min-w-[48rem] text-sm">
            <thead className="sticky top-0 z-10 bg-background/95 text-left text-xs uppercase tracking-wider text-muted-foreground backdrop-blur">
              <tr>
                <th className="px-4 py-3">{t.rank}</th>
                <th className="px-4 py-3">{t.symbol}</th>
                <th className="px-4 py-3">{t.metric}</th>
                <th className="px-4 py-3">{t.products}</th>
                <th className="px-4 py-3"><span className="sr-only">{t.add}</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.06]">
              {rows.map((row) => {
                const selected = selectedSymbol === row.symbol;
                const watched = watchlist.includes(row.symbol);
                return (
                  <Fragment key={row.symbol}>
                    <tr data-testid={`popular-row-${row.symbol}`}>
                      <td className="px-4 py-3 font-mono">{row.rank}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          aria-expanded={selected}
                          onClick={() => {
                            setSelectedSymbol(selected ? null : row.symbol);
                            if (row.supported_leveraged_products > 0) onSelect(row);
                          }}
                          className="text-left hover:text-primary focus-visible:outline-2 focus-visible:outline-primary"
                        >
                          <span className="font-mono font-medium">{row.symbol}</span>
                          <span className="ml-3 text-muted-foreground">{row.name}</span>
                        </button>
                      </td>
                      <td className="px-4 py-3 font-mono">
                        {formatDollarVolume(row.trading_metric, locale)}
                      </td>
                      <td className="px-4 py-3">{row.supported_leveraged_products}</td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={row.supported_leveraged_products === 0 || watched}
                          onClick={() => onAdd(row.symbol)}
                        >
                          <Plus className="size-3.5" /> {watched ? t.saved : t.add}
                        </Button>
                      </td>
                    </tr>
                    {selected ? (
                      <tr>
                        <td colSpan={5} className="bg-primary/[0.035] px-4 py-3 text-sm text-muted-foreground">
                          {row.supported_leveraged_products > 0
                            ? t.popularWorkspaceOpened
                            : t.popularNoProducts}
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import type { ApiResponse, Instrument } from "@/lib/api/types";

import { normalizedSearchQuery } from "./workspace-model";

type SearchStatus = "idle" | "loading" | "ready" | "error";

type InstrumentSearchProps = {
  id: string;
  title: string;
  label: string;
  placeholder: string;
  loadingText: string;
  noMatchesText: string;
  search: (query: string) => Promise<ApiResponse<Instrument[]>>;
  errorMessage: (error: unknown) => string;
  onSelect: (symbol: string) => void | Promise<void>;
};

export function InstrumentSearch({
  id,
  title,
  label,
  placeholder,
  loadingText,
  noMatchesText,
  search,
  errorMessage,
  onSelect,
}: InstrumentSearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Instrument[]>([]);
  const [status, setStatus] = useState<SearchStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const normalized = normalizedSearchQuery(query);
    if (!normalized) return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      search(normalized)
        .then(({ data }) => {
          if (cancelled) return;
          setResults(data);
          setStatus("ready");
        })
        .catch((requestError) => {
          if (cancelled) return;
          setResults([]);
          setError(errorMessage(requestError));
          setStatus("error");
        });
    }, 200);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [errorMessage, query, search]);

  function changeQuery(value: string) {
    const normalized = normalizedSearchQuery(value);
    setQuery(value);
    setResults([]);
    setError(null);
    setStatus(normalized ? "loading" : "idle");
  }

  async function select(symbol: string) {
    setQuery("");
    setResults([]);
    setStatus("idle");
    setError(null);
    await onSelect(symbol);
  }

  const resultsId = `${id}-results`;

  return (
    <section aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`} className="mb-2 text-sm font-medium">
        {title}
      </h3>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
        <Input
          id={id}
          value={query}
          onChange={(event) => changeQuery(event.target.value)}
          placeholder={placeholder}
          autoComplete="off"
          className="h-10 border-white/[0.1] bg-background/55 pl-10"
          aria-controls={resultsId}
          aria-busy={status === "loading"}
        />
      </div>
      {results.length ? (
        <ul
          id={resultsId}
          className="mt-2 divide-y divide-white/[0.06] rounded-xl border border-white/[0.08] bg-background/45"
        >
          {results.map((instrument) => (
            <li key={instrument.id}>
              <button
                type="button"
                onClick={() => void select(instrument.symbol)}
                className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-white/[0.035] focus-visible:outline-2 focus-visible:outline-primary"
              >
                <span className="min-w-0">
                  <span className="font-mono font-medium">{instrument.symbol}</span>
                  <span className="ml-3 text-sm text-muted-foreground">
                    {instrument.name}
                  </span>
                </span>
                <Badge variant="outline">{instrument.instrument_type}</Badge>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {status === "loading" ? (
        <p className="mt-2 text-sm text-muted-foreground" role="status">
          {loadingText}
        </p>
      ) : null}
      {status === "ready" && results.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground" role="status">
          {noMatchesText}
        </p>
      ) : null}
      {status === "error" && error ? (
        <p className="mt-2 text-sm text-amber-200" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

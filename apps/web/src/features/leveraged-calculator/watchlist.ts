export const WATCHLIST_STORAGE_KEY = "trafriend.watchlist.v1";

export type StorageLike = Pick<Storage, "getItem" | "setItem">;

export function normalizeWatchlist(symbols: string[]): string[] {
  return Array.from(
    new Set(
      symbols
        .map((symbol) => symbol.trim().toUpperCase())
        .filter((symbol) => /^[A-Z0-9.-]{1,16}$/.test(symbol)),
    ),
  ).slice(0, 50);
}

export function addWatchlistSymbol(symbols: string[], symbol: string): string[] {
  return normalizeWatchlist([...symbols, symbol]);
}

export function removeWatchlistSymbol(symbols: string[], symbol: string): string[] {
  const normalized = symbol.trim().toUpperCase();
  return symbols.filter((candidate) => candidate !== normalized);
}

export function loadWatchlist(storage: StorageLike): string[] {
  try {
    const value = storage.getItem(WATCHLIST_STORAGE_KEY);
    if (!value) return [];
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed)
      ? normalizeWatchlist(parsed.filter((item): item is string => typeof item === "string"))
      : [];
  } catch {
    return [];
  }
}

export function saveWatchlist(storage: StorageLike, symbols: string[]): void {
  storage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(normalizeWatchlist(symbols)));
}

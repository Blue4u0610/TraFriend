import { describe, expect, it } from "vitest";

import {
  WATCHLIST_STORAGE_KEY,
  addWatchlistSymbol,
  loadWatchlist,
  removeWatchlistSymbol,
  saveWatchlist,
} from "./watchlist";

class MemoryStorage {
  private values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
}

describe("watchlist persistence", () => {
  it("adds normalized underlying symbols without duplicates", () => {
    expect(addWatchlistSymbol(["QQQ"], " qqq ")).toEqual(["QQQ"]);
    expect(addWatchlistSymbol(["QQQ"], "sndk")).toEqual(["QQQ", "SNDK"]);
  });

  it("removes an underlying", () => {
    expect(removeWatchlistSymbol(["QQQ", "SNDK"], "qqq")).toEqual(["SNDK"]);
  });

  it("restores the watchlist after a reload and ignores malformed values", () => {
    const storage = new MemoryStorage();
    saveWatchlist(storage, ["QQQ", "sndk"]);
    expect(loadWatchlist(storage)).toEqual(["QQQ", "SNDK"]);

    storage.setItem(WATCHLIST_STORAGE_KEY, "not-json");
    expect(loadWatchlist(storage)).toEqual([]);
  });
});

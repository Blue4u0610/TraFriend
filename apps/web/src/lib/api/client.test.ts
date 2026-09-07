import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  getPopularUniverse,
  searchLeveragedProducts,
  searchUnderlyings,
  searchUniverse,
} from "./client";

describe("TraFriend API client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("classifies a network failure without exposing browser error details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));

    await expect(getPopularUniverse()).rejects.toMatchObject({
      code: "API_UNAVAILABLE",
      status: 0,
      message: "The TraFriend data service is unavailable.",
    });
    await expect(getPopularUniverse()).rejects.toBeInstanceOf(ApiError);
  });

  it("encodes metadata search text and returns the API response", async () => {
    const response = {
      data: [],
      meta: { request_id: "req_test", next_cursor: null },
    };
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(searchUniverse("ProShares QQQ")).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("q=ProShares%20QQQ"),
      expect.objectContaining({ headers: expect.objectContaining({ Accept: "application/json" }) }),
    );
  });

  it("uses distinct endpoints for underlying and leveraged-product search", async () => {
    const response = {
      data: [],
      meta: { request_id: "req_test", next_cursor: null },
    };
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify(response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.test.trafriend.com/");

    await searchUnderlyings("Micron MU");
    await searchLeveragedProducts("MUU & MUG");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "https://api.test.trafriend.com/api/v1/universe/underlyings/search?q=Micron%20MU&limit=10",
    );
    expect(fetchMock.mock.calls[1][0]).toBe(
      "https://api.test.trafriend.com/api/v1/universe/leveraged-products/search?q=MUU%20%26%20MUG&limit=10",
    );
  });
});

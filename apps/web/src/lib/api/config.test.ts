import { describe, expect, it } from "vitest";

import { getApiBaseUrl } from "@/lib/api/config";

describe("getApiBaseUrl", () => {
  it("keeps local development working without configuration", () => {
    expect(getApiBaseUrl(undefined, "development", "localhost")).toBe(
      "http://localhost:8010",
    );
  });

  it("uses one normalized configured API base URL", () => {
    expect(getApiBaseUrl("https://api.trafriend.com/", "production")).toBe(
      "https://api.trafriend.com",
    );
  });

  it("does not silently fall back to localhost in production", () => {
    expect(() => getApiBaseUrl(undefined, "production")).toThrow(
      "NEXT_PUBLIC_API_BASE_URL is required in production",
    );
    expect(() =>
      getApiBaseUrl("http://api.trafriend.com", "production"),
    ).toThrow("must use HTTPS");
  });

  it("rejects credential-bearing public URLs", () => {
    expect(() =>
      getApiBaseUrl("https://user:secret@api.trafriend.com", "production"),
    ).toThrow("must not contain credentials");
  });
});

import type {
  ApiResponse,
  Calculation,
  DailyCloseAnchor,
  Health,
  Instrument,
  LeveragedProducts,
  MultiCalculation,
  PopularDataset,
  ProfitRatioHistory,
  ProfitRatioLatest,
  UnderlyingWorkspace,
} from "@/lib/api/types";
import { getApiBaseUrl } from "@/lib/api/config";

type Problem = {
  code?: string;
  detail?: string;
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "The TraFriend data service is unavailable.",
      "API_UNAVAILABLE",
      0,
    );
  }

  if (!response.ok) {
    const problem = (await response.json().catch(() => ({}))) as Problem;
    throw new ApiError(
      problem.detail ?? "TraFriend API request failed.",
      problem.code ?? "API_REQUEST_FAILED",
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function getHealth(): Promise<Health> {
  return fetchJson<Health>("/health");
}

export function searchInstruments(query: string): Promise<ApiResponse<Instrument[]>> {
  return fetchJson<ApiResponse<Instrument[]>>(
    `/api/v1/instruments/search?query=${encodeURIComponent(query)}&limit=10`,
  );
}

export function searchUniverse(query: string): Promise<ApiResponse<Instrument[]>> {
  return fetchJson<ApiResponse<Instrument[]>>(
    `/api/v1/universe/search?q=${encodeURIComponent(query)}&limit=10`,
  );
}

export function searchUnderlyings(
  query: string,
): Promise<ApiResponse<Instrument[]>> {
  return fetchJson<ApiResponse<Instrument[]>>(
    `/api/v1/universe/underlyings/search?q=${encodeURIComponent(query)}&limit=10`,
  );
}

export function searchLeveragedProducts(
  query: string,
): Promise<ApiResponse<Instrument[]>> {
  return fetchJson<ApiResponse<Instrument[]>>(
    `/api/v1/universe/leveraged-products/search?q=${encodeURIComponent(query)}&limit=10`,
  );
}

export function getUnderlyingWorkspace(
  symbol: string,
): Promise<ApiResponse<UnderlyingWorkspace>> {
  return fetchJson<ApiResponse<UnderlyingWorkspace>>(
    `/api/v1/underlyings/${encodeURIComponent(symbol)}`,
  );
}

export function resolveUnderlyingWorkspace(
  symbol: string,
): Promise<ApiResponse<UnderlyingWorkspace>> {
  return fetchJson<ApiResponse<UnderlyingWorkspace>>(
    `/api/v1/underlyings/${encodeURIComponent(symbol)}/resolve`,
    { method: "POST" },
  );
}

export function calculateAllProducts(
  symbol: string,
  targetPrice: string,
): Promise<ApiResponse<MultiCalculation>> {
  return fetchJson<ApiResponse<MultiCalculation>>(
    `/api/v1/underlyings/${encodeURIComponent(symbol)}/calculations`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_price: targetPrice }),
    },
  );
}

export function getPopularUniverse(): Promise<ApiResponse<PopularDataset>> {
  return fetchJson<ApiResponse<PopularDataset>>(
    "/api/v1/popular?ranking_period=2026-09&limit=100",
  );
}

export function getLeveragedProducts(
  instrumentId: string,
): Promise<ApiResponse<LeveragedProducts>> {
  return fetchJson<ApiResponse<LeveragedProducts>>(
    `/api/v1/instruments/${encodeURIComponent(instrumentId)}/leveraged-products`,
  );
}

export function getDailyCloseAnchor(
  relationshipId: string,
): Promise<ApiResponse<DailyCloseAnchor>> {
  return fetchJson<ApiResponse<DailyCloseAnchor>>(
    `/api/v1/leveraged-etf/relationships/${encodeURIComponent(relationshipId)}/anchor`,
  );
}

export function calculateTarget(payload: {
  relationship_id: string;
  anchor_version_id: string;
  input_side: "underlying" | "leveraged_product";
  target_price: string;
}): Promise<ApiResponse<Calculation>> {
  return fetchJson<ApiResponse<Calculation>>("/api/v1/leveraged-etf/calculations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getProfitRatioLatest(
  instrumentId: string,
): Promise<ApiResponse<ProfitRatioLatest>> {
  return fetchJson<ApiResponse<ProfitRatioLatest>>(
    `/api/v1/profit-ratio/instruments/${encodeURIComponent(instrumentId)}/latest`,
  );
}

export function getProfitRatioHistory(
  instrumentId: string,
  start: string,
  end: string,
): Promise<ApiResponse<ProfitRatioHistory>> {
  const query = new URLSearchParams({
    start,
    end,
    interval: "1d",
    include_price: "true",
  });
  return fetchJson<ApiResponse<ProfitRatioHistory>>(
    `/api/v1/profit-ratio/instruments/${encodeURIComponent(instrumentId)}/history?${query}`,
  );
}

import type {
  ApiResponse,
  Calculation,
  DailyReference,
  Health,
  Instrument,
  LeveragedProducts,
  ProfitRatioHistory,
  ProfitRatioLatest,
} from "@/lib/api/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });

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

export function getLeveragedProducts(
  instrumentId: string,
): Promise<ApiResponse<LeveragedProducts>> {
  return fetchJson<ApiResponse<LeveragedProducts>>(
    `/api/v1/instruments/${encodeURIComponent(instrumentId)}/leveraged-products`,
  );
}

export function getReference(
  relationshipId: string,
): Promise<ApiResponse<DailyReference>> {
  return fetchJson<ApiResponse<DailyReference>>(
    `/api/v1/leveraged-etf/relationships/${encodeURIComponent(relationshipId)}/reference`,
  );
}

export function calculateTarget(payload: {
  relationship_id: string;
  reference_version_id: string;
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


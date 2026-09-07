export type ApiMeta = {
  request_id: string;
  next_cursor?: string | null;
};

export type ApiResponse<T> = {
  data: T;
  meta: ApiMeta;
};

export type Instrument = {
  id: string;
  symbol: string;
  name: string;
  instrument_type: "stock" | "etf" | "leveraged_etf";
  exchange_mic: string;
  currency: string;
  status: string;
  capabilities: {
    leveraged_relationships: boolean;
    profit_ratio: boolean;
  };
  created_at?: string | null;
  updated_at?: string | null;
};

export type Relationship = {
  id: string;
  underlying: Instrument;
  leveraged_product: Instrument;
  leverage_factor: string;
  objective_period: "daily";
  effective_from: string;
  effective_to: string | null;
  issuer: string | null;
  direction: "LONG" | "INVERSE" | null;
  status: string;
  authoritative_source: string | null;
  verified_at: string | null;
};

export type LeveragedProducts = {
  selected_instrument_id: string;
  underlying: Instrument;
  relationships: Relationship[];
};

export type DailyCloseAnchorValue = {
  symbol: string;
  close: string | null;
  trading_date: string | null;
  market_timestamp: string | null;
  observed_at: string;
  source: string;
  source_feed: string;
  currency: "USD";
  quality: "REALTIME" | "DELAYED" | "STALE" | "UNAVAILABLE";
  status: "AVAILABLE" | "REJECTED" | "MISSING";
  message: string;
};

export type DailyCloseAnchor = {
  id: string;
  relationship_id: string;
  trading_date: string;
  status: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
  version: number;
  underlying: DailyCloseAnchorValue;
  leveraged_product: DailyCloseAnchorValue;
  session_closed_at: string;
  captured_at: string;
  provider: string;
  source_feed: string;
  anchor_type: "DAILY_CLOSE_ANCHOR";
};

export type Calculation = {
  formula_version: string;
  relationship_id: string;
  leverage_factor: string;
  objective_period: string;
  input: {
    side: "underlying" | "leveraged_product";
    instrument_id: string;
    symbol: string;
    target_price: string;
  };
  output: {
    side: "underlying" | "leveraged_product";
    instrument_id: string;
    symbol: string;
    theoretical_target_price: string;
  };
  underlying_return: string;
  leveraged_return: string;
  anchor: {
    id: string;
    anchor_type: "DAILY_CLOSE_ANCHOR";
    trading_date: string;
    underlying_close: string;
    leveraged_product_close: string;
    underlying_market_timestamp: string;
    leveraged_product_market_timestamp: string;
    provider: string;
    source_feed: string;
  };
  calculated_at: string;
  warnings: { code: string; message: string }[];
};

export type AnchorResolution = {
  relationship: Relationship;
  status: "AVAILABLE" | "UNAVAILABLE";
  anchor_source: "CACHE" | "ON_DEMAND" | "NONE";
  message: string;
  anchor: DailyCloseAnchor | null;
};

export type UnderlyingWorkspace = {
  underlying: Instrument;
  rows: AnchorResolution[];
};

export type MultiCalculationRow = {
  relationship: Relationship;
  status: "AVAILABLE" | "UNAVAILABLE";
  anchor: DailyCloseAnchor | null;
  theoretical_target_price: string | null;
  underlying_return: string | null;
  leveraged_return: string | null;
  message: string;
};

export type MultiCalculation = {
  underlying: Instrument;
  target_price: string;
  rows: MultiCalculationRow[];
  formula_version: "leveraged-daily-close-linear/v2";
};

export type PopularRow = {
  rank: number;
  symbol: string;
  name: string | null;
  trading_metric: string;
  calculated_at: string;
  source: string;
  completeness_status: "COMPLETE" | "INCOMPLETE";
  sessions_observed: number;
  sessions_expected: number;
  supported_leveraged_products: number;
};

export type PopularDataset = {
  ranking_period: string;
  period_status: "SEPTEMBER_TO_DATE" | "MONTH_TO_DATE" | "FINAL";
  ranking_type: "DOLLAR_TRADING_VOLUME";
  population_status: "COMPLETE" | "PARTIAL" | "NOT_POPULATED";
  rows: PopularRow[];
};

export type Methodology = {
  id: string;
  version: string;
  display_name: string;
};

export type ProfitRatioLatest = {
  instrument: Instrument;
  ratio: string;
  observed_at: string;
  trading_date: string;
  freshness: string;
  methodology: Methodology;
  provider: string;
};

export type ProfitRatioPoint = {
  timestamp: string;
  trading_date: string;
  ratio: string;
  quality: string;
};

export type PricePoint = {
  timestamp: string;
  trading_date: string;
  close: string;
  adjustment: string;
};

export type ProfitRatioHistory = {
  instrument_id: string;
  symbol: string;
  interval: string;
  timezone: string;
  methodology: Methodology;
  profit_ratio_series: ProfitRatioPoint[];
  price_series: PricePoint[];
  gaps: string[];
  as_of: string;
  provider: string;
};

export type Health = {
  status: "ok";
  service: string;
  market_data_provider: "mock";
};

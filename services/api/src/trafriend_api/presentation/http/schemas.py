from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class FromDomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ResponseMeta(BaseModel):
    request_id: str
    next_cursor: Optional[str] = None


class CapabilitiesSchema(FromDomainModel):
    leveraged_relationships: bool
    profit_ratio: bool


class InstrumentSchema(FromDomainModel):
    id: str
    symbol: str
    name: str
    instrument_type: Literal["stock", "etf", "leveraged_etf"]
    exchange_mic: str
    currency: str
    status: str
    capabilities: CapabilitiesSchema
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RelationshipSchema(FromDomainModel):
    id: str
    underlying: InstrumentSchema
    leveraged_product: InstrumentSchema
    leverage_factor: Decimal
    objective_period: Literal["daily"]
    effective_from: date
    effective_to: Optional[date] = None
    issuer: Optional[str] = None
    direction: Optional[Literal["LONG", "INVERSE"]] = None
    status: str
    authoritative_source: Optional[str] = None
    verified_at: Optional[datetime] = None


class DailyCloseAnchorValueSchema(FromDomainModel):
    symbol: str
    close: Optional[Decimal]
    trading_date: Optional[date]
    market_timestamp: Optional[datetime]
    observed_at: datetime
    source: str
    source_feed: str
    currency: Literal["USD"]
    quality: Literal["REALTIME", "DELAYED", "STALE", "UNAVAILABLE"]
    status: Literal["AVAILABLE", "REJECTED", "MISSING"]
    message: str


class DailyCloseAnchorSchema(FromDomainModel):
    id: str
    relationship_id: str
    trading_date: date
    status: Literal["COMPLETE", "PARTIAL", "UNAVAILABLE"]
    version: int
    underlying: DailyCloseAnchorValueSchema
    leveraged_product: DailyCloseAnchorValueSchema
    session_closed_at: datetime
    captured_at: datetime
    provider: str
    source_feed: str
    signed_leverage: Decimal
    created_at: datetime
    anchor_type: Literal["DAILY_CLOSE_ANCHOR"]


class InstrumentCollectionResponse(BaseModel):
    data: List[InstrumentSchema]
    meta: ResponseMeta


class InstrumentResponse(BaseModel):
    data: InstrumentSchema
    meta: ResponseMeta


class LeveragedProductsData(BaseModel):
    selected_instrument_id: str
    underlying: InstrumentSchema
    relationships: List[RelationshipSchema]


class LeveragedProductsResponse(BaseModel):
    data: LeveragedProductsData
    meta: ResponseMeta


class DailyCloseAnchorResponse(BaseModel):
    data: DailyCloseAnchorSchema
    meta: ResponseMeta


class CalculationRequest(BaseModel):
    relationship_id: str
    anchor_version_id: str
    input_side: Literal["underlying", "leveraged_product"]
    target_price: Decimal

    @field_validator("target_price", mode="before")
    @classmethod
    def require_decimal_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("target_price must be a decimal string")
        return value


class CalculationInputSchema(BaseModel):
    side: Literal["underlying", "leveraged_product"]
    instrument_id: str
    symbol: str
    target_price: Decimal


class CalculationOutputSchema(BaseModel):
    side: Literal["underlying", "leveraged_product"]
    instrument_id: str
    symbol: str
    theoretical_target_price: Decimal


class CalculationAnchorSchema(BaseModel):
    id: str
    anchor_type: Literal["DAILY_CLOSE_ANCHOR"]
    trading_date: date
    underlying_close: Decimal
    leveraged_product_close: Decimal
    underlying_market_timestamp: datetime
    leveraged_product_market_timestamp: datetime
    provider: str
    source_feed: str


class WarningSchema(BaseModel):
    code: str
    message: str


class CalculationData(BaseModel):
    formula_version: str
    relationship_id: str
    leverage_factor: Decimal
    objective_period: str
    input: CalculationInputSchema
    output: CalculationOutputSchema
    underlying_return: Decimal
    leveraged_return: Decimal
    anchor: CalculationAnchorSchema
    calculated_at: datetime
    warnings: List[WarningSchema]


class CalculationResponse(BaseModel):
    data: CalculationData
    meta: ResponseMeta


class AnchorResolutionSchema(BaseModel):
    relationship: RelationshipSchema
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    anchor_source: Literal["CACHE", "ON_DEMAND", "NONE"]
    message: str
    anchor: Optional[DailyCloseAnchorSchema] = None


class UnderlyingWorkspaceData(BaseModel):
    underlying: InstrumentSchema
    rows: List[AnchorResolutionSchema]


class UnderlyingWorkspaceResponse(BaseModel):
    data: UnderlyingWorkspaceData
    meta: ResponseMeta


class PopularRowSchema(BaseModel):
    rank: int
    symbol: str
    name: Optional[str] = None
    trading_metric: Decimal
    calculated_at: datetime
    source: str
    completeness_status: Literal["COMPLETE", "INCOMPLETE"]
    sessions_observed: int
    sessions_expected: int
    supported_leveraged_products: int


class PopularData(BaseModel):
    ranking_period: str
    period_status: Literal["SEPTEMBER_TO_DATE", "MONTH_TO_DATE", "FINAL"]
    ranking_type: Literal["DOLLAR_TRADING_VOLUME"]
    population_status: Literal["COMPLETE", "PARTIAL", "NOT_POPULATED"]
    rows: List[PopularRowSchema]


class PopularResponse(BaseModel):
    data: PopularData
    meta: ResponseMeta


class MultiCalculationRequest(BaseModel):
    target_price: Decimal

    @field_validator("target_price", mode="before")
    @classmethod
    def require_target_decimal_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("target_price must be a decimal string")
        return value


class MultiCalculationRowSchema(BaseModel):
    relationship: RelationshipSchema
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    anchor: Optional[DailyCloseAnchorSchema]
    theoretical_target_price: Optional[Decimal]
    underlying_return: Optional[Decimal]
    leveraged_return: Optional[Decimal]
    message: str


class MultiCalculationData(BaseModel):
    underlying: InstrumentSchema
    target_price: Decimal
    rows: List[MultiCalculationRowSchema]
    formula_version: Literal["leveraged-daily-close-linear/v2"]


class MultiCalculationResponse(BaseModel):
    data: MultiCalculationData
    meta: ResponseMeta


class MethodologySchema(FromDomainModel):
    id: str
    version: str
    display_name: str


class ProfitRatioPointSchema(FromDomainModel):
    timestamp: datetime
    trading_date: date
    ratio: Decimal
    quality: str


class PricePointSchema(FromDomainModel):
    timestamp: datetime
    trading_date: date
    close: Decimal
    adjustment: str


class ProfitRatioLatestData(BaseModel):
    instrument: InstrumentSchema
    ratio: Decimal
    observed_at: datetime
    trading_date: date
    freshness: str
    methodology: MethodologySchema
    provider: str


class ProfitRatioLatestResponse(BaseModel):
    data: ProfitRatioLatestData
    meta: ResponseMeta


class ProfitRatioHistoryData(BaseModel):
    instrument_id: str
    symbol: str
    interval: str
    timezone: str
    methodology: MethodologySchema
    profit_ratio_series: List[ProfitRatioPointSchema]
    price_series: List[PricePointSchema]
    gaps: List[str]
    as_of: datetime
    provider: str


class ProfitRatioHistoryResponse(BaseModel):
    data: ProfitRatioHistoryData
    meta: ResponseMeta


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    market_data_provider: Literal["mock"]

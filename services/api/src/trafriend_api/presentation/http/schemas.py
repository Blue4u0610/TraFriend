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


class RelationshipSchema(FromDomainModel):
    id: str
    underlying: InstrumentSchema
    leveraged_product: InstrumentSchema
    leverage_factor: Decimal
    objective_period: Literal["daily"]
    effective_from: date
    effective_to: Optional[date] = None


class ReferencePriceSchema(FromDomainModel):
    instrument_id: str
    symbol: str
    price: Decimal
    quoted_at: datetime


class DailyReferenceSetSchema(FromDomainModel):
    id: str
    relationship_id: str
    trading_date: date
    session: str
    status: Literal["active"]
    version: int
    underlying: ReferencePriceSchema
    leveraged_product: ReferencePriceSchema
    captured_at: datetime
    provider: Literal["mock"]
    freshness: Literal["current", "stale", "unknown"]


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


class DailyReferenceResponse(BaseModel):
    data: DailyReferenceSetSchema
    meta: ResponseMeta


class CalculationRequest(BaseModel):
    relationship_id: str
    reference_version_id: str
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


class CalculationReferenceSchema(BaseModel):
    id: str
    trading_date: date
    session: str
    underlying_price: Decimal
    leveraged_product_price: Decimal
    underlying_quoted_at: datetime
    leveraged_product_quoted_at: datetime
    provider: str


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
    reference: CalculationReferenceSchema
    calculated_at: datetime
    warnings: List[WarningSchema]


class CalculationResponse(BaseModel):
    data: CalculationData
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


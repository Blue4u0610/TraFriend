from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Tuple


@dataclass(frozen=True)
class InstrumentCapabilities:
    leveraged_relationships: bool
    profit_ratio: bool


@dataclass(frozen=True)
class Instrument:
    id: str
    symbol: str
    name: str
    instrument_type: str
    exchange_mic: str
    currency: str
    status: str
    capabilities: InstrumentCapabilities
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class LeveragedRelationship:
    id: str
    underlying: Instrument
    leveraged_product: Instrument
    leverage_factor: Decimal
    objective_period: str
    effective_from: date
    effective_to: Optional[date] = None
    issuer: Optional[str] = None
    direction: Optional[str] = None
    status: str = "active"
    authoritative_source: Optional[str] = None
    verified_at: Optional[datetime] = None


@dataclass(frozen=True)
class ProfitRatioMethodology:
    id: str
    version: str
    display_name: str


@dataclass(frozen=True)
class ProfitRatioPoint:
    timestamp: datetime
    trading_date: date
    ratio: Decimal
    quality: str


@dataclass(frozen=True)
class PricePoint:
    timestamp: datetime
    trading_date: date
    close: Decimal
    adjustment: str


@dataclass(frozen=True)
class ProfitRatioHistory:
    instrument: Instrument
    methodology: ProfitRatioMethodology
    ratio_points: Tuple[ProfitRatioPoint, ...]
    price_points: Tuple[PricePoint, ...]
    provider: str
    as_of: datetime


@dataclass(frozen=True)
class CalculationResult:
    input_side: str
    input_target_price: Decimal
    output_side: str
    theoretical_target_price: Decimal
    underlying_return: Decimal
    leveraged_return: Decimal
    formula_version: str = "leveraged-daily-close-linear/v2"

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from trafriend_api.infrastructure.persistence.models import Base


class QqqConstituentRecord(Base):
    __tablename__ = "qqq_constituent_snapshots"
    instrument_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(500))
    __table_args__ = (UniqueConstraint("as_of", "symbol"),)


class ProfitRatioPriceRecord(Base):
    __tablename__ = "profit_ratio_capture_prices"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(100), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    phase: Mapped[str] = mapped_column(String(8))
    price: Mapped[Decimal] = mapped_column(Numeric())
    previous_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(), nullable=True)
    market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(50))
    source_feed: Mapped[str] = mapped_column(String(50))
    methodology_key: Mapped[str] = mapped_column(String(100), default="CHIP_TURNOVER")
    methodology_version: Mapped[str] = mapped_column(String(20), default="1")
    currency: Mapped[str] = mapped_column(String(3))
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trading_date",
            "phase",
            "methodology_key",
            "methodology_version",
        ),
        CheckConstraint("phase IN ('OPEN', 'CLOSE')"),
        CheckConstraint("price > 0 AND price < 10000000000000000"),
        CheckConstraint(
            "previous_close IS NULL OR (previous_close > 0 AND previous_close < 10000000000000000)"
        ),
        CheckConstraint("market_timestamp <= observed_at"),
        CheckConstraint("currency = 'USD'"),
    )


class ProfitRatioObservationRecord(Base):
    __tablename__ = "profit_ratio_observations"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    price_id: Mapped[str] = mapped_column(ForeignKey("profit_ratio_capture_prices.id"))
    instrument_id: Mapped[str] = mapped_column(String(100), index=True)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    phase: Mapped[str] = mapped_column(String(8))
    ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str] = mapped_column(String(100))
    methodology_key: Mapped[str] = mapped_column(String(100))
    methodology_version: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trading_date",
            "phase",
            "methodology_key",
            "methodology_version",
            "version",
        ),
        CheckConstraint("phase IN ('OPEN', 'CLOSE')"),
        CheckConstraint("version > 0"),
        CheckConstraint("ratio IS NULL OR (ratio >= 0 AND ratio <= 1)"),
        CheckConstraint(
            "(status = 'DATA_INSUFFICIENT' AND ratio IS NULL) OR "
            "(status IN ('ESTIMATED', 'REPORTED') AND ratio IS NOT NULL)"
        ),
    )


class ProfitRatioDailyObservationRecord(Base):
    __tablename__ = "profit_ratio_daily_observations"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(100), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    ratio: Mapped[Decimal] = mapped_column(Numeric())
    time_basis: Mapped[str] = mapped_column(String(40))
    market_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(50))
    source_feed: Mapped[str] = mapped_column(String(100))
    quality: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    reason_code: Mapped[str] = mapped_column(String(100))
    methodology_key: Mapped[str] = mapped_column(String(100))
    methodology_version: Mapped[str] = mapped_column(String(20))
    source_note: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "trading_date",
            "methodology_key",
            "methodology_version",
            "time_basis",
            "version",
            name="uq_profit_ratio_daily_observation_version",
        ),
        CheckConstraint("ratio >= 0 AND ratio <= 1"),
        CheckConstraint(
            "time_basis IN ('CLOSE', 'DAILY_TIME_UNVERIFIED')",
            name="ck_profit_ratio_daily_time_basis",
        ),
        CheckConstraint(
            "(time_basis = 'CLOSE' AND market_timestamp IS NOT NULL) OR "
            "(time_basis = 'DAILY_TIME_UNVERIFIED' AND market_timestamp IS NULL)",
            name="ck_profit_ratio_daily_market_timestamp",
        ),
        CheckConstraint("status = 'REPORTED'"),
        CheckConstraint("version > 0"),
        CheckConstraint("market_timestamp IS NULL OR market_timestamp <= observed_at"),
    )

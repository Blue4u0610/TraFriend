from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DailyCloseAnchorRecord(Base):
    __tablename__ = "daily_close_anchors"
    __table_args__ = (
        UniqueConstraint(
            "underlying_symbol",
            "leveraged_product_symbol",
            "trading_date",
            name="uq_daily_close_anchor_logical_identity",
        ),
        UniqueConstraint(
            "relationship_id",
            "trading_date",
            name="uq_daily_close_anchor_relationship_date",
        ),
        UniqueConstraint(
            "relationship_id",
            "version",
            name="uq_daily_close_anchor_relationship_version",
        ),
        CheckConstraint("version > 0", name="ck_daily_close_anchor_version_positive"),
        CheckConstraint(
            "signed_leverage <> 0",
            name="ck_daily_close_anchor_leverage_nonzero",
        ),
        CheckConstraint(
            "underlying_close > 0 AND leveraged_product_close > 0",
            name="ck_daily_close_anchor_prices_positive",
        ),
        CheckConstraint(
            "underlying_trading_date = trading_date "
            "AND leveraged_product_trading_date = trading_date",
            name="ck_daily_close_anchor_same_date",
        ),
        CheckConstraint(
            "underlying_symbol <> leveraged_product_symbol",
            name="ck_daily_close_anchor_symbols_differ",
        ),
        CheckConstraint(
            "status = 'COMPLETE'",
            name="ck_daily_close_anchor_complete_only",
        ),
        CheckConstraint(
            "anchor_type = 'DAILY_CLOSE_ANCHOR'",
            name="ck_daily_close_anchor_type",
        ),
        CheckConstraint(
            "underlying_currency = 'USD' AND leveraged_product_currency = 'USD'",
            name="ck_daily_close_anchor_usd",
        ),
        CheckConstraint(
            "session_closed_at <= captured_at",
            name="ck_daily_close_anchor_session_complete",
        ),
        Index(
            "ix_daily_close_anchors_relationship_latest",
            "relationship_id",
            "trading_date",
            "version",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    relationship_id: Mapped[str] = mapped_column(String(128), nullable=False)
    underlying_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    leveraged_product_symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    signed_leverage: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    underlying_trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    leveraged_product_trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    session_closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    underlying_close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    leveraged_product_close: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source_feed: Mapped[str] = mapped_column(String(64), nullable=False)
    underlying_market_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    leveraged_product_market_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    underlying_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    leveraged_product_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    underlying_quality: Mapped[str] = mapped_column(String(16), nullable=False)
    leveraged_product_quality: Mapped[str] = mapped_column(String(16), nullable=False)
    underlying_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    leveraged_product_currency: Mapped[str] = mapped_column(
        String(3), nullable=False
    )
    underlying_message: Mapped[str] = mapped_column(String(512), nullable=False)
    leveraged_product_message: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    anchor_type: Mapped[str] = mapped_column(String(32), nullable=False)


class UnderlyingRecord(Base):
    __tablename__ = "underlyings"
    __table_args__ = (
        CheckConstraint("symbol = UPPER(symbol)", name="ck_underlying_symbol_upper"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(32), nullable=False)
    exchange_mic: Mapped[str] = mapped_column(String(8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    profit_ratio_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class LeveragedProductRecord(Base):
    __tablename__ = "leveraged_products"
    __table_args__ = (
        CheckConstraint("symbol = UPPER(symbol)", name="ck_leveraged_symbol_upper"),
        CheckConstraint(
            "signed_leverage <> 0", name="ck_leveraged_product_leverage_nonzero"
        ),
        CheckConstraint(
            "direction IN ('LONG', 'INVERSE')",
            name="ck_leveraged_product_direction",
        ),
        CheckConstraint(
            "(direction = 'LONG' AND signed_leverage > 0) OR "
            "(direction = 'INVERSE' AND signed_leverage < 0)",
            name="ck_leveraged_product_direction_matches_leverage",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    relationship_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    exchange_mic: Mapped[str] = mapped_column(String(8), nullable=False)
    underlying_id: Mapped[str] = mapped_column(
        ForeignKey("underlyings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    signed_leverage: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    issuer: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    objective_period: Mapped[str] = mapped_column(String(16), nullable=False)
    authoritative_source: Mapped[str] = mapped_column(String(1024), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class MarketRankingRecord(Base):
    __tablename__ = "market_rankings"
    __table_args__ = (
        UniqueConstraint(
            "ranking_period",
            "ranking_type",
            "rank",
            name="uq_market_ranking_period_type_rank",
        ),
        UniqueConstraint(
            "ranking_period",
            "ranking_type",
            "symbol",
            name="uq_market_ranking_period_type_symbol",
        ),
        CheckConstraint("rank BETWEEN 1 AND 100", name="ck_market_ranking_rank"),
        CheckConstraint(
            "trading_metric >= 0", name="ck_market_ranking_metric_nonnegative"
        ),
        CheckConstraint(
            "period_status IN ('SEPTEMBER_TO_DATE', 'MONTH_TO_DATE', 'FINAL')",
            name="ck_market_ranking_period_status",
        ),
        CheckConstraint(
            "completeness_status IN ('COMPLETE', 'INCOMPLETE')",
            name="ck_market_ranking_completeness_status",
        ),
        CheckConstraint(
            "sessions_observed >= 0 AND sessions_expected >= 0 "
            "AND sessions_observed <= sessions_expected",
            name="ck_market_ranking_session_counts",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ranking_period: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_status: Mapped[str] = mapped_column(String(32), nullable=False)
    ranking_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), nullable=False)
    trading_metric: Mapped[Decimal] = mapped_column(Numeric(30, 4), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    completeness_status: Mapped[str] = mapped_column(String(16), nullable=False)
    sessions_observed: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_expected: Mapped[int] = mapped_column(Integer, nullable=False)

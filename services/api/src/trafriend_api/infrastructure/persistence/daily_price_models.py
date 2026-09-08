from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trafriend_api.infrastructure.persistence.models import Base


class DailyPriceBarRecord(Base):
    __tablename__ = "market_daily_price_bars"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(100), index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric())
    high: Mapped[Decimal] = mapped_column(Numeric())
    low: Mapped[Decimal] = mapped_column(Numeric())
    close: Mapped[Decimal] = mapped_column(Numeric())
    previous_close: Mapped[Optional[Decimal]] = mapped_column(Numeric(), nullable=True)
    session_opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    session_closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(50))
    source_feed: Mapped[str] = mapped_column(String(50))
    quality: Mapped[str] = mapped_column(String(40))
    currency: Mapped[str] = mapped_column(String(3))
    adjustment: Mapped[str] = mapped_column(String(20))
    price_scope: Mapped[str] = mapped_column(String(60))
    __table_args__ = (
        UniqueConstraint("instrument_id", "trading_date"),
        CheckConstraint('"low" > 0 AND "high" < 10000000000000000'),
        CheckConstraint(
            '"low" <= "open" AND "low" <= "close" AND "high" >= "open" AND "high" >= "close"'
        ),
        CheckConstraint(
            "previous_close IS NULL OR (previous_close > 0 AND previous_close < 10000000000000000)"
        ),
        CheckConstraint(
            "market_timestamp <= session_opened_at AND session_opened_at < session_closed_at "
            "AND session_closed_at <= observed_at"
        ),
        CheckConstraint("currency = 'USD' AND adjustment = 'raw'"),
        CheckConstraint("quality IN ('REALTIME', 'DELAYED', 'MOCK')"),
        CheckConstraint("price_scope = 'CONSOLIDATED_DAILY_ELIGIBLE_TRADES'"),
    )

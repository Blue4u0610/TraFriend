"""Explicit, credential-free endpoint examples; never seed PostgreSQL with these."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioObservation,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioRecord,
    ProfitRatioStatus,
)
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)


def build_mock_profit_ratio_repository() -> InMemoryProfitRatioRepository:
    """Synthetic fixture values demonstrate UI states, not validated market estimates."""

    trading_date = date(2026, 9, 4)
    fixtures = (
        ("NVDA", "NVIDIA Corporation", "168.37", "170", "168.37", "0.771", "0.826"),
        ("AAPL", "Apple Inc.", "230", "227.5", "230", "0.68", "0.65"),
        ("TSLA", "Tesla, Inc.", "400", "420", "400", "0.55", "0.7"),
    )
    members = tuple(
        NasdaqConstituent(
            instrument_id=f"ins_{symbol.lower()}_xnas",
            symbol=symbol,
            name=name,
            as_of=trading_date,
            source="MOCK_NASDAQ_FIXTURE",
        )
        for symbol, name, *_values in fixtures
    )
    repository = InMemoryProfitRatioRepository(members)
    for member, (_symbol, _name, opening, closing, previous, open_ratio, close_ratio) in zip(
        members, fixtures
    ):
        for phase, amount, ratio, hour, minute in (
            (ProfitRatioPhase.OPEN, opening, open_ratio, 13, 30),
            (ProfitRatioPhase.CLOSE, closing, close_ratio, 20, 0),
        ):
            timestamp = datetime(2026, 9, 4, hour, minute, tzinfo=timezone.utc)
            price = ProfitRatioPriceObservation(
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                trading_date=trading_date,
                phase=phase,
                price=Decimal(amount),
                previous_close=Decimal(previous),
                market_timestamp=timestamp,
                observed_at=timestamp + timedelta(minutes=20),
                provider="mock",
                source_feed="MOCK_NASDAQ_FIXTURE",
            )
            observation = ProfitRatioObservation(
                id=f"mock-{member.symbol}-{trading_date}-{phase.value}",
                instrument_id=member.instrument_id,
                symbol=member.symbol,
                trading_date=trading_date,
                phase=phase,
                ratio=Decimal(ratio),
                market_timestamp=timestamp,
                observed_at=price.observed_at,
                provider="mock",
                source_feed=price.source_feed,
                quality="MOCK",
                status=ProfitRatioStatus.ESTIMATED,
                reason_code="",
            )
            repository.save(ProfitRatioRecord(observation, price))
    return repository

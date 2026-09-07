from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

import pytest

from trafriend_api.application.ports.daily_close import DailyCloseMarketDataProvider
from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.market_data import MarketDataService
from trafriend_api.domain.daily_close import (
    DailyCloseAnchorStatus,
    DailyCloseBar,
    DailyCloseQuality,
    DailyCloseValueStatus,
)
from trafriend_api.domain.errors import AnchorConflictError, AnchorUnavailableError
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryDailyCloseAnchorRepository

UTC = timezone.utc
NOW = datetime(2026, 9, 4, 21, tzinfo=UTC)


def _service(scenario: str = "normal") -> DailyCloseAnchorService:
    provider = MockMarketDataProvider(scenario, now=lambda: NOW)
    return DailyCloseAnchorService(
        provider=provider,
        calendar=NyseTradingCalendar(),
        repository=InMemoryDailyCloseAnchorRepository(),
        now=lambda: NOW,
    )


def test_capture_accepts_same_date_completed_close_pair() -> None:
    anchor = _service().capture("rel", "QQQ", "TQQQ", Decimal("3"))

    assert anchor.status == DailyCloseAnchorStatus.COMPLETE
    assert anchor.trading_date == date(2026, 9, 4)
    assert anchor.underlying.close == Decimal("480.00")
    assert anchor.leveraged_product.close == Decimal("82.50")
    assert anchor.underlying.status == DailyCloseValueStatus.AVAILABLE
    assert anchor.leveraged_product.status == DailyCloseValueStatus.AVAILABLE
    assert anchor.session_closed_at == datetime(2026, 9, 4, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("scenario", "expected_status", "underlying_status", "leveraged_status"),
    [
        (
            "partial",
            DailyCloseAnchorStatus.PARTIAL,
            DailyCloseValueStatus.AVAILABLE,
            DailyCloseValueStatus.MISSING,
        ),
        (
            "missing_underlying",
            DailyCloseAnchorStatus.PARTIAL,
            DailyCloseValueStatus.MISSING,
            DailyCloseValueStatus.AVAILABLE,
        ),
        (
            "missing",
            DailyCloseAnchorStatus.UNAVAILABLE,
            DailyCloseValueStatus.MISSING,
            DailyCloseValueStatus.MISSING,
        ),
        (
            "provider_failure",
            DailyCloseAnchorStatus.UNAVAILABLE,
            DailyCloseValueStatus.MISSING,
            DailyCloseValueStatus.MISSING,
        ),
    ],
)
def test_capture_never_publishes_missing_or_partial_pair(
    scenario: str,
    expected_status: DailyCloseAnchorStatus,
    underlying_status: DailyCloseValueStatus,
    leveraged_status: DailyCloseValueStatus,
) -> None:
    anchor = _service(scenario).capture(
        "rel", "QQQ", "TQQQ", Decimal("3")
    )

    assert anchor.status == expected_status
    assert anchor.underlying.status == underlying_status
    assert anchor.leveraged_product.status == leveraged_status


@pytest.mark.parametrize("scenario", ["partial", "missing_underlying"])
def test_missing_either_anchor_member_cannot_calculate(scenario: str) -> None:
    provider = MockMarketDataProvider(scenario, now=lambda: NOW)
    anchor_service = DailyCloseAnchorService(
        provider=provider,
        calendar=NyseTradingCalendar(),
        repository=InMemoryDailyCloseAnchorRepository(),
        now=lambda: NOW,
    )
    anchor = anchor_service.capture(
        "rel_qqq_tqqq_3x", "QQQ", "TQQQ", Decimal("3")
    )
    calculator = MarketDataService(provider, anchor_service, provider)

    with pytest.raises(AnchorUnavailableError):
        calculator.calculate(
            relationship_id="rel_qqq_tqqq_3x",
            anchor_version_id=anchor.id,
            input_side="underlying",
            target_price=Decimal("500"),
        )


def test_provider_lag_does_not_fall_back_to_prior_trading_date() -> None:
    anchor = _service("stale").capture(
        "rel", "QQQ", "TQQQ", Decimal("3")
    )

    assert anchor.status == DailyCloseAnchorStatus.UNAVAILABLE
    assert anchor.underlying.status == DailyCloseValueStatus.REJECTED
    assert anchor.underlying.trading_date == date(2026, 9, 3)
    assert anchor.trading_date == date(2026, 9, 4)


class MismatchedDateProvider(DailyCloseMarketDataProvider):
    @property
    def provider_code(self) -> str:
        return "test"

    @property
    def daily_close_feed(self) -> str:
        return "test-feed"

    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        return tuple(
            DailyCloseBar(
                symbol=symbol,
                trading_date=end if index == 0 else end - timedelta(days=1),
                close=Decimal("100") + index,
                market_timestamp=datetime(2026, 9, 4 - index, 4, tzinfo=UTC),
                observed_at=NOW,
                source=self.provider_code,
                source_feed=self.daily_close_feed,
                currency="USD",
                quality=DailyCloseQuality.DELAYED,
            )
            for index, symbol in enumerate(symbols)
        )


def test_capture_rejects_mismatched_member_dates() -> None:
    service = DailyCloseAnchorService(
        provider=MismatchedDateProvider(),
        calendar=NyseTradingCalendar(),
        repository=InMemoryDailyCloseAnchorRepository(),
        now=lambda: NOW,
    )

    anchor = service.capture("rel", "QQQ", "TQQQ", Decimal("3"))

    assert anchor.status == DailyCloseAnchorStatus.PARTIAL
    assert anchor.underlying.status == DailyCloseValueStatus.AVAILABLE
    assert anchor.leveraged_product.status == DailyCloseValueStatus.REJECTED


def test_repository_versions_are_immutable_and_missing_latest_is_explicit() -> None:
    repository = InMemoryDailyCloseAnchorRepository()
    with pytest.raises(AnchorUnavailableError):
        repository.latest("missing")

    provider = MockMarketDataProvider(now=lambda: NOW)
    service = DailyCloseAnchorService(
        provider=provider,
        calendar=NyseTradingCalendar(),
        repository=repository,
        now=lambda: NOW,
    )
    first = service.capture("rel", "QQQ", "TQQQ", Decimal("3"))
    second = service.capture("rel", "QQQ", "TQQQ", Decimal("3"))

    assert first.version == 1
    assert second.version == 1
    assert first.id == second.id
    assert service.latest("rel") == first


def test_conflicting_recapture_is_explicit_and_does_not_overwrite() -> None:
    repository = InMemoryDailyCloseAnchorRepository()
    service = DailyCloseAnchorService(
        provider=MockMarketDataProvider(now=lambda: NOW),
        calendar=NyseTradingCalendar(),
        repository=repository,
        now=lambda: NOW,
    )
    stored = service.capture("rel", "QQQ", "TQQQ", Decimal("3"))
    assert stored.underlying.close is not None
    conflicting = replace(
        stored,
        id="pending",
        version=0,
        underlying=replace(
            stored.underlying,
            close=stored.underlying.close + Decimal("0.01"),
        ),
    )

    with pytest.raises(AnchorConflictError, match="conflicting immutable"):
        repository.save(conflicting)

    assert repository.latest("rel") == stored


def test_incomplete_capture_is_not_persisted() -> None:
    repository = InMemoryDailyCloseAnchorRepository()
    service = DailyCloseAnchorService(
        provider=MockMarketDataProvider("partial", now=lambda: NOW),
        calendar=NyseTradingCalendar(),
        repository=repository,
        now=lambda: NOW,
    )

    captured = service.capture("rel", "QQQ", "TQQQ", Decimal("3"))

    assert captured.status == DailyCloseAnchorStatus.PARTIAL
    with pytest.raises(AnchorUnavailableError):
        repository.latest("rel")


def test_latest_never_falls_back_to_an_older_completed_session() -> None:
    current = [datetime(2026, 9, 3, 21, tzinfo=UTC)]
    repository = InMemoryDailyCloseAnchorRepository()
    service = DailyCloseAnchorService(
        provider=MockMarketDataProvider(now=lambda: current[0]),
        calendar=NyseTradingCalendar(),
        repository=repository,
        now=lambda: current[0],
    )
    service.capture("rel", "QQQ", "TQQQ", Decimal("3"))
    current[0] = NOW

    with pytest.raises(AnchorUnavailableError, match="latest completed session"):
        service.latest("rel")

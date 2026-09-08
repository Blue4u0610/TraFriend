from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

import pytest
from fastapi.testclient import TestClient

from trafriend_api.application.ports.daily_price import DailyPriceProvider
from trafriend_api.application.services.daily_price import DailyPriceCaptureService
from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.domain.daily_price import DailyPriceBar, DailyPriceConflictError
from trafriend_api.domain.errors import MarketDataProviderError, ResourceNotFoundError
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent, ProfitRatioSession
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.market_data.mock.daily_price import (
    MockDailyPriceProvider,
    build_mock_daily_price_repository,
    mock_daily_price_bars,
)
from trafriend_api.infrastructure.persistence.daily_price import InMemoryDailyPriceRepository
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)
from trafriend_api.main import create_app
from trafriend_api.settings import Settings

DAY = date(2026, 9, 4)
NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
BAR = mock_daily_price_bars()[0]
MEMBER = NasdaqConstituent(BAR.instrument_id, BAR.symbol, "NVIDIA", DAY, "MOCK_NASDAQ_FIXTURE")
SECOND = NasdaqConstituent("ins_aapl_xnas", "AAPL", "Apple", DAY, "MOCK_NASDAQ_FIXTURE")


class Provider(DailyPriceProvider):
    def __init__(self, bars: Sequence[DailyPriceBar] = (BAR,)) -> None:
        self.bars = bars
        self.calls: list[tuple[str, ...]] = []
        self.fail = False

    def get_daily_price_bars(
        self, symbols: Sequence[str], sessions: Sequence[ProfitRatioSession]
    ) -> Sequence[DailyPriceBar]:
        self.calls.append(tuple(symbols))
        if self.fail:
            raise MarketDataProviderError("synthetic failure")
        return self.bars


def test_daily_candles_work_without_any_ratio_records_or_model_inputs() -> None:
    ratios = InMemoryProfitRatioRepository((MEMBER,))
    prices = InMemoryDailyPriceRepository((BAR,))
    service = ProfitRatioService(
        ratios, ProfitRatioExchangeCalendar(), now=lambda: NOW, price_repository=prices
    )
    assert service.search("nvda") == (MEMBER,)
    history = service.daily("NVDA", DAY, DAY)
    row = history.rows[0]
    assert row.price_status == "COMPLETE"
    assert (row.open_price, row.high_price, row.low_price, row.close_price) == (
        BAR.open,
        BAR.high,
        BAR.low,
        BAR.close,
    )
    assert row.price_change_return == BAR.price_change_return
    assert row.open_ratio is None and row.close_ratio is None
    assert row.price_provider == "mock" and row.price_quality == "MOCK"
    assert row.price_scope == "CONSOLIDATED_DAILY_ELIGIBLE_TRADES"
    assert row.price_market_timestamp == BAR.market_timestamp
    assert ratios.history(MEMBER.instrument_id, DAY, DAY) == ()


def test_daily_price_api_decimals_and_utc_provenance_without_provider_reads() -> None:
    app = create_app(Settings())
    repository = InMemoryProfitRatioRepository((MEMBER,))
    app.state.profit_ratio_service = ProfitRatioService(
        repository,
        ProfitRatioExchangeCalendar(),
        now=lambda: NOW,
        price_repository=InMemoryDailyPriceRepository((BAR,)),
    )
    with TestClient(app) as client:
        response = client.get(f"/api/v1/profit-ratio/symbols/NVDA/daily?start={DAY}&end={DAY}")
        assert response.status_code == 200
        row = response.json()["data"]["rows"][0]
    assert row["high_price"] == "173"
    assert row["low_price"] == "167.4"
    assert row["price_market_timestamp"] == "2026-09-04T04:00:00Z"
    assert row["price_observed_at"] == "2026-09-04T20:20:00Z"
    assert row["open_ratio"] is None and row["close_ratio"] is None


def test_daily_capture_independent_of_ratio_availability_and_idempotent() -> None:
    ratios = InMemoryProfitRatioRepository((MEMBER,))
    prices = InMemoryDailyPriceRepository()
    provider = Provider()
    service = DailyPriceCaptureService(
        ratios, prices, provider, ProfitRatioExchangeCalendar(), now=lambda: NOW
    )
    first = service.capture(DAY, DAY)
    second = service.capture(DAY, DAY)
    assert first.status == "COMPLETE" and first.inserted == 1
    assert second.status == "COMPLETE" and second.existing == 1 and second.inserted == 0
    assert provider.calls == [("NVDA",)]
    assert ratios.history(MEMBER.instrument_id, DAY, DAY) == ()


def test_partial_batch_persists_valid_stock_and_retries_only_missing_stock() -> None:
    catalog = InMemoryProfitRatioRepository((MEMBER, SECOND))
    prices = InMemoryDailyPriceRepository()
    provider = Provider()
    service = DailyPriceCaptureService(
        catalog, prices, provider, ProfitRatioExchangeCalendar(), now=lambda: NOW
    )
    first = service.capture(DAY, DAY)
    assert first.status == "PARTIAL_RETRYABLE" and first.inserted == 1 and first.unavailable == 1
    provider.bars = (mock_daily_price_bars()[1],)
    second = service.capture(DAY, DAY)
    assert second.status == "COMPLETE" and second.inserted == 1 and second.existing == 1
    assert provider.calls == [("AAPL", "NVDA"), ("AAPL",)]


def test_provider_failure_keeps_existing_candles_and_does_not_fabricate_missing() -> None:
    catalog = InMemoryProfitRatioRepository((MEMBER, SECOND))
    prices = InMemoryDailyPriceRepository((BAR,))
    provider = Provider()
    provider.fail = True
    result = DailyPriceCaptureService(
        catalog, prices, provider, ProfitRatioExchangeCalendar(), now=lambda: NOW
    ).capture(DAY, DAY)
    assert result.status == "PARTIAL_RETRYABLE" and result.existing == 1
    assert result.unavailable == 1 and prices.get(SECOND.instrument_id, DAY) is None


def test_no_completed_session_means_no_provider_call_or_intraday_fake_candle() -> None:
    provider = Provider()
    service = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        provider,
        ProfitRatioExchangeCalendar(),
        now=lambda: datetime(2026, 9, 4, 20, 19, tzinfo=timezone.utc),
    )
    report = service.capture(DAY, DAY)
    assert report.status == "NOT_DUE" and provider.calls == []


def test_early_close_and_daylight_saving_use_calendar_not_hardcoded_utc() -> None:
    calendar = ProfitRatioExchangeCalendar()
    summer = calendar.session(date(2026, 9, 4))
    winter = calendar.session(date(2026, 11, 30))
    shortened = calendar.session(date(2026, 11, 27))
    assert summer.closed_at.hour == 20 and winter.closed_at.hour == 21
    assert shortened.closed_at.hour == 18
    provider = Provider(())
    report = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        provider,
        calendar,
        now=lambda: shortened.closed_at + timedelta(minutes=20),
    ).capture(shortened.trading_date, shortened.trading_date)
    assert report.sessions == 1 and provider.calls == [("NVDA",)]


def test_weekend_and_holiday_add_no_candles() -> None:
    provider = Provider(())
    report = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        provider,
        ProfitRatioExchangeCalendar(),
        now=lambda: NOW,
    ).capture(date(2026, 9, 5), date(2026, 9, 7))
    assert report.status == "NOT_DUE" and provider.calls == []


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e16"])
def test_daily_bar_requires_positive_finite_bounded_prices(value: str) -> None:
    with pytest.raises(ValueError):
        replace(BAR, low=Decimal(value))


@pytest.mark.parametrize(
    "changes",
    [
        {"high": Decimal("169")},
        {"low": Decimal("169")},
        {"observed_at": BAR.session_closed_at - timedelta(seconds=1)},
        {"market_timestamp": BAR.market_timestamp.replace(tzinfo=None)},
        {"quality": "STALE"},
        {"adjustment": "all"},
    ],
)
def test_invalid_ohlc_or_provenance_cannot_become_complete_bar(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(BAR, **changes)


def test_missing_previous_close_preserves_candles_without_fabricating_return() -> None:
    assert replace(BAR, previous_close=None).price_change_return is None


def test_identical_price_retry_ignores_capture_time_but_conflict_is_explicit() -> None:
    repository = InMemoryDailyPriceRepository()
    first = repository.save(BAR)
    second = repository.save(replace(BAR, id="retry", observed_at=NOW))
    assert first.outcome == "INSERTED" and second.outcome == "EXISTING"
    assert second.bar.id == BAR.id
    with pytest.raises(DailyPriceConflictError):
        repository.save(replace(BAR, high=Decimal("174")))
    assert repository.get(BAR.instrument_id, DAY) == BAR


@pytest.mark.parametrize(
    "changes",
    [
        {"market_timestamp": BAR.market_timestamp + timedelta(minutes=1)},
        {"source_feed": "iex", "provider": "alpaca"},
        {"symbol": "DIFFERENT"},
        {"observed_at": NOW + timedelta(seconds=1)},
    ],
)
def test_capture_rejects_wrong_daily_source_or_observation(changes: dict[str, object]) -> None:
    provider = Provider((replace(BAR, **changes),))
    result = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        provider,
        ProfitRatioExchangeCalendar(),
        now=lambda: NOW,
    ).capture(DAY, DAY)
    assert result.unavailable == 1 and result.inserted == 0


def test_missing_prior_session_is_not_replaced_with_older_daily_bar() -> None:
    previous = replace(BAR, trading_date=date(2026, 9, 3))
    result = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        Provider((previous,)),
        ProfitRatioExchangeCalendar(),
        now=lambda: NOW,
    ).capture(DAY, DAY)
    assert result.unavailable == 1 and result.inserted == 0


def test_mock_ohlc_contract_and_deterministic_source_are_explicit() -> None:
    provider = MockDailyPriceProvider()
    bars = provider.get_daily_price_bars(["NVDA"], [ProfitRatioExchangeCalendar().session(DAY)])
    assert bars == (BAR,)
    assert bars[0].provider == "mock" and bars[0].quality == "MOCK"
    assert build_mock_daily_price_repository().get(MEMBER.instrument_id, DAY) == BAR


def test_capture_invalid_range_or_unsupported_stock_does_not_call_provider() -> None:
    provider = Provider()
    service = DailyPriceCaptureService(
        InMemoryProfitRatioRepository((MEMBER,)),
        InMemoryDailyPriceRepository(),
        provider,
        ProfitRatioExchangeCalendar(),
        now=lambda: NOW,
    )
    with pytest.raises(ResourceNotFoundError):
        service.capture(DAY, DAY, ["UNKNOWN"])
    for start, end in (
        (DAY, DAY - timedelta(days=1)),
        (DAY, DAY + timedelta(days=200)),
        (DAY, NOW.date() + timedelta(days=1)),
    ):
        with pytest.raises(ValueError):
            service.capture(start, end)
    assert provider.calls == []

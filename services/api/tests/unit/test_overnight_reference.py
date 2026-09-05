from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from trafriend_api.application.ports.overnight_market_data import TradingCalendar
from trafriend_api.application.services.overnight_reference import (
    EASTERN,
    OvernightReferenceService,
)
from trafriend_api.domain.errors import OvernightSessionError
from trafriend_api.domain.overnight import (
    CaptureStatus,
    DataQuality,
    OvernightBar,
    ReferenceStatus,
)
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryOvernightReferenceRepository

UTC = timezone.utc
TRADING_DATE = date(2026, 9, 8)


class FixedCalendar(TradingCalendar):
    def __init__(self, closed=()) -> None:
        self._closed = set(closed)

    def is_trading_day(self, trading_date: date) -> bool:
        return trading_date.weekday() < 5 and trading_date not in self._closed


def build_service(scenario="normal", calendar=None):
    provider = MockMarketDataProvider(scenario)
    repository = InMemoryOvernightReferenceRepository()
    service = OvernightReferenceService(
        provider,
        calendar or FixedCalendar(),
        repository,
        now=lambda: datetime(2026, 9, 8, 0, 5, 30, tzinfo=UTC),
    )
    return service, provider, repository


def test_sunday_night_maps_to_monday_trading_date() -> None:
    service, _, _ = build_service()
    sunday_night = datetime(2026, 9, 13, 20, 0, tzinfo=EASTERN)

    assert service.trading_date_for(sunday_night) == date(2026, 9, 14)


def test_timestamp_outside_overnight_session_is_rejected() -> None:
    service, _, _ = build_service()

    with pytest.raises(OvernightSessionError):
        service.trading_date_for(datetime(2026, 9, 8, 12, 0, tzinfo=EASTERN))


def test_non_trading_day_has_no_session() -> None:
    service, _, _ = build_service(calendar=FixedCalendar({date(2026, 9, 7)}))

    with pytest.raises(OvernightSessionError):
        service.session_window(date(2026, 9, 7))


def test_dst_is_resolved_by_america_new_york_not_a_fixed_offset() -> None:
    service, _, _ = build_service()

    winter_start, _ = service.session_window(date(2026, 1, 5))
    summer_start, _ = service.session_window(date(2026, 7, 6))

    assert winter_start.hour == 1
    assert summer_start.hour == 0
    assert winter_start.tzinfo == UTC
    assert summer_start.tzinfo == UTC


def test_open_uses_first_valid_bar_even_when_exact_2000_bar_is_missing() -> None:
    service, provider, _ = build_service("missing_open")

    capture = service.capture_open(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.COMPLETE
    assert capture.values[0].market_timestamp == datetime(
        2026, 9, 8, 0, 2, tzinfo=UTC
    )
    assert capture.values[0].price == Decimal("1702.35")
    assert provider.overnight_request_log == [("bars", ("SNDK", "SNXX"))]


def test_open_selects_earliest_returned_bar_not_response_order() -> None:
    service, provider, _ = build_service()
    original = provider.get_overnight_bars

    def unordered_bars(symbols, start, end, timeframe):
        base = original(symbols, start, end, timeframe)[0]
        return (
            OvernightBar(
                symbol="SNDK",
                open_price=Decimal("1703"),
                starts_at=start + timedelta(minutes=3),
                observed_at=start + timedelta(minutes=4),
                source="mock",
                source_feed="mock-boats",
                quality=DataQuality.REALTIME,
            ),
            OvernightBar(
                symbol="SNDK",
                open_price=Decimal("1701"),
                starts_at=start + timedelta(minutes=1),
                observed_at=start + timedelta(minutes=4),
                source=base.source,
                source_feed=base.source_feed,
                quality=base.quality,
            ),
        )

    provider.get_overnight_bars = unordered_bars

    capture = service.capture_open(("SNDK",), TRADING_DATE)

    assert capture.values[0].price == Decimal("1701")
    assert capture.values[0].market_timestamp == datetime(
        2026, 9, 8, 0, 1, tzinfo=UTC
    )


def test_snapshot_is_synchronized_and_uses_one_batch_request() -> None:
    service, provider, _ = build_service()

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.COMPLETE
    assert {value.quality for value in capture.values} == {DataQuality.REALTIME}
    timestamps = [value.market_timestamp for value in capture.values]
    assert max(timestamps) - min(timestamps) <= timedelta(seconds=5)
    assert provider.overnight_request_log == [("snapshot", ("SNDK", "SNXX"))]


def test_stale_quote_is_rejected() -> None:
    service, _, _ = build_service("stale")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.UNAVAILABLE
    assert all(value.quality == DataQuality.STALE for value in capture.values)
    assert all(value.status == ReferenceStatus.REJECTED for value in capture.values)


def test_missing_etf_data_is_partial() -> None:
    service, _, _ = build_service("partial")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.PARTIAL
    assert capture.values[0].status == ReferenceStatus.AVAILABLE
    assert capture.values[1].status == ReferenceStatus.MISSING
    assert capture.values[1].quality == DataQuality.UNAVAILABLE


def test_missing_underlying_data_is_partial() -> None:
    service, _, _ = build_service("missing_underlying")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.PARTIAL
    assert capture.values[0].status == ReferenceStatus.MISSING
    assert capture.values[1].status == ReferenceStatus.AVAILABLE


def test_provider_failure_becomes_explicit_unavailable_capture() -> None:
    service, _, _ = build_service("provider_failure")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.UNAVAILABLE
    assert all(value.quality == DataQuality.UNAVAILABLE for value in capture.values)
    assert all("ProviderUnavailableError" in value.message for value in capture.values)


def test_delayed_data_keeps_delayed_quality() -> None:
    service, _, _ = build_service("delayed")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.COMPLETE
    assert all(value.quality == DataQuality.DELAYED for value in capture.values)


def test_out_of_sync_snapshot_rejects_older_value() -> None:
    service, _, _ = build_service("out_of_sync")

    capture = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.PARTIAL
    assert capture.values[0].status == ReferenceStatus.REJECTED
    assert capture.values[1].status == ReferenceStatus.AVAILABLE
    assert capture.synchronization_difference == timedelta(seconds=19)


def test_missing_open_bars_do_not_fall_back_to_prior_session() -> None:
    service, _, _ = build_service("missing")

    capture = service.capture_open(("SNDK", "SNXX"), TRADING_DATE)

    assert capture.status == CaptureStatus.UNAVAILABLE
    assert all(value.price is None for value in capture.values)
    assert all(value.market_timestamp is None for value in capture.values)


def test_capture_retry_is_idempotent_for_same_market_observations() -> None:
    service, _, repository = build_service()

    first = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)
    second = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert second.id == first.id
    assert second.version == 1
    assert repository.latest(
        TRADING_DATE, first.reference_type, ("SNDK", "SNXX")
    ) == first


def test_open_and_snapshot_are_stored_as_separate_reference_types() -> None:
    service, _, repository = build_service()

    opening = service.capture_open(("SNDK", "SNXX"), TRADING_DATE)
    snapshot = service.capture_snapshot(("SNDK", "SNXX"), TRADING_DATE)

    assert opening.reference_type != snapshot.reference_type
    assert opening.id != snapshot.id
    assert repository.latest(
        TRADING_DATE, opening.reference_type, ("SNDK", "SNXX")
    ) == opening
    assert repository.latest(
        TRADING_DATE, snapshot.reference_type, ("SNDK", "SNXX")
    ) == snapshot

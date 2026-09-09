from datetime import date, datetime, timezone
from decimal import Decimal

from trafriend_api.application.services.daily_price import DailyPriceCaptureReport
from trafriend_api.application.services.market_update import DailyMarketUpdateService
from trafriend_api.application.services.universe import (
    CaptureItem,
    DailyCaptureReport,
)
from trafriend_api.domain.daily_close import CompletedTradingSession
from trafriend_api.domain.universe import (
    MarketRanking,
    PopularDataset,
    RankingBuildReport,
    RankingPeriodStatus,
    RankingPopulationStatus,
    RankingType,
)
from trafriend_api.scripts.run_daily_market_update import _exit_code_for_status

UTC = timezone.utc
NOW = datetime(2026, 9, 7, 16, tzinfo=UTC)
SESSION = CompletedTradingSession(
    trading_date=date(2026, 9, 4),
    closed_at=datetime(2026, 9, 4, 20, tzinfo=UTC),
)


def _row(period_end: date = SESSION.trading_date) -> MarketRanking:
    return MarketRanking(
        ranking_period="2026-09",
        period_start=date(2026, 9, 1),
        period_end=period_end,
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        rank=1,
        symbol="QQQ",
        trading_metric=Decimal("100"),
        calculated_at=NOW,
        source="test",
    )


class FakeCalendar:
    def latest_completed_session(self, timestamp: datetime) -> CompletedTradingSession:
        assert timestamp == NOW
        return SESSION


class FakeRepository:
    def __init__(self, dataset: PopularDataset) -> None:
        self.dataset = dataset

    def get_dataset(
        self, ranking_period: str, ranking_type: RankingType, limit: int = 100
    ) -> PopularDataset:
        assert ranking_period == "2026-09"
        assert ranking_type == RankingType.DOLLAR_TRADING_VOLUME
        return self.dataset

    def replace_verified_rows(self, rows) -> int:
        raise AssertionError("repository replacement is owned by the ranking builder")


class FakeRankingBuilder:
    def __init__(self) -> None:
        self.calls = 0

    def build_month_to_date(self, year: int, month: int) -> RankingBuildReport:
        self.calls += 1
        assert (year, month) == (2026, 9)
        row = _row()
        return RankingBuildReport(
            ranking_period="2026-09",
            completed_trading_dates=(SESSION.trading_date,),
            candidate_assets=100,
            complete_assets=100,
            incomplete_assets=0,
            persisted_rows=100,
            rows=(row,),
        )


class FakeCapture:
    def __init__(self, report: DailyCaptureReport) -> None:
        self.report = report

    def capture_popular(self, ranking_period: str) -> DailyCaptureReport:
        assert ranking_period == "2026-09"
        return self.report


class FakeOhlcCapture:
    def __init__(self, report: DailyPriceCaptureReport) -> None:
        self.report = report
        self.calls: list[tuple[date, date]] = []

    def capture(self, start: date, end: date) -> DailyPriceCaptureReport:
        self.calls.append((start, end))
        return self.report


def _ohlc(
    status: str = "COMPLETE",
    *,
    inserted: int = 0,
    existing: int = 1,
    unavailable: int = 0,
    conflicts: int = 0,
) -> DailyPriceCaptureReport:
    return DailyPriceCaptureReport(
        start=SESSION.trading_date,
        end=SESSION.trading_date,
        status=status,
        symbols=1,
        sessions=1,
        inserted=inserted,
        existing=existing,
        unavailable=unavailable,
        conflicts=conflicts,
        results=(),
    )


def _capture(status: str, item_status: str) -> DailyCaptureReport:
    return DailyCaptureReport(
        trading_date="2026-09-04",
        status=status,
        underlying_symbols=("QQQ",),
        leveraged_product_symbols=("TQQQ",),
        items=(
            CaptureItem(
                relationship_id="rel_qqq_tqqq_3x",
                underlying_symbol="QQQ",
                leveraged_product_symbol="TQQQ",
                status=item_status,
                message="test",
                anchor=None,
            ),
        ),
    )


def _capture_with_structural_skip() -> DailyCaptureReport:
    return DailyCaptureReport(
        trading_date="2026-09-04",
        status="COMPLETE",
        underlying_symbols=("QQQ", "WMT"),
        leveraged_product_symbols=("TQQQ",),
        items=(
            CaptureItem(
                relationship_id="rel_qqq_tqqq_3x",
                underlying_symbol="QQQ",
                leveraged_product_symbol="TQQQ",
                status="EXISTING",
                message="test",
                anchor=None,
            ),
            CaptureItem(
                relationship_id="",
                underlying_symbol="WMT",
                leveraged_product_symbol="",
                status="SKIPPED_NO_SUPPORTED_PRODUCT",
                message="test",
                anchor=None,
            ),
        ),
    )


def _dataset(current: bool) -> PopularDataset:
    rows = (_row(),) if current else (_row(date(2026, 9, 3)),)
    return PopularDataset(
        ranking_period="2026-09",
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        population_status=RankingPopulationStatus.COMPLETE,
        rows=rows,
    )


def test_weekend_or_holiday_rerun_skips_current_data() -> None:
    builder = FakeRankingBuilder()
    ohlc = FakeOhlcCapture(_ohlc())
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=builder,
        daily_close_capture=FakeCapture(_capture("COMPLETE", "EXISTING")),
        daily_ohlc_capture=ohlc,
        now=lambda: NOW,
    ).run()

    assert report.status == "SKIPPED"
    assert report.ranking_status == "SKIPPED"
    assert report.daily_close_status == "SKIPPED"
    assert report.ohlc_status == "EXISTING"
    assert ohlc.calls == [(SESSION.trading_date, SESSION.trading_date)]
    assert builder.calls == 0


def test_new_session_updates_ranking_and_inserts_daily_close() -> None:
    builder = FakeRankingBuilder()
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=False)),
        ranking_builder=builder,
        daily_close_capture=FakeCapture(_capture("COMPLETE", "INSERTED")),
        daily_ohlc_capture=FakeOhlcCapture(_ohlc(inserted=1, existing=0)),
        now=lambda: NOW,
    ).run()

    assert report.status == "COMPLETE"
    assert report.ranking_status == "UPDATED"
    assert report.daily_close_status == "COMPLETE"
    assert report.ohlc_status == "INSERTED"
    assert builder.calls == 1


def test_zero_product_ranked_symbol_does_not_trigger_cron_retry() -> None:
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=FakeRankingBuilder(),
        daily_close_capture=FakeCapture(_capture_with_structural_skip()),
        daily_ohlc_capture=FakeOhlcCapture(_ohlc()),
        now=lambda: NOW,
    ).run()

    assert report.status == "SKIPPED"
    assert report.daily_close_status == "SKIPPED"
    assert report.daily_close_report.skipped_no_supported_product == 1
    assert report.daily_close_report.unavailable == 0
    assert _exit_code_for_status(report.status) == 0


def test_provider_lag_is_explicitly_retryable() -> None:
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=FakeRankingBuilder(),
        daily_close_capture=FakeCapture(_capture("FAILED", "UNAVAILABLE")),
        daily_ohlc_capture=FakeOhlcCapture(_ohlc()),
        now=lambda: NOW,
    ).run()

    assert report.status == "PARTIAL_RETRYABLE"
    assert report.daily_close_report.unavailable == 1
    assert _exit_code_for_status(report.status) == 2


def test_ohlc_provider_lag_does_not_rollback_successful_daily_close() -> None:
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=FakeRankingBuilder(),
        daily_close_capture=FakeCapture(_capture("COMPLETE", "INSERTED")),
        daily_ohlc_capture=FakeOhlcCapture(
            _ohlc("PARTIAL_RETRYABLE", existing=0, unavailable=1)
        ),
        now=lambda: NOW,
    ).run()

    assert report.status == "PARTIAL_RETRYABLE"
    assert report.daily_close_report is not None
    assert report.daily_close_report.inserted == 1
    assert report.ohlc_status == "PARTIAL_RETRYABLE"


def test_conflict_is_not_classified_as_retryable() -> None:
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=FakeRankingBuilder(),
        daily_close_capture=FakeCapture(_capture("FAILED", "CONFLICT")),
        daily_ohlc_capture=FakeOhlcCapture(_ohlc()),
        now=lambda: NOW,
    ).run()

    assert report.status == "CONFLICT"
    assert _exit_code_for_status(report.status) == 1

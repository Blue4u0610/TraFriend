from datetime import date, datetime, timezone
from decimal import Decimal

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
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=builder,
        daily_close_capture=FakeCapture(_capture("VALID", "EXISTING")),
        now=lambda: NOW,
    ).run()

    assert report.status == "SKIPPED"
    assert report.ranking_status == "SKIPPED"
    assert report.daily_close_status == "SKIPPED"
    assert builder.calls == 0


def test_new_session_updates_ranking_and_inserts_daily_close() -> None:
    builder = FakeRankingBuilder()
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=False)),
        ranking_builder=builder,
        daily_close_capture=FakeCapture(_capture("VALID", "INSERTED")),
        now=lambda: NOW,
    ).run()

    assert report.status == "VALID"
    assert report.ranking_status == "UPDATED"
    assert report.daily_close_status == "VALID"
    assert builder.calls == 1


def test_provider_lag_is_explicitly_retryable() -> None:
    report = DailyMarketUpdateService(
        calendar=FakeCalendar(),
        ranking_repository=FakeRepository(_dataset(current=True)),
        ranking_builder=FakeRankingBuilder(),
        daily_close_capture=FakeCapture(_capture("FAILED", "UNAVAILABLE")),
        now=lambda: NOW,
    ).run()

    assert report.status == "PARTIAL_RETRYABLE"
    assert report.daily_close_report.unavailable == 1

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from trafriend_api.application.ports.daily_close import CompletedSessionCalendar
from trafriend_api.application.ports.ranking import MarketRankingRepository
from trafriend_api.application.services.universe import DailyCaptureReport
from trafriend_api.domain.errors import MarketDataProviderError
from trafriend_api.domain.universe import (
    RankingBuildReport,
    RankingPopulationStatus,
    RankingType,
)

UTC = timezone.utc


class MonthlyRankingBuilder(Protocol):
    def build_month_to_date(self, year: int, month: int) -> RankingBuildReport:
        raise NotImplementedError


class PopularDailyCloseCapture(Protocol):
    def capture_popular(self, ranking_period: str) -> DailyCaptureReport:
        raise NotImplementedError


@dataclass(frozen=True)
class DailyMarketUpdateReport:
    status: str
    trading_date: str
    ranking_period: str
    ranking_status: str
    ranking_rows: int
    daily_close_status: str
    daily_close_report: DailyCaptureReport


class DailyMarketUpdateService:
    """Coordinate one idempotent external market-data update invocation."""

    def __init__(
        self,
        calendar: CompletedSessionCalendar,
        ranking_repository: MarketRankingRepository,
        ranking_builder: MonthlyRankingBuilder,
        daily_close_capture: PopularDailyCloseCapture,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._calendar = calendar
        self._ranking_repository = ranking_repository
        self._ranking_builder = ranking_builder
        self._daily_close_capture = daily_close_capture
        self._now = now

    def run(self) -> DailyMarketUpdateReport:
        timestamp = self._utc_now()
        session = self._calendar.latest_completed_session(timestamp)
        ranking_period = session.trading_date.strftime("%Y-%m")
        dataset = self._ranking_repository.get_dataset(
            ranking_period,
            RankingType.DOLLAR_TRADING_VOLUME,
        )

        ranking_status = "SKIPPED"
        ranking_rows = len(dataset.rows)
        ranking_is_current = bool(
            dataset.rows
            and dataset.population_status == RankingPopulationStatus.COMPLETE
            and dataset.rows[0].period_end == session.trading_date
        )
        if not ranking_is_current:
            try:
                ranking_report = self._ranking_builder.build_month_to_date(
                    session.trading_date.year,
                    session.trading_date.month,
                )
                ranking_status = "UPDATED"
                ranking_rows = ranking_report.persisted_rows
            except (MarketDataProviderError, ValueError):
                ranking_status = "RETRYABLE"

        capture_report = self._daily_close_capture.capture_popular(ranking_period)
        daily_close_status = capture_report.status
        if (
            capture_report.items
            and capture_report.inserted == 0
            and all(
                item.status
                in {"EXISTING", "SKIPPED_NO_SUPPORTED_PRODUCT"}
                for item in capture_report.items
            )
        ):
            daily_close_status = "SKIPPED"

        if ranking_status == "RETRYABLE" or daily_close_status in {
            "PARTIAL",
            "FAILED",
        }:
            status = "PARTIAL_RETRYABLE"
        elif ranking_status == "SKIPPED" and daily_close_status == "SKIPPED":
            status = "SKIPPED"
        else:
            status = "COMPLETE"

        return DailyMarketUpdateReport(
            status=status,
            trading_date=session.trading_date.isoformat(),
            ranking_period=ranking_period,
            ranking_status=ranking_status,
            ranking_rows=ranking_rows,
            daily_close_status=daily_close_status,
            daily_close_report=capture_report,
        )

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("market update time must be timezone-aware")
        return timestamp.astimezone(UTC)

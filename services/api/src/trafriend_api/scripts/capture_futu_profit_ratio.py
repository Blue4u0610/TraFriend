"""Capture current-session QQQ Profit Ratio endpoints from a local Futu OpenD."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.services.profit_ratio import (
    FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY,
    ProfitRatioService,
)
from trafriend_api.domain.errors import MarketDataProviderError
from trafriend_api.domain.profit_ratio_daily import ProfitRatioConflictError, ProfitRatioPhase
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.market_data.futu import FutuOpenDProfitRatioProvider
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.database_target import (
    require_writable_database_target,
)
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.settings import Settings

EASTERN = ZoneInfo("America/New_York")
PUBLICATION_DELAY = timedelta(minutes=20)
CAPTURE_WINDOW = timedelta(minutes=35)


def _due_phase(
    now: datetime, opened_at: datetime, closed_at: datetime
) -> Optional[ProfitRatioPhase]:
    for phase, instant in (
        (ProfitRatioPhase.CLOSE, closed_at),
        (ProfitRatioPhase.OPEN, opened_at),
    ):
        start = instant + PUBLICATION_DELAY
        if start <= now <= start + CAPTURE_WINDOW:
            return phase
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=[phase.value for phase in ProfitRatioPhase], help="expected due phase"
    )
    parser.add_argument("--symbols", help="comma-separated QQQ symbols for a bounded smoke test")
    arguments = parser.parse_args(argv)

    engine = None
    provider = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        now = datetime.now(timezone.utc)
        today = now.astimezone(EASTERN).date()
        calendar = ProfitRatioExchangeCalendar()
        sessions = calendar.sessions(today, today)
        if not sessions:
            print(json.dumps({"status": "NOT_DUE", "trading_date": str(today)}))
            return 0
        session = sessions[0]
        due_phase = _due_phase(now, session.opened_at, session.closed_at)
        requested_phase = ProfitRatioPhase(arguments.phase) if arguments.phase else due_phase
        if requested_phase is None or requested_phase != due_phase:
            print(
                json.dumps(
                    {
                        "status": "NOT_DUE",
                        "trading_date": str(today),
                        "due_phase": due_phase.value if due_phase else None,
                    }
                )
            )
            return 0

        database_url = settings.database_url.get_secret_value()
        target = require_writable_database_target(database_url, settings.environment)
        engine = create_database_engine(database_url)
        repository = PostgreSQLProfitRatioRepository(engine)
        constituents = tuple(repository.list_constituents())
        if not constituents:
            raise ValueError("the stored QQQ constituent snapshot is empty")

        selected = None
        if arguments.symbols:
            selected = tuple(
                dict.fromkeys(
                    symbol.strip().upper()
                    for symbol in arguments.symbols.split(",")
                    if symbol.strip()
                )
            )
            if not selected or len(selected) > 25:
                raise ValueError("--symbols requires 1-25 comma-separated symbols")

        provider = FutuOpenDProfitRatioProvider(
            host=settings.futu_opend_host,
            port=settings.futu_opend_port,
            instrument_ids={item.symbol: item.instrument_id for item in constituents},
            quality=settings.futu_profit_ratio_quality,
        )
        report = ProfitRatioService(
            repository=repository,
            calendar=calendar,
            provider=provider,
            # The provider observes data after the CLI's due-window check. Use a
            # fresh clock here so a genuine response is not rejected as future data.
            now=lambda: datetime.now(timezone.utc),
            publication_delay=PUBLICATION_DELAY,
            methodology=FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY,
        ).capture(today, requested_phase, selected)
        print(
            json.dumps(
                {
                    "status": report.status,
                    "trading_date": str(today),
                    "phase": requested_phase.value,
                    "methodology": FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY.id,
                    "symbols": len(selected) if selected is not None else len(constituents),
                    "data_target": target.environment.value,
                    "database_host": target.host,
                    "database_name": target.database,
                    "inserted": report.inserted,
                    "existing": report.existing,
                    "unavailable": report.unavailable,
                    "conflicts": report.conflicts,
                    "results": [asdict(item) for item in report.results],
                },
                default=str,
            )
        )
        return 2 if report.status == "PARTIAL_RETRYABLE" else 1 if report.conflicts else 0
    except (SQLAlchemyError, ValueError, MarketDataProviderError, ProfitRatioConflictError) as exc:
        print(json.dumps({"status": "FAILED", "error_class": type(exc).__name__}))
        return 1
    finally:
        if provider is not None:
            provider.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

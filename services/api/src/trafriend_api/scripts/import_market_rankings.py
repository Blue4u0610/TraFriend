from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

from trafriend_api.domain.universe import (
    MarketRanking,
    RankingCompletenessStatus,
    RankingPeriodStatus,
    RankingType,
)
from trafriend_api.infrastructure.persistence import PostgreSQLMarketRankingRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.settings import Settings

UTC = timezone.utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import a source-attributed verified market-ranking CSV."
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--period", required=True)
    parser.add_argument("--period-start", required=True, type=date.fromisoformat)
    parser.add_argument("--period-end", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--period-status",
        required=True,
        choices=("SEPTEMBER_TO_DATE", "MONTH_TO_DATE", "FINAL"),
    )
    parser.add_argument("--source", required=True)
    parser.add_argument(
        "--calculated-at",
        type=datetime.fromisoformat,
        default=datetime.now(UTC),
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if (
            args.period == "2026-09"
            and args.period_status == "FINAL"
            and date.today() <= date(2026, 9, 30)
        ):
            raise ValueError("September 2026 cannot be FINAL before the month ends")
        calculated_at = args.calculated_at
        if calculated_at.tzinfo is None or calculated_at.utcoffset() is None:
            raise ValueError("calculated-at must include a timezone offset")
        rows = _read_rows(
            args.file,
            args.period,
            args.period_start,
            args.period_end,
            RankingPeriodStatus(args.period_status),
            args.source,
            calculated_at,
        )
        engine = create_database_engine(settings.database_url.get_secret_value())
        imported = PostgreSQLMarketRankingRepository(engine).replace_verified_rows(rows)
        engine.dispose()
        print(f"Imported Ranking Rows: {imported}")
        print(f"Ranking Period: {args.period}")
        print(f"Period Status: {args.period_status}")
        print("Ranking Type: DOLLAR_TRADING_VOLUME")
        print(f"Source: {args.source}")
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Market ranking import failed: {exc}", file=sys.stderr)
        return 1


def _read_rows(
    path: Path,
    ranking_period: str,
    period_start: date,
    period_end: date,
    period_status: RankingPeriodStatus,
    source: str,
    calculated_at: datetime,
) -> tuple[MarketRanking, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not {"rank", "symbol", "trading_metric"}.issubset(reader.fieldnames or ()):
            raise ValueError("CSV requires rank,symbol,trading_metric columns")
        return tuple(
            MarketRanking(
                ranking_period=ranking_period,
                period_start=period_start,
                period_end=period_end,
                period_status=period_status,
                ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
                rank=int(row["rank"]),
                symbol=row["symbol"].strip().upper(),
                display_name=(
                    row.get("display_name", "").strip()
                    or row["symbol"].strip().upper()
                ),
                exchange=row.get("exchange", "").strip().upper() or "UNKNOWN",
                trading_metric=Decimal(row["trading_metric"]),
                calculated_at=calculated_at,
                source=source.strip(),
                completeness_status=RankingCompletenessStatus(
                    row.get("completeness_status", "COMPLETE").strip().upper()
                    or "COMPLETE"
                ),
                sessions_observed=int(row.get("sessions_observed", "0") or "0"),
                sessions_expected=int(row.get("sessions_expected", "0") or "0"),
            )
            for row in reader
        )

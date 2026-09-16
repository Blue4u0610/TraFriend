"""Import reviewed provider-reported daily Profit Ratio values idempotently."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.application.ports.profit_ratio import ProfitRatioPersistenceOutcome
from trafriend_api.domain.profit_ratio_daily import (
    ProfitRatioConflictError,
    ProfitRatioDailyObservation,
    ProfitRatioStatus,
    ProfitRatioTimeBasis,
)
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.database_target import (
    require_writable_database_target,
)
from trafriend_api.infrastructure.persistence.postgresql_profit_ratio import (
    PostgreSQLProfitRatioRepository,
)
from trafriend_api.settings import Settings

DEFAULT_FILE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "profit_ratio"
    / "sndk_futu_daily_2026-08-04_2026-09-15.csv"
)
EXPECTED_COLUMNS = {
    "symbol",
    "trading_date",
    "ratio",
    "methodology_key",
    "methodology_version",
    "provider",
    "source_feed",
    "quality",
    "time_basis",
    "observed_at",
    "source_note",
}


def _read(path: Path) -> tuple[dict[str, str], ...]:
    if not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("a bounded CSV import file is required")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if set(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ValueError("daily Profit Ratio CSV columns do not match the reviewed schema")
        rows = tuple(reader)
    if not rows or len(rows) > 1000:
        raise ValueError("daily Profit Ratio import requires 1-1000 rows")
    return rows


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return parsed


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    arguments = parser.parse_args(argv)
    engine = None
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        database_url = settings.database_url.get_secret_value()
        target = require_writable_database_target(database_url, settings.environment)
        engine = create_database_engine(database_url)
        repository = PostgreSQLProfitRatioRepository(engine)
        constituents = {item.symbol: item for item in repository.list_constituents()}
        parsed: list[ProfitRatioDailyObservation] = []
        identities: set[tuple[str, date, str]] = set()
        for row in _read(arguments.file):
            symbol = row["symbol"].strip().upper()
            member = constituents.get(symbol)
            if member is None:
                raise ValueError("every import symbol must belong to the stored QQQ snapshot")
            trading_date = date.fromisoformat(row["trading_date"])
            time_basis = ProfitRatioTimeBasis(row["time_basis"])
            identity = (member.instrument_id, trading_date, time_basis.value)
            if identity in identities:
                raise ValueError("daily Profit Ratio CSV contains a duplicate identity")
            identities.add(identity)
            parsed.append(
                ProfitRatioDailyObservation(
                    id="pending",
                    instrument_id=member.instrument_id,
                    symbol=member.symbol,
                    trading_date=trading_date,
                    ratio=Decimal(row["ratio"]),
                    time_basis=time_basis,
                    market_timestamp=None,
                    observed_at=_instant(row["observed_at"]),
                    provider=row["provider"],
                    source_feed=row["source_feed"],
                    quality=row["quality"],
                    status=ProfitRatioStatus.REPORTED,
                    reason_code="HISTORICAL_UI_REPORTED",
                    methodology_key=row["methodology_key"],
                    methodology_version=row["methodology_version"],
                    source_note=row["source_note"],
                )
            )
        inserted = existing = conflicts = 0
        for observation in parsed:
            try:
                outcome = repository.save_daily(observation)
            except ProfitRatioConflictError:
                conflicts += 1
            else:
                inserted += int(outcome == ProfitRatioPersistenceOutcome.INSERTED)
                existing += int(outcome == ProfitRatioPersistenceOutcome.EXISTING)
        print(
            json.dumps(
                {
                    "status": "COMPLETE" if conflicts == 0 else "CONFLICT",
                    "data_target": target.environment.value,
                    "database_host": target.host,
                    "database_name": target.database,
                    "rows": len(parsed),
                    "inserted": inserted,
                    "existing": existing,
                    "conflicts": conflicts,
                }
            )
        )
        return 1 if conflicts else 0
    except (SQLAlchemyError, ValueError, InvalidOperation) as exc:
        print(json.dumps({"status": "FAILED", "error_class": type(exc).__name__}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())

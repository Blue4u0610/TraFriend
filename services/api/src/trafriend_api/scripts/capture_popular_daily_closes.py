from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.presentation.http.dependencies import build_application_services
from trafriend_api.settings import Settings

UTC = timezone.utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture latest completed regular-session anchors for the populated "
            "popular universe or an explicit manual symbol list."
        )
    )
    parser.add_argument(
        "--period",
        help="Ranking period in YYYY-MM; defaults to the latest completed session month.",
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated supported underlyings for deterministic/manual runs.",
    )
    parser.add_argument("--provider", choices=("mock", "alpaca"))
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if args.provider:
            settings = settings.model_copy(
                update={"daily_close_provider": args.provider}
            )
        services = build_application_services(settings)
        if args.symbols:
            report = services.universe.capture_symbols(args.symbols.split(","))
        else:
            period = args.period
            if period is None:
                session = NyseTradingCalendar().latest_completed_session(
                    datetime.now(UTC)
                )
                period = session.trading_date.strftime("%Y-%m")
            report = services.universe.capture_popular(period)
        print(f"Capture Status: {report.status}")
        print(f"Latest Completed Trading Date: {report.trading_date}")
        print(
            "Underlying Symbols: "
            + (", ".join(report.underlying_symbols) or "NONE")
        )
        print(
            "Leveraged ETF Symbols: "
            + (", ".join(report.leveraged_product_symbols) or "NONE")
        )
        print(f"Inserted: {report.inserted}")
        print(f"Existing: {report.existing}")
        print(
            "Skipped No Supported Product: "
            f"{report.skipped_no_supported_product}"
        )
        print(f"Unavailable: {report.unavailable}")
        print(f"Conflicts: {report.conflicts}")
        for item in report.items:
            pair = (
                f"{item.underlying_symbol}/{item.leveraged_product_symbol}"
                if item.leveraged_product_symbol
                else item.underlying_symbol
            )
            print(f"{pair}: {item.status} ({item.message})")
        return (
            0
            if report.status == "COMPLETE"
            else 2
            if report.status == "PARTIAL"
            else 1
        )
    except (SQLAlchemyError, ValueError) as exc:
        print(
            f"Popular daily-close capture failed: {exc.__class__.__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

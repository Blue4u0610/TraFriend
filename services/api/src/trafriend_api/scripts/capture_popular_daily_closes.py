from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from trafriend_api.presentation.http.dependencies import build_application_services
from trafriend_api.settings import Settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture latest completed regular-session anchors for the populated "
            "popular universe or an explicit manual symbol list."
        )
    )
    parser.add_argument("--period", default="2026-09")
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
            report = services.universe.capture_popular(args.period)
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
        print(f"Unavailable: {report.unavailable}")
        for item in report.items:
            pair = (
                f"{item.underlying_symbol}/{item.leveraged_product_symbol}"
                if item.leveraged_product_symbol
                else item.underlying_symbol
            )
            print(f"{pair}: {item.status} ({item.message})")
        return 0 if report.status == "VALID" else 2 if report.status == "PARTIAL" else 1
    except ValueError as exc:
        print(f"Popular daily-close capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

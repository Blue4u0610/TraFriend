from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trafriend_api.application.ports.overnight_market_data import (
    OvernightMarketDataProvider,
)
from trafriend_api.application.services.overnight_reference import (
    OvernightReferenceService,
)
from trafriend_api.domain.errors import OvernightSessionError, ProviderAuthenticationError
from trafriend_api.domain.overnight import (
    CaptureStatus,
    OvernightReferenceCapture,
    ReferenceType,
)
from trafriend_api.domain.universe import (
    DEFAULT_SUPPORTED_UNIVERSE,
    SupportedAssetGroup,
    SupportedLeveragedProduct,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.alpaca import AlpacaMarketDataProvider
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryOvernightReferenceRepository
from trafriend_api.settings import Settings

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and print an overnight reference without scheduling it."
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated supported symbols, for example SNDK,SNXX",
    )
    parser.add_argument(
        "--trading-date",
        "--date",
        dest="trading_date",
        required=True,
        type=date.fromisoformat,
        help="Exchange trading date in YYYY-MM-DD form",
    )
    parser.add_argument(
        "--reference-type",
        type=_parse_reference_type,
        default=ReferenceType.OVERNIGHT_SNAPSHOT,
        metavar="OVERNIGHT_OPEN|OVERNIGHT_SNAPSHOT",
    )
    parser.add_argument("--provider", choices=("mock", "alpaca"))
    parser.add_argument(
        "--mock-scenario",
        choices=MockMarketDataProvider.scenario_codes,
        default="normal",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print ET/UTC request windows and selection/rejection details",
    )
    return parser


def _parse_reference_type(value: str) -> ReferenceType:
    normalized = value.strip().upper().replace("-", "_")
    try:
        return ReferenceType(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "reference type must be overnight-open or overnight-snapshot"
        ) from exc


def _resolve_supported_group(
    symbols: Sequence[str],
) -> Tuple[Tuple[str, ...], SupportedAssetGroup, Tuple[SupportedLeveragedProduct, ...]]:
    normalized = tuple(
        dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
    )
    if not normalized:
        raise ValueError("at least one symbol is required")
    try:
        group = DEFAULT_SUPPORTED_UNIVERSE.group_for(normalized[0])
    except KeyError as exc:
        raise ValueError(str(exc).strip("'")) from exc
    unsupported = tuple(symbol for symbol in normalized if symbol not in group.symbols)
    if unsupported:
        raise ValueError(
            "symbols must belong to one supported underlying group; unsupported here: "
            + ",".join(unsupported)
        )
    if group.underlying_symbol not in normalized:
        raise ValueError(
            f"capture must include underlying symbol {group.underlying_symbol}"
        )
    selected_products = tuple(
        product for product in group.leveraged_products if product.symbol in normalized
    )
    if not selected_products:
        raise ValueError("capture must include at least one associated leveraged ETF")
    return normalized, group, selected_products


def _build_provider(
    provider_name: str, settings: Settings, mock_scenario: str
) -> OvernightMarketDataProvider:
    if provider_name == "mock":
        return MockMarketDataProvider(mock_scenario)
    if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
        raise ProviderAuthenticationError(
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY first"
        )
    return AlpacaMarketDataProvider(
        key_id=settings.alpaca_key_id.get_secret_value(),
        secret_key=settings.alpaca_secret_key.get_secret_value(),
        base_url=settings.alpaca_data_base_url,
        snapshot_feed=settings.alpaca_snapshot_feed,
        bars_feed=settings.alpaca_bars_feed,
        snapshot_quality=settings.alpaca_snapshot_quality,
        bars_quality=settings.alpaca_bars_quality,
    )


def _format_market_time(timestamp: datetime) -> str:
    return timestamp.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_utc(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _format_leverage(value: Decimal) -> str:
    prefix = "+" if value > 0 else ""
    return f"{prefix}{value}x"


def _print_debug_context(
    service: OvernightReferenceService,
    provider: OvernightMarketDataProvider,
    symbols: Sequence[str],
    trading_date: date,
    reference_type: ReferenceType,
) -> None:
    session_start, session_end = service.session_window(trading_date)
    requested_end = (
        min(session_start + timedelta(minutes=15), session_end)
        if reference_type == ReferenceType.OVERNIGHT_OPEN
        else service.snapshot_timestamp(trading_date)
    )
    print("Debug Context:")
    print(f"  Requested Symbols: {','.join(symbols)}")
    print(f"  Provider: {provider.provider_code}")
    print(f"  Configured Feed(s): {provider.source_feed}")
    print(
        "  Request Window ET: "
        f"{_format_market_time(session_start)} -> {_format_market_time(requested_end)}"
    )
    print(
        "  Request Window UTC: "
        f"{_format_utc(session_start)} -> {_format_utc(requested_end)}"
    )
    print(f"  Overnight Session End ET: {_format_market_time(session_end)}")
    print()


def _print_capture(
    capture: OvernightReferenceCapture,
    group: SupportedAssetGroup,
    products: Sequence[SupportedLeveragedProduct],
    verbose: bool,
) -> None:
    print(f"Trading Date: {capture.trading_date.isoformat()}")
    print(f"Reference Type: {capture.reference_type.value}")
    print(f"Provider: {capture.source}")
    print(f"Provider Feed(s): {capture.source_feed}")
    print(f"Underlying: {group.underlying_symbol}")
    print(
        "Leveraged ETF(s): "
        + ", ".join(
            f"{product.symbol} ({_format_leverage(product.signed_leverage)})"
            for product in products
        )
    )
    print(f"Capture Status: {capture.status.value}")
    print(f"Version: {capture.version}")
    for value in capture.values:
        print()
        print(value.symbol)
        print(f"Price: {value.price if value.price is not None else 'N/A'}")
        print(f"Observed At: {_format_market_time(value.observed_at)}")
        print(
            "Market/Bar Timestamp (ET): "
            f"{_format_market_time(value.market_timestamp) if value.market_timestamp else 'N/A'}"
        )
        if verbose:
            print(
                "Market/Bar Timestamp (UTC): "
                f"{_format_utc(value.market_timestamp) if value.market_timestamp else 'N/A'}"
            )
            print(f"Observed At (UTC): {_format_utc(value.observed_at)}")
        print(f"Source: {value.source}")
        print(f"Feed: {value.source_feed}")
        print(f"Quality: {value.quality.value}")
        print(f"Status: {value.status.value}")
        print(f"Price Basis: {value.price_basis.value}")
        if value.message:
            print(f"Selection/Rejection Reason: {value.message}")

    difference = capture.synchronization_difference
    if difference is None:
        print("\nSynchronization Difference: N/A")
    else:
        milliseconds = difference.total_seconds() * 1000
        print(f"\nSynchronization Difference: {milliseconds:.3f} ms")
    overall = {
        CaptureStatus.COMPLETE: "VALID",
        CaptureStatus.PARTIAL: "PARTIAL",
        CaptureStatus.UNAVAILABLE: "UNAVAILABLE",
    }[capture.status]
    print(f"Overall Result: {overall}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        symbols, group, products = _resolve_supported_group(args.symbols.split(","))
        settings = Settings.from_environment()
        provider_name = args.provider or settings.overnight_provider
        provider = _build_provider(provider_name, settings, args.mock_scenario)
        service = OvernightReferenceService(
            provider=provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryOvernightReferenceRepository(),
            now=lambda: datetime.now(UTC),
        )
        if args.verbose:
            _print_debug_context(
                service, provider, symbols, args.trading_date, args.reference_type
            )
        if args.reference_type == ReferenceType.OVERNIGHT_OPEN:
            capture = service.capture_open(symbols, args.trading_date)
        else:
            capture = service.capture_snapshot(symbols, args.trading_date)
        _print_capture(capture, group, products, args.verbose)
        return 0 if capture.status == CaptureStatus.COMPLETE else 2
    except (OvernightSessionError, ProviderAuthenticationError, ValueError) as exc:
        print("Overall Result: UNAVAILABLE", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

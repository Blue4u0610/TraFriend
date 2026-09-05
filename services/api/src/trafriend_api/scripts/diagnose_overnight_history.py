from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from trafriend_api.application.ports.overnight_market_data import (
    HistoricalOvernightMarketDataProvider,
)
from trafriend_api.application.services.overnight_reference import (
    OvernightReferenceService,
)
from trafriend_api.domain.errors import (
    MarketDataProviderError,
    OvernightSessionError,
    ProviderAuthenticationError,
)
from trafriend_api.domain.overnight import (
    HistoricalOvernightBar,
    HistoricalOvernightQuote,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.alpaca import AlpacaMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryOvernightReferenceRepository
from trafriend_api.settings import Settings

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")
OPENING_WINDOW = timedelta(minutes=15)
MAX_SYNCHRONIZATION_DIFFERENCE = timedelta(seconds=5)

VALID_OPENING_WINDOW_DATA = "VALID OPENING-WINDOW DATA"
OVERNIGHT_WITHOUT_OPENING_TRADE = "OVERNIGHT DATA BUT NO OPENING-WINDOW TRADE"
NO_OVERNIGHT_TRADE_DATA = "NO OVERNIGHT TRADE DATA"
PROVIDER_LIMITATION_UNKNOWN = "PROVIDER LIMITATION / UNKNOWN"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect bounded historical Alpaca BOATS bars and two-sided quotes "
            "without changing reference-capture policy."
        )
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, for example SNDK,SNXX",
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
        "--quote-time",
        type=_parse_time,
        default=time(20, 5),
        help="Eastern target time in HH:MM[:SS] form (default: 20:05)",
    )
    parser.add_argument(
        "--quote-window-seconds",
        type=_positive_integer,
        default=60,
        help="Bounded historical quote radius on each side of the target (default: 60)",
    )
    return parser


def _parse_time(value: str) -> time:
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, pattern).time()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError("quote time must use HH:MM or HH:MM:SS")


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0 or parsed > 300:
        raise argparse.ArgumentTypeError("quote window must be between 1 and 300 seconds")
    return parsed


def _normalize_symbols(value: str) -> Tuple[str, ...]:
    symbols = tuple(
        dict.fromkeys(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    )
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols


def _build_provider(settings: Settings) -> AlpacaMarketDataProvider:
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
        timeout_seconds=30,
    )


def _classify_bars(
    bars: Sequence[HistoricalOvernightBar], session_start: datetime
) -> str:
    if not bars:
        return NO_OVERNIGHT_TRADE_DATA
    first = min(bars, key=lambda bar: bar.starts_at)
    if session_start <= first.starts_at < session_start + OPENING_WINDOW:
        return VALID_OPENING_WINDOW_DATA
    return OVERNIGHT_WITHOUT_OPENING_TRADE


def _select_nearest_quote(
    quotes: Sequence[HistoricalOvernightQuote], target: datetime
) -> Optional[HistoricalOvernightQuote]:
    if not quotes:
        return None
    return min(
        quotes,
        key=lambda quote: (
            abs(quote.market_timestamp - target),
            quote.market_timestamp,
        ),
    )


def _format_market_time(timestamp: datetime) -> str:
    return f"{timestamp.astimezone(EASTERN).isoformat()} [America/New_York]"


def _format_utc(timestamp: datetime) -> str:
    return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _print_bar_diagnostic(
    symbol: str,
    bars: Sequence[HistoricalOvernightBar],
    session_start: datetime,
) -> None:
    ordered = sorted(bars, key=lambda bar: bar.starts_at)
    print(f"\n{symbol} FULL OVERNIGHT BARS")
    print(f"Classification: {_classify_bars(ordered, session_start)}")
    print(f"Total Bars: {len(ordered)}")
    if not ordered:
        print("First Bar Timestamp: N/A")
        print("First Bar Open: N/A")
        print("First Bar High: N/A")
        print("First Bar Low: N/A")
        print("First Bar Close: N/A")
        print("First Bar Volume: N/A")
        print("Last Bar Timestamp: N/A")
        print("Last Bar Close: N/A")
        print("Opening Window: NO BAR")
        return

    first = ordered[0]
    last = ordered[-1]
    print(f"First Bar Timestamp: {_format_market_time(first.starts_at)}")
    print(f"First Bar Open: {first.open_price}")
    print(f"First Bar High: {first.high_price}")
    print(f"First Bar Low: {first.low_price}")
    print(f"First Bar Close: {first.close_price}")
    print(f"First Bar Volume: {first.volume}")
    print(f"Last Bar Timestamp: {_format_market_time(last.starts_at)}")
    print(f"Last Bar Close: {last.close_price}")
    print(
        "Opening Window: "
        + (
            "INSIDE 20:00-20:15 ET"
            if session_start <= first.starts_at < session_start + OPENING_WINDOW
            else "OUTSIDE 20:00-20:15 ET"
        )
    )
    print(f"Feed: {first.source_feed}")
    print(f"Quality: {first.quality.value}")


def _print_quote_diagnostic(
    symbol: str,
    quotes: Sequence[HistoricalOvernightQuote],
    target: datetime,
) -> Optional[HistoricalOvernightQuote]:
    selected = _select_nearest_quote(quotes, target)
    print(f"\n{symbol} HISTORICAL QUOTE")
    print(f"Valid Two-Sided Quotes Returned: {len(quotes)}")
    print(
        "Selection Rule: closest valid two-sided quote to the 20:05 ET target; "
        "an exact-distance tie uses the earlier timestamp"
    )
    if selected is None:
        print("Bid: N/A")
        print("Ask: N/A")
        print("Midpoint: N/A")
        print("Market Timestamp: N/A")
        print("Feed: boats")
        print("Quality: UNAVAILABLE")
        print("Status: MISSING")
        return None

    offset = abs(selected.market_timestamp - target)
    print(f"Bid: {selected.bid_price}")
    print(f"Ask: {selected.ask_price}")
    print(f"Midpoint: {selected.midpoint}")
    print(f"Market Timestamp: {_format_market_time(selected.market_timestamp)}")
    print(f"Target Offset: {offset.total_seconds():.6f} seconds")
    print(f"Feed: {selected.source_feed}")
    print(f"Quality: {selected.quality.value}")
    print("Status: AVAILABLE")
    return selected


def _group_by_symbol(items: Sequence[object], symbols: Sequence[str]) -> Dict[str, list]:
    grouped: Dict[str, list] = {symbol: [] for symbol in symbols}
    for item in items:
        symbol = getattr(item, "symbol", "").upper()
        if symbol in grouped:
            grouped[symbol].append(item)
    return grouped


def _run_diagnostic(
    provider: HistoricalOvernightMarketDataProvider,
    symbols: Sequence[str],
    session_start: datetime,
    session_end: datetime,
    quote_target: datetime,
    quote_radius: timedelta,
) -> None:
    bars = provider.get_historical_overnight_bars(
        symbols, session_start, session_end, "1Min"
    )
    quotes = provider.get_historical_overnight_quotes(
        symbols, quote_target - quote_radius, quote_target + quote_radius
    )
    bars_by_symbol = _group_by_symbol(bars, symbols)
    quotes_by_symbol = _group_by_symbol(quotes, symbols)

    for symbol in symbols:
        _print_bar_diagnostic(symbol, bars_by_symbol[symbol], session_start)

    selected_quotes = []
    for symbol in symbols:
        selected = _print_quote_diagnostic(
            symbol, quotes_by_symbol[symbol], quote_target
        )
        if selected is not None:
            selected_quotes.append(selected)

    if len(selected_quotes) == len(symbols) and len(symbols) >= 2:
        timestamps = [quote.market_timestamp for quote in selected_quotes]
        difference = max(timestamps) - min(timestamps)
        print(
            "\nQuote Synchronization Difference: "
            f"{difference.total_seconds():.6f} seconds "
            f"({difference.total_seconds() * 1000:.3f} ms)"
        )
        feasible = difference <= MAX_SYNCHRONIZATION_DIFFERENCE
        print(
            "Synchronized Quote-Based Reference Feasible: "
            + ("YES" if feasible else "NO")
            + " under the existing 5-second maximum-skew criterion"
        )
    else:
        print("\nQuote Synchronization Difference: N/A")
        print("Synchronized Quote-Based Reference Feasible: UNKNOWN")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    symbols = _normalize_symbols(args.symbols)
    try:
        settings = Settings.from_environment()
        provider = _build_provider(settings)
        session_service = OvernightReferenceService(
            provider=provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryOvernightReferenceRepository(),
            now=lambda: datetime.now(UTC),
        )
        session_start, session_end = session_service.session_window(args.trading_date)
        session_evening = session_start.astimezone(EASTERN).date()
        quote_target = datetime.combine(
            session_evening, args.quote_time, tzinfo=EASTERN
        ).astimezone(UTC)
        if not session_start <= quote_target < session_end:
            raise ValueError("quote target must fall inside the overnight session")
        quote_radius = timedelta(seconds=args.quote_window_seconds)

        print(f"Trading Date: {args.trading_date.isoformat()}")
        print(f"Provider: {provider.provider_code}")
        print("Historical Feed: boats")
        print(
            "Session Window ET: "
            f"{_format_market_time(session_start)} -> {_format_market_time(session_end)}"
        )
        print(
            "Session Window UTC: "
            f"{_format_utc(session_start)} -> {_format_utc(session_end)}"
        )
        print(f"Quote Target ET: {_format_market_time(quote_target)}")
        print(
            "Quote Request Window ET: "
            f"{_format_market_time(quote_target - quote_radius)} -> "
            f"{_format_market_time(quote_target + quote_radius)}"
        )
        _run_diagnostic(
            provider,
            symbols,
            session_start,
            session_end,
            quote_target,
            quote_radius,
        )
        return 0
    except (
        MarketDataProviderError,
        OvernightSessionError,
        ProviderAuthenticationError,
        ValueError,
    ) as exc:
        print(f"Classification: {PROVIDER_LIMITATION_UNKNOWN}", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import httpx

from trafriend_api.application.ports.daily_close import DailyCloseMarketDataProvider
from trafriend_api.application.ports.overnight_market_data import (
    HistoricalOvernightMarketDataProvider,
    OvernightMarketDataProvider,
)
from trafriend_api.domain.daily_close import DailyCloseBar, DailyCloseQuality
from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.overnight import (
    DataQuality,
    HistoricalOvernightBar,
    HistoricalOvernightQuote,
    OvernightBar,
    OvernightQuote,
    PriceBasis,
    ProviderCapabilities,
)

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.-]{1,16}$")


class AlpacaMarketDataProvider(
    OvernightMarketDataProvider,
    HistoricalOvernightMarketDataProvider,
    DailyCloseMarketDataProvider,
):
    """Alpaca HTTP adapter for BOATS bars and overnight/BOATS quotes."""

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        base_url: str = "https://data.alpaca.markets",
        snapshot_feed: str = "overnight",
        bars_feed: str = "boats",
        snapshot_quality: DataQuality = DataQuality.REALTIME,
        bars_quality: DataQuality = DataQuality.DELAYED,
        daily_bars_feed: str = "sip",
        daily_bars_quality: DailyCloseQuality = DailyCloseQuality.DELAYED,
        timeout_seconds: float = 10.0,
        client: Optional[httpx.Client] = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not key_id or not secret_key:
            raise ProviderAuthenticationError("Alpaca credentials are required")
        if snapshot_feed not in {"overnight", "boats"}:
            raise ValueError("snapshot_feed must be overnight or boats")
        if bars_feed != "boats":
            raise ValueError("historical overnight bars require the boats feed")
        if snapshot_quality not in {DataQuality.REALTIME, DataQuality.DELAYED}:
            raise ValueError("snapshot quality must be REALTIME or DELAYED")
        if bars_quality not in {DataQuality.REALTIME, DataQuality.DELAYED}:
            raise ValueError("bars quality must be REALTIME or DELAYED")
        if daily_bars_feed not in {"sip", "iex"}:
            raise ValueError("daily_bars_feed must be sip or iex")
        if daily_bars_quality not in {
            DailyCloseQuality.REALTIME,
            DailyCloseQuality.DELAYED,
        }:
            raise ValueError("daily bars quality must be REALTIME or DELAYED")
        self._snapshot_feed = snapshot_feed
        self._bars_feed = bars_feed
        self._snapshot_quality = snapshot_quality
        self._bars_quality = bars_quality
        self._daily_bars_feed = daily_bars_feed
        self._daily_bars_quality = daily_bars_quality
        self._now = now
        self._headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    @property
    def provider_code(self) -> str:
        return "alpaca"

    @property
    def source_feed(self) -> str:
        if self._snapshot_feed == self._bars_feed:
            return self._snapshot_feed
        return f"snapshot:{self._snapshot_feed};bars:{self._bars_feed}"

    @property
    def daily_close_feed(self) -> str:
        return self._daily_bars_feed

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            true_overnight=True,
            minute_bars=True,
            quotes=True,
            snapshots=True,
            batch_quotes=True,
            batch_bars=True,
            historical_overnight=True,
        )

    def get_latest_quotes(self, symbols: Sequence[str]) -> Sequence[OvernightQuote]:
        normalized = self._normalize_symbols(symbols)
        observed_at = self._utc_now()
        payload = self._request_json(
            "/v2/stocks/quotes/latest",
            {"symbols": ",".join(normalized), "feed": self._snapshot_feed},
        )
        quotes_payload = payload.get("quotes")
        if not isinstance(quotes_payload, Mapping):
            raise ProviderUnavailableError("Alpaca returned a malformed quote response")
        quotes = []
        for symbol in normalized:
            raw_quote = quotes_payload.get(symbol)
            if not isinstance(raw_quote, Mapping):
                continue
            quote = self._parse_quote(symbol, raw_quote, observed_at)
            if quote is None:
                raise ProviderUnavailableError(
                    "Alpaca returned malformed data for a requested quote"
                )
            quotes.append(quote)
        return tuple(quotes)

    def get_overnight_snapshot(
        self, symbols: Sequence[str], timestamp: datetime
    ) -> Sequence[OvernightQuote]:
        self._require_aware(timestamp)
        return self.get_latest_quotes(symbols)

    def get_overnight_bars(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> Sequence[OvernightBar]:
        detailed_bars = self.get_historical_overnight_bars(
            symbols, start, end, timeframe
        )
        return tuple(
            OvernightBar(
                symbol=bar.symbol,
                open_price=bar.open_price,
                starts_at=bar.starts_at,
                observed_at=bar.observed_at,
                source=bar.source,
                source_feed=bar.source_feed,
                quality=bar.quality,
            )
            for bar in detailed_bars
        )

    def get_historical_overnight_bars(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> Sequence[HistoricalOvernightBar]:
        normalized = self._normalize_symbols(symbols)
        self._require_aware(start)
        self._require_aware(end)
        if start >= end:
            raise ValueError("bar start must precede bar end")
        if timeframe != "1Min":
            raise ValueError("Alpaca overnight reference capture requires 1Min bars")

        bars = []
        page_token = None
        while True:
            params = {
                "symbols": ",".join(normalized),
                "timeframe": timeframe,
                "start": self._format_rfc3339(start),
                "end": self._format_rfc3339(end),
                "feed": self._bars_feed,
                "adjustment": "raw",
                "sort": "asc",
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            payload = self._request_json("/v2/stocks/bars", params)
            observed_at = self._utc_now()
            bars_payload = payload.get("bars")
            if not isinstance(bars_payload, Mapping):
                raise ProviderUnavailableError("Alpaca returned a malformed bars response")
            for symbol in normalized:
                raw_bars = bars_payload.get(symbol, ())
                if not isinstance(raw_bars, list):
                    continue
                for raw_bar in raw_bars:
                    if isinstance(raw_bar, Mapping):
                        parsed = self._parse_historical_bar(
                            symbol, raw_bar, observed_at
                        )
                        if parsed is None:
                            raise ProviderUnavailableError(
                                "Alpaca returned malformed data for a requested bar"
                            )
                        bars.append(parsed)
            page_token = payload.get("next_page_token")
            if not isinstance(page_token, str) or not page_token:
                break
        return tuple(sorted(bars, key=lambda bar: (bar.starts_at, bar.symbol)))

    def get_historical_overnight_quotes(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> Sequence[HistoricalOvernightQuote]:
        normalized = self._normalize_symbols(symbols)
        self._require_aware(start)
        self._require_aware(end)
        if start >= end:
            raise ValueError("quote start must precede quote end")

        quotes = []
        page_token = None
        while True:
            params = {
                "symbols": ",".join(normalized),
                "start": self._format_rfc3339(start),
                "end": self._format_rfc3339(end),
                "feed": self._bars_feed,
                "sort": "asc",
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            observed_at = self._utc_now()
            payload = self._request_json("/v2/stocks/quotes", params)
            quotes_payload = payload.get("quotes")
            if not isinstance(quotes_payload, Mapping):
                raise ProviderUnavailableError(
                    "Alpaca returned a malformed historical quote response"
                )
            for symbol in normalized:
                raw_quotes = quotes_payload.get(symbol, ())
                if not isinstance(raw_quotes, list):
                    continue
                for raw_quote in raw_quotes:
                    if isinstance(raw_quote, Mapping):
                        parsed = self._parse_historical_quote(
                            symbol, raw_quote, observed_at
                        )
                        if parsed is not None:
                            quotes.append(parsed)
            page_token = payload.get("next_page_token")
            if not isinstance(page_token, str) or not page_token:
                break
        return tuple(
            sorted(quotes, key=lambda quote: (quote.market_timestamp, quote.symbol))
        )

    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        """Return normalized unadjusted daily bars for inclusive trading dates."""

        normalized = self._normalize_symbols(symbols)
        if start > end:
            raise ValueError("daily bar start cannot follow end")
        start_at = datetime.combine(start, time.min, tzinfo=EASTERN)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=EASTERN)
        bars = []
        page_token = None
        while True:
            params = {
                "symbols": ",".join(normalized),
                "timeframe": "1Day",
                "start": self._format_rfc3339(start_at),
                "end": self._format_rfc3339(end_at),
                "feed": self._daily_bars_feed,
                "adjustment": "raw",
                "sort": "asc",
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            payload = self._request_json("/v2/stocks/bars", params)
            observed_at = self._utc_now()
            bars_payload = payload.get("bars")
            if not isinstance(bars_payload, Mapping):
                raise ProviderUnavailableError("Alpaca returned a malformed bars response")
            for symbol in normalized:
                raw_bars = bars_payload.get(symbol, ())
                if not isinstance(raw_bars, list):
                    continue
                for raw_bar in raw_bars:
                    if not isinstance(raw_bar, Mapping):
                        continue
                    parsed = self._parse_daily_close_bar(
                        symbol, raw_bar, observed_at
                    )
                    if parsed is None:
                        raise ProviderUnavailableError(
                            "Alpaca returned malformed daily bar data"
                        )
                    if start <= parsed.trading_date <= end:
                        bars.append(parsed)
            page_token = payload.get("next_page_token")
            if not isinstance(page_token, str) or not page_token:
                break
        return tuple(sorted(bars, key=lambda bar: (bar.trading_date, bar.symbol)))

    def _parse_quote(
        self, symbol: str, raw: Mapping[str, Any], observed_at: datetime
    ) -> Optional[OvernightQuote]:
        try:
            bid = Decimal(str(raw["bp"]))
            ask = Decimal(str(raw["ap"]))
            timestamp = self._parse_rfc3339(str(raw["t"]))
        except (KeyError, InvalidOperation, ValueError):
            return None
        if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0:
            return None
        return OvernightQuote(
            symbol=symbol,
            price=(bid + ask) / Decimal("2"),
            market_timestamp=timestamp,
            observed_at=observed_at,
            source=self.provider_code,
            source_feed=self._snapshot_feed,
            quality=self._snapshot_quality,
            price_basis=PriceBasis.QUOTE_MIDPOINT,
        )

    def _parse_historical_bar(
        self, symbol: str, raw: Mapping[str, Any], observed_at: datetime
    ) -> Optional[HistoricalOvernightBar]:
        try:
            open_price = Decimal(str(raw["o"]))
            high_price = Decimal(str(raw["h"]))
            low_price = Decimal(str(raw["l"]))
            close_price = Decimal(str(raw["c"]))
            volume = Decimal(str(raw["v"]))
            starts_at = self._parse_rfc3339(str(raw["t"]))
            return HistoricalOvernightBar(
                symbol=symbol,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                starts_at=starts_at,
                observed_at=observed_at,
                source=self.provider_code,
                source_feed=self._bars_feed,
                quality=self._bars_quality,
            )
        except (KeyError, InvalidOperation, ValueError):
            return None

    def _parse_historical_quote(
        self, symbol: str, raw: Mapping[str, Any], observed_at: datetime
    ) -> Optional[HistoricalOvernightQuote]:
        try:
            bid = Decimal(str(raw["bp"]))
            ask = Decimal(str(raw["ap"]))
            timestamp = self._parse_rfc3339(str(raw["t"]))
        except (KeyError, InvalidOperation, ValueError):
            return None
        if not bid.is_finite() or not ask.is_finite() or bid <= 0 or ask <= 0:
            return None
        return HistoricalOvernightQuote(
            symbol=symbol,
            bid_price=bid,
            ask_price=ask,
            market_timestamp=timestamp,
            observed_at=observed_at,
            source=self.provider_code,
            source_feed=self._bars_feed,
            quality=self._bars_quality,
        )

    def _parse_daily_close_bar(
        self, symbol: str, raw: Mapping[str, Any], observed_at: datetime
    ) -> Optional[DailyCloseBar]:
        try:
            close = Decimal(str(raw["c"]))
            market_timestamp = self._parse_rfc3339(str(raw["t"]))
            return DailyCloseBar(
                symbol=symbol,
                trading_date=market_timestamp.astimezone(EASTERN).date(),
                close=close,
                market_timestamp=market_timestamp,
                observed_at=observed_at,
                source=self.provider_code,
                source_feed=self._daily_bars_feed,
                currency="USD",
                quality=self._daily_bars_quality,
            )
        except (KeyError, InvalidOperation, ValueError):
            return None

    def _request_json(self, path: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        try:
            response = self._client.get(path, params=params, headers=self._headers)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ProviderUnavailableError("Alpaca market data request failed") from exc
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "Alpaca credentials or market-data entitlement are invalid"
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("Alpaca market data rate limit was reached")
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"Alpaca market data request failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Alpaca returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("Alpaca returned an unexpected response shape")
        return payload

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        self._require_aware(timestamp)
        return timestamp.astimezone(UTC)

    @staticmethod
    def _normalize_symbols(symbols: Sequence[str]) -> Tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        if not normalized:
            raise ValueError("at least one symbol is required")
        if len(normalized) > 200:
            raise ValueError("at most 200 symbols may be requested together")
        if any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in normalized):
            raise ValueError("one or more symbols have an invalid format")
        return normalized

    @staticmethod
    def _parse_rfc3339(value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        match = re.match(r"^(.*\.)(\d{7,})([+-]\d\d:\d\d)$", normalized)
        if match:
            normalized = f"{match.group(1)}{match.group(2)[:6]}{match.group(3)}"
        timestamp = datetime.fromisoformat(normalized)
        AlpacaMarketDataProvider._require_aware(timestamp)
        return timestamp.astimezone(UTC)

    @staticmethod
    def _format_rfc3339(timestamp: datetime) -> str:
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _require_aware(timestamp: datetime) -> None:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")

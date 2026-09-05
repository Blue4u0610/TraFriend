from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

import httpx

from trafriend_api.application.ports.overnight_market_data import (
    OvernightMarketDataProvider,
)
from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.overnight import (
    DataQuality,
    OvernightBar,
    OvernightQuote,
    PriceBasis,
    ProviderCapabilities,
)

UTC = timezone.utc
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.-]{1,16}$")


class AlpacaMarketDataProvider(OvernightMarketDataProvider):
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
        self._snapshot_feed = snapshot_feed
        self._bars_feed = bars_feed
        self._snapshot_quality = snapshot_quality
        self._bars_quality = bars_quality
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
            observed_at = self._utc_now()
            payload = self._request_json("/v2/stocks/bars", params)
            bars_payload = payload.get("bars")
            if not isinstance(bars_payload, Mapping):
                raise ProviderUnavailableError("Alpaca returned a malformed bars response")
            for symbol in normalized:
                raw_bars = bars_payload.get(symbol, ())
                if not isinstance(raw_bars, list):
                    continue
                for raw_bar in raw_bars:
                    if isinstance(raw_bar, Mapping):
                        parsed = self._parse_bar(symbol, raw_bar, observed_at)
                        if parsed is None:
                            raise ProviderUnavailableError(
                                "Alpaca returned malformed data for a requested bar"
                            )
                        bars.append(parsed)
            page_token = payload.get("next_page_token")
            if not isinstance(page_token, str) or not page_token:
                break
        return tuple(bars)

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

    def _parse_bar(
        self, symbol: str, raw: Mapping[str, Any], observed_at: datetime
    ) -> Optional[OvernightBar]:
        try:
            open_price = Decimal(str(raw["o"]))
            starts_at = self._parse_rfc3339(str(raw["t"]))
            return OvernightBar(
                symbol=symbol,
                open_price=open_price,
                starts_at=starts_at,
                observed_at=observed_at,
                source=self.provider_code,
                source_feed=self._bars_feed,
                quality=self._bars_quality,
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
                "Alpaca credentials or overnight data entitlement are invalid"
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

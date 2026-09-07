from __future__ import annotations

import re
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import httpx

from trafriend_api.application.ports.ranking import RankingMarketDataProvider
from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.universe import RankingAsset, RankingDailyBar

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.-]{1,16}$")


class AlpacaRankingDataProvider(RankingMarketDataProvider):
    """Alpaca asset-universe and batch daily-bar adapter for ranking builds."""

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        trading_base_url: str = "https://paper-api.alpaca.markets",
        data_base_url: str = "https://data.alpaca.markets",
        feed: str = "sip",
        timeout_seconds: float = 30.0,
        batch_size: int = 200,
        trading_client: Optional[httpx.Client] = None,
        data_client: Optional[httpx.Client] = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not key_id or not secret_key:
            raise ProviderAuthenticationError("Alpaca credentials are required")
        if feed not in {"sip", "iex"}:
            raise ValueError("ranking feed must be sip or iex")
        if batch_size < 1 or batch_size > 200:
            raise ValueError("ranking batch size must be between 1 and 200")
        self._headers = {
            "APCA-API-KEY-ID": key_id,
            "APCA-API-SECRET-KEY": secret_key,
        }
        self._trading_client = trading_client or httpx.Client(
            base_url=trading_base_url.rstrip("/"), timeout=timeout_seconds
        )
        self._data_client = data_client or httpx.Client(
            base_url=data_base_url.rstrip("/"), timeout=timeout_seconds
        )
        self._feed = feed
        self._batch_size = batch_size
        self._now = now

    @property
    def provider_code(self) -> str:
        return "alpaca"

    @property
    def source_feed(self) -> str:
        return self._feed

    def list_active_us_equities(self) -> tuple[RankingAsset, ...]:
        payload = self._request_json(
            self._trading_client,
            "/v2/assets",
            {"status": "active", "asset_class": "us_equity"},
        )
        if not isinstance(payload, list):
            raise ProviderUnavailableError("Alpaca returned a malformed asset response")
        assets = []
        for raw in payload:
            if not isinstance(raw, Mapping):
                continue
            symbol = str(raw.get("symbol", "")).strip().upper()
            name = str(raw.get("name", "")).strip()
            exchange = str(raw.get("exchange", "")).strip().upper()
            status = str(raw.get("status", "")).strip().lower()
            tradable = raw.get("tradable") is True
            if not SYMBOL_PATTERN.fullmatch(symbol) or not name:
                continue
            assets.append(
                RankingAsset(
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    status=status,
                    tradable=tradable,
                )
            )
        return tuple(sorted(assets, key=lambda asset: asset.symbol))

    def get_daily_ranking_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> tuple[RankingDailyBar, ...]:
        if start > end:
            raise ValueError("ranking bar start cannot follow end")
        normalized = tuple(
            dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip())
        )
        if not normalized:
            raise ValueError("at least one ranking symbol is required")
        if any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in normalized):
            raise ValueError("one or more ranking symbols have an invalid format")

        bars = []
        for offset in range(0, len(normalized), self._batch_size):
            batch = normalized[offset : offset + self._batch_size]
            bars.extend(self._get_batch(batch, start, end))
        return tuple(sorted(bars, key=lambda bar: (bar.symbol, bar.trading_date)))

    def _get_batch(
        self, symbols: Sequence[str], start: date, end: date
    ) -> list[RankingDailyBar]:
        start_at = datetime.combine(start, time.min, tzinfo=EASTERN)
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=EASTERN)
        page_token = None
        bars = []
        while True:
            params = {
                "symbols": ",".join(symbols),
                "timeframe": "1Day",
                "start": self._format_rfc3339(start_at),
                "end": self._format_rfc3339(end_at),
                "feed": self._feed,
                "adjustment": "raw",
                "sort": "asc",
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            payload = self._request_json(self._data_client, "/v2/stocks/bars", params)
            if not isinstance(payload, Mapping):
                raise ProviderUnavailableError("Alpaca returned a malformed bars response")
            raw_bars = payload.get("bars")
            if not isinstance(raw_bars, Mapping):
                raise ProviderUnavailableError("Alpaca returned a malformed bars response")
            for symbol in symbols:
                symbol_bars = raw_bars.get(symbol, ())
                if not isinstance(symbol_bars, list):
                    continue
                for raw_bar in symbol_bars:
                    parsed = self._parse_bar(symbol, raw_bar)
                    if parsed is not None and start <= parsed.trading_date <= end:
                        bars.append(parsed)
            token = payload.get("next_page_token")
            if not isinstance(token, str) or not token:
                break
            page_token = token
        return bars

    def _parse_bar(
        self, symbol: str, raw: object
    ) -> Optional[RankingDailyBar]:
        if not isinstance(raw, Mapping):
            return None
        try:
            vwap = Decimal(str(raw["vw"]))
            volume = Decimal(str(raw["v"]))
            timestamp = self._parse_rfc3339(str(raw["t"]))
            return RankingDailyBar(
                symbol=symbol,
                trading_date=timestamp.astimezone(EASTERN).date(),
                vwap=vwap,
                volume=volume,
                source=self.provider_code,
                source_feed=self._feed,
            )
        except (KeyError, InvalidOperation, ValueError):
            return None

    def _request_json(
        self,
        client: httpx.Client,
        path: str,
        params: Mapping[str, Any],
    ) -> object:
        response = None
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                response = client.get(path, params=params, headers=self._headers)
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = exc
                if attempt < 2:
                    time_module.sleep(2**attempt)
                    continue
                raise ProviderUnavailableError("Alpaca ranking request failed") from exc
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    retry_after = response.headers.get("Retry-After", "1")
                    try:
                        delay = min(max(float(retry_after), 0.25), 5.0)
                    except ValueError:
                        delay = 1.0
                    time_module.sleep(delay)
                    continue
            break
        if response is None:
            raise ProviderUnavailableError("Alpaca ranking request failed") from last_error
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "Alpaca credentials or market-data entitlement are invalid"
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("Alpaca ranking rate limit was reached")
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"Alpaca ranking request failed with HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Alpaca returned invalid JSON") from exc

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("current time must be timezone-aware")
        return timestamp.astimezone(UTC)

    @staticmethod
    def _parse_rfc3339(value: str) -> datetime:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        match = re.match(r"^(.*\.)(\d{7,})([+-]\d\d:\d\d)$", normalized)
        if match:
            normalized = f"{match.group(1)}{match.group(2)[:6]}{match.group(3)}"
        timestamp = datetime.fromisoformat(normalized)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("ranking bar timestamp must be timezone-aware")
        return timestamp.astimezone(UTC)

    @staticmethod
    def _format_rfc3339(timestamp: datetime) -> str:
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")

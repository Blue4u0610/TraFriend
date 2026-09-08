from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

import httpx

from trafriend_api.application.ports.profit_ratio import ProfitRatioCaptureProvider
from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.profit_ratio_daily import (
    ProfitRatioCaptureInput,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioSession,
)

EASTERN = ZoneInfo("America/New_York")
UTC = timezone.utc


class AlpacaProfitRatioCaptureProvider(ProfitRatioCaptureProvider):
    """SIP regular-price input capture, not an Alpaca Profit Ratio endpoint.

    Alpaca does not supply our validated cost seed/dated float. Those capabilities
    remain explicitly absent, so this adapter cannot manufacture real ratios.
    """

    def __init__(
        self,
        key_id: str,
        secret_key: str,
        instrument_ids: Mapping[str, str],
        base_url: str = "https://data.alpaca.markets",
        client: Optional[httpx.Client] = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not key_id or not secret_key:
            raise ProviderAuthenticationError("Alpaca credentials are required")
        self._headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key}
        self._ids = dict(instrument_ids)
        self._client = client or httpx.Client(base_url=base_url.rstrip("/"), timeout=30)
        self._owns_client = client is None
        self._now = now
        self._bars: dict[tuple[str, str, date], tuple[Decimal, Decimal]] = {}
        self._primed: Optional[tuple[date, date, frozenset[str]]] = None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def prime_history(self, symbols: Sequence[str], start: date, end: date) -> None:
        """Batch a bounded completed-history range once for both endpoint phases."""
        if end < start or (end - start).days > 400:
            raise ValueError("historical price input range must be at most 400 days")
        end_at = datetime.combine(end + timedelta(days=1), time.min, EASTERN)
        if end_at > self._now() - timedelta(minutes=20):
            raise ValueError("prime_history accepts completed historical dates only")
        self._load(symbols, start, end_at)
        self._primed = (start, end, frozenset(symbols))

    def get_capture_inputs(
        self, symbols: Sequence[str], session: ProfitRatioSession, phase: ProfitRatioPhase
    ) -> tuple[ProfitRatioCaptureInput, ...]:
        if not symbols or any(symbol not in self._ids for symbol in symbols):
            raise ValueError("capture symbols must belong to the stored QQQ stock universe")
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("capture clock must be timezone-aware")
        if now < session.instant(phase) + timedelta(minutes=20):
            raise ValueError("capture must wait for the phase publication delay")
        primed = self._primed
        if not (
            primed
            and primed[0] <= session.previous_trading_date
            and session.trading_date <= primed[1]
            and set(symbols) <= primed[2]
        ):
            # Daily bar O/C are eligible consolidated prices. The calendar instant
            # below identifies the observation phase, not an exchange auction print.
            self._load(
                symbols,
                session.previous_trading_date,
                session.instant(phase) + timedelta(minutes=1),
            )
        now = self._now()
        results = []
        for symbol in symbols:
            raw = self._bars.get(("raw", symbol, session.trading_date))
            adjusted = self._bars.get(("split", symbol, session.trading_date))
            previous = self._bars.get(("split", symbol, session.previous_trading_date))
            if raw is None:
                continue
            previous_close = None
            if adjusted is not None and previous is not None:
                # Transform prior close onto this day's raw share basis; this avoids
                # presenting a split as a price crash. Never dividend-adjust returns.
                previous_close = previous[1] * raw[0] / adjusted[0]
            price = raw[0] if phase == ProfitRatioPhase.OPEN else raw[1]
            results.append(
                ProfitRatioCaptureInput(
                    price=ProfitRatioPriceObservation(
                        instrument_id=self._ids[symbol],
                        symbol=symbol,
                        trading_date=session.trading_date,
                        phase=phase,
                        price=price,
                        previous_close=previous_close,
                        market_timestamp=session.instant(phase),
                        observed_at=now,
                        provider="alpaca",
                        source_feed="sip",
                    )
                )
            )
        return tuple(results)

    def _load(self, symbols: Sequence[str], start: date, end_at: datetime) -> None:
        if not symbols or len(symbols) > 200 or any(symbol not in self._ids for symbol in symbols):
            raise ValueError("capture requires 1-200 known QQQ equity symbols")
        request_start = datetime.combine(start, time.min, EASTERN)
        combined: dict[tuple[str, str, date], tuple[Decimal, Decimal]] = {}
        for adjustment in ("raw", "split"):
            token: Optional[str] = None
            tokens: set[str] = set()
            parsed: dict[tuple[str, str, date], tuple[Decimal, Decimal]] = {}
            while True:
                params = {
                    "symbols": ",".join(symbols),
                    "timeframe": "1Day",
                    "feed": "sip",
                    "adjustment": adjustment,
                    "sort": "asc",
                    "limit": "10000",
                    "start": datetime.combine(start, time.min, EASTERN).isoformat(),
                    "end": end_at.isoformat(),
                }
                if token:
                    params["page_token"] = token
                payload = self._request(params)
                bars = payload.get("bars")
                if not isinstance(bars, dict):
                    raise ProviderUnavailableError("malformed daily price response")
                for symbol in symbols:
                    values = bars.get(symbol, [])
                    if not isinstance(values, list):
                        raise ProviderUnavailableError("malformed daily price list")
                    for value in values:
                        try:
                            stamp = datetime.fromisoformat(str(value["t"]).replace("Z", "+00:00"))
                            if stamp.tzinfo is None or stamp.utcoffset() is None:
                                raise ValueError("missing timezone")
                            if not request_start <= stamp < end_at or stamp > self._now():
                                raise ValueError("unexpected source instant")
                            if stamp.astimezone(EASTERN).timetz().replace(tzinfo=None) != time.min:
                                raise ValueError("daily bars must start at New York midnight")
                            trading_date = stamp.astimezone(EASTERN).date()
                            prices = (Decimal(str(value["o"])), Decimal(str(value["c"])))
                            if any(not price.is_finite() or price <= 0 for price in prices):
                                raise ValueError("invalid price")
                        except (KeyError, TypeError, ValueError, InvalidOperation):
                            raise ProviderUnavailableError("malformed daily price bar") from None
                        if not start <= trading_date <= end_at.astimezone(EASTERN).date():
                            raise ProviderUnavailableError("unexpected daily price date")
                        key = (adjustment, symbol, trading_date)
                        if key in parsed:
                            raise ProviderUnavailableError("duplicate daily price bar")
                        parsed[key] = prices
                next_token = payload.get("next_page_token")
                if not next_token:
                    break
                if not isinstance(next_token, str) or next_token in tokens or len(tokens) >= 500:
                    raise ProviderUnavailableError("invalid price pagination")
                tokens.add(next_token)
                token = next_token
            combined.update(parsed)
        # A missing symbol in a fresh response must not reuse an older cached bar.
        self._bars = {
            key: value
            for key, value in self._bars.items()
            if not (key[1] in symbols and start <= key[2] <= end_at.astimezone(EASTERN).date())
        }
        self._bars.update(combined)

    def _request(self, params: Mapping[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get("/v2/stocks/bars", params=params, headers=self._headers)
        except httpx.HTTPError:
            raise ProviderUnavailableError("Alpaca price request failed") from None
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError("Alpaca SIP historical data entitlement required")
        if response.status_code == 429:
            raise ProviderRateLimitError("Alpaca price request rate limited")
        if response.status_code >= 400:
            raise ProviderUnavailableError("Alpaca price data unavailable")
        try:
            payload = response.json()
        except ValueError:
            raise ProviderUnavailableError("malformed price JSON") from None
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("malformed price response")
        return payload

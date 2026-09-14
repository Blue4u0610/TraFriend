"""Futu OpenD adapter for the provider-reported chip profit ratio."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from trafriend_api.application.ports.profit_ratio import ProfitRatioCaptureProvider
from trafriend_api.application.services.profit_ratio import (
    FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY,
)
from trafriend_api.domain.errors import ProviderUnavailableError
from trafriend_api.domain.profit_ratio_daily import (
    ProfitRatioCaptureInput,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioSession,
)

EASTERN = ZoneInfo("America/New_York")
UTC = timezone.utc
SOURCE_FEED = "stock-screen-v2+market-snapshot"
SCREEN_PAGE_SIZE = 200
MAX_SCREEN_PAGES = 10


def _default_context_factory(host: str, port: int) -> Any:
    try:
        from futu import OpenQuoteContext
    except ImportError as exc:  # pragma: no cover - exercised without optional dependency
        raise ProviderUnavailableError("the optional Futu SDK is not installed") from exc
    try:
        return OpenQuoteContext(host=host, port=port)
    except Exception as exc:
        raise ProviderUnavailableError("Futu OpenD is unavailable") from exc


class FutuOpenDProfitRatioProvider(ProfitRatioCaptureProvider):
    """Read current QQQ chip ratios and price timestamps from one local OpenD."""

    def __init__(
        self,
        host: str,
        port: int,
        instrument_ids: Mapping[str, str],
        quality: str = "UNKNOWN",
        context_factory: Callable[[str, int], Any] = _default_context_factory,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not host.strip() or not 1 <= port <= 65535:
            raise ValueError("a valid local Futu OpenD host and port are required")
        if quality not in {"REALTIME", "DELAYED", "UNKNOWN"}:
            raise ValueError("Futu quality must be REALTIME, DELAYED, or UNKNOWN")
        self._host = host
        self._port = port
        self._ids = {
            symbol.upper(): instrument_id for symbol, instrument_id in instrument_ids.items()
        }
        self._quality = quality
        self._context_factory = context_factory
        self._now = now
        self._context: Optional[Any] = None

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None

    def get_capture_inputs(
        self,
        symbols: Sequence[str],
        session: ProfitRatioSession,
        phase: ProfitRatioPhase,
    ) -> tuple[ProfitRatioCaptureInput, ...]:
        requested = tuple(dict.fromkeys(symbol.upper() for symbol in symbols))
        if (
            not requested
            or len(requested) > 200
            or any(symbol not in self._ids for symbol in requested)
        ):
            raise ValueError("capture requires 1-200 stored QQQ equity symbols")
        observed_at = self._utc_now()
        context = self._get_context()
        try:
            ratios = self._ratios(context, requested)
            codes = [f"US.{symbol}" for symbol in requested if symbol in ratios]
            snapshots = self._snapshots(context, codes)
        except ProviderUnavailableError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Futu OpenD returned an unusable response") from exc

        captures = []
        for symbol in requested:
            ratio = ratios.get(symbol)
            snapshot = snapshots.get(symbol)
            if ratio is None or snapshot is None:
                continue
            snapshot_timestamp, last_price, open_price, previous_close = snapshot
            earliest_snapshot = (
                session.opened_at
                if phase == ProfitRatioPhase.OPEN
                else session.closed_at - timedelta(minutes=15)
            )
            if (
                snapshot_timestamp > observed_at
                or snapshot_timestamp < earliest_snapshot
                or snapshot_timestamp.astimezone(EASTERN).date() != session.trading_date
            ):
                continue
            price = open_price if phase == ProfitRatioPhase.OPEN else last_price
            captures.append(
                ProfitRatioCaptureInput(
                    price=ProfitRatioPriceObservation(
                        instrument_id=self._ids[symbol],
                        symbol=symbol,
                        trading_date=session.trading_date,
                        phase=phase,
                        price=price,
                        previous_close=previous_close,
                        # This is the calendar phase being evaluated. The source
                        # snapshot update time is used above only to reject stale input.
                        market_timestamp=session.instant(phase),
                        observed_at=observed_at,
                        provider="futu",
                        source_feed=SOURCE_FEED,
                    ),
                    quality=self._quality,
                    reported_ratio=ratio,
                    methodology_key=FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY.id,
                    methodology_version=FUTU_CHIPS_PROFIT_RATIO_METHODOLOGY.version,
                )
            )
        return tuple(captures)

    def _get_context(self) -> Any:
        if self._context is None:
            self._context = self._context_factory(self._host, self._port)
        return self._context

    def _ratios(self, context: Any, requested: Sequence[str]) -> dict[str, Decimal]:
        try:
            from futu import (
                RET_OK,
                BasicProperty,
                FeaturedProperty,
                ScrMarket,
                ScrSortDir,
                SimpleField,
                SimpleProperty,
                StockScreenRequest,
            )
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ProviderUnavailableError("the optional Futu SDK is not installed") from exc

        results: dict[str, Decimal] = {}
        requested_set = set(requested)
        for page_number in range(MAX_SCREEN_PAGES):
            request = StockScreenRequest()
            request.page_from = page_number * SCREEN_PAGE_SIZE
            request.page_count = SCREEN_PAGE_SIZE
            request.add_simple_field(SimpleField.MARKET, [ScrMarket.US])
            request.add_featured_property(
                FeaturedProperty.CHIPS_PROFIT_RATIO,
                intervals=[
                    {
                        "filterMin": {"value": 0.0, "includes": True},
                        "filterMax": {"value": 1.0, "includes": True},
                    }
                ],
            )
            request.add_retrieve_basic(BasicProperty.CODE)
            request.add_retrieve_featured(FeaturedProperty.CHIPS_PROFIT_RATIO)
            # Stock Screening V2's INDEX_ID filter currently returns an empty U.S.
            # result from OpenD. Sorting by market cap keeps the bounded scan small;
            # membership still comes exclusively from TraFriend's dated QQQ catalog.
            request.set_sort(
                direction=ScrSortDir.DESC,
                property_type="simple",
                property_params={"name": int(SimpleProperty.MARKET_CAP)},
            )
            ret, payload = context.get_stock_screen(request)
            if ret != RET_OK or not isinstance(payload, tuple) or len(payload) != 3:
                raise ProviderUnavailableError("Futu stock screening is unavailable")
            last_page, _all_count, items = payload
            if not isinstance(items, list):
                raise ProviderUnavailableError("Futu stock screening response was incomplete")

            for item in items:
                symbol: Optional[str] = None
                ratio: Optional[Decimal] = None
                for result in item.get("results", []):
                    prop = result.get("property", {})
                    if result.get("type") == "basic" and prop.get("name") == int(
                        BasicProperty.CODE
                    ):
                        symbol = str(result.get("sval", "")).removeprefix("US.").upper()
                    elif result.get("type") == "featured" and prop.get("name") == int(
                        FeaturedProperty.CHIPS_PROFIT_RATIO
                    ):
                        ratio = self._ratio(result.get("dval"))
                if symbol in requested_set and ratio is not None:
                    results[symbol] = ratio

            if requested_set.issubset(results) or last_page:
                break
        return results

    @staticmethod
    def _snapshots(
        context: Any, codes: Sequence[str]
    ) -> dict[str, tuple[datetime, Decimal, Decimal, Optional[Decimal]]]:
        if not codes:
            return {}
        try:
            from futu import RET_OK
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ProviderUnavailableError("the optional Futu SDK is not installed") from exc
        ret, frame = context.get_market_snapshot(list(codes))
        if ret != RET_OK or frame is None:
            raise ProviderUnavailableError("Futu market snapshots are unavailable")
        results = {}
        for _index, row in frame.iterrows():
            try:
                symbol = str(row["code"]).removeprefix("US.").upper()
                snapshot_timestamp = datetime.fromisoformat(str(row["update_time"])).replace(
                    tzinfo=EASTERN
                ).astimezone(UTC)
                last_price = Decimal(str(row["last_price"]))
                open_price = Decimal(str(row["open_price"]))
                previous_raw = Decimal(str(row["prev_close_price"]))
                previous_close = (
                    previous_raw if previous_raw.is_finite() and previous_raw > 0 else None
                )
                if (
                    not last_price.is_finite()
                    or last_price <= 0
                    or not open_price.is_finite()
                    or open_price <= 0
                ):
                    continue
            except (KeyError, TypeError, ValueError, InvalidOperation):
                continue
            results[symbol] = (
                snapshot_timestamp,
                last_price,
                open_price,
                previous_close,
            )
        return results

    @staticmethod
    def _ratio(value: object) -> Optional[Decimal]:
        try:
            ratio = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        if not ratio.is_finite() or not Decimal(0) <= ratio <= Decimal(1):
            return None
        return ratio

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capture clock must return a timezone-aware instant")
        return value.astimezone(UTC)

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, Sequence, Tuple

from trafriend_api.application.ports.daily_close import DailyCloseMarketDataProvider
from trafriend_api.application.ports.market_data import MarketDataProvider
from trafriend_api.application.ports.overnight_market_data import (
    OvernightMarketDataProvider,
)
from trafriend_api.domain.daily_close import DailyCloseBar, DailyCloseQuality
from trafriend_api.domain.errors import (
    ProviderUnavailableError,
    ResourceNotFoundError,
    UnsupportedFeatureError,
)
from trafriend_api.domain.models import (
    Instrument,
    InstrumentCapabilities,
    LeveragedRelationship,
    PricePoint,
    ProfitRatioHistory,
    ProfitRatioMethodology,
    ProfitRatioPoint,
)
from trafriend_api.domain.overnight import (
    DataQuality,
    OvernightBar,
    OvernightQuote,
    PriceBasis,
    ProviderCapabilities,
)

UTC = timezone.utc


def _at(year: int, month: int, day: int, hour: int = 20) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


class MockMarketDataProvider(
    MarketDataProvider, OvernightMarketDataProvider, DailyCloseMarketDataProvider
):
    """Deterministic data source for local development and ordinary CI."""

    scenario_codes = (
        "normal",
        "inverse",
        "stale",
        "missing",
        "partial",
        "missing_underlying",
        "holiday",
        "boundary",
        "missing_open",
        "provider_failure",
        "delayed",
        "out_of_sync",
    )

    def __init__(
        self,
        scenario_code: str = "normal",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if scenario_code not in self.scenario_codes:
            raise ValueError(f"unknown mock scenario: {scenario_code}")
        self.scenario_code = scenario_code
        self._instruments = self._build_instruments()
        self._relationships = self._build_relationships()
        self._profit_histories = self._build_profit_histories()
        self._now = now
        self.overnight_request_log: list[Tuple[str, Tuple[str, ...]]] = []
        self.daily_close_request_log: list[
            Tuple[Tuple[str, ...], date, date]
        ] = []

    @property
    def provider_code(self) -> str:
        return "mock"

    @property
    def source_feed(self) -> str:
        return "mock-boats"

    @property
    def daily_close_feed(self) -> str:
        return "mock-regular-close"

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
        return self.get_overnight_snapshot(symbols, datetime.now(UTC))

    def get_overnight_snapshot(
        self, symbols: Sequence[str], timestamp: datetime
    ) -> Sequence[OvernightQuote]:
        normalized = tuple(symbol.strip().upper() for symbol in symbols)
        self.overnight_request_log.append(("snapshot", normalized))
        if self.scenario_code == "provider_failure":
            raise ProviderUnavailableError("mock provider is unavailable")
        if self.scenario_code in {"missing", "holiday"}:
            return ()

        prices = self._overnight_prices()
        quotes = []
        for index, symbol in enumerate(normalized):
            if symbol not in prices:
                continue
            if self.scenario_code == "partial" and index > 0:
                continue
            if self.scenario_code == "missing_underlying" and index == 0:
                continue
            market_timestamp = timestamp + timedelta(seconds=1)
            quality = DataQuality.REALTIME
            if self.scenario_code == "stale":
                market_timestamp = timestamp - timedelta(minutes=10)
            elif self.scenario_code == "delayed":
                quality = DataQuality.DELAYED
            elif self.scenario_code == "out_of_sync" and index > 0:
                market_timestamp = timestamp + timedelta(seconds=20)
            quotes.append(
                OvernightQuote(
                    symbol=symbol,
                    price=prices[symbol][1],
                    market_timestamp=market_timestamp,
                    observed_at=timestamp + timedelta(seconds=30),
                    source=self.provider_code,
                    source_feed=self.source_feed,
                    quality=quality,
                    price_basis=PriceBasis.QUOTE_MIDPOINT,
                )
            )
        return tuple(quotes)

    def get_overnight_bars(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        timeframe: str,
    ) -> Sequence[OvernightBar]:
        if timeframe != "1Min":
            raise ValueError("mock overnight provider supports only 1Min bars")
        normalized = tuple(symbol.strip().upper() for symbol in symbols)
        self.overnight_request_log.append(("bars", normalized))
        if self.scenario_code == "provider_failure":
            raise ProviderUnavailableError("mock provider is unavailable")
        if self.scenario_code in {"missing", "holiday"}:
            return ()

        prices = self._overnight_prices()
        starts_at = (
            start + timedelta(minutes=2)
            if self.scenario_code == "missing_open"
            else start
        )
        if starts_at >= end:
            return ()
        bars = []
        for index, symbol in enumerate(normalized):
            if symbol not in prices:
                continue
            if self.scenario_code == "partial" and index > 0:
                continue
            if self.scenario_code == "missing_underlying" and index == 0:
                continue
            quality = (
                DataQuality.DELAYED
                if self.scenario_code == "delayed"
                else DataQuality.REALTIME
            )
            bars.append(
                OvernightBar(
                    symbol=symbol,
                    open_price=prices[symbol][0],
                    starts_at=starts_at,
                    observed_at=starts_at + timedelta(seconds=30),
                    source=self.provider_code,
                    source_feed=self.source_feed,
                    quality=quality,
                )
            )
        return tuple(bars)

    def get_daily_close_bars(
        self, symbols: Sequence[str], start: date, end: date
    ) -> Sequence[DailyCloseBar]:
        if start > end:
            raise ValueError("daily bar start cannot follow end")
        normalized = tuple(symbol.strip().upper() for symbol in symbols)
        self.daily_close_request_log.append((normalized, start, end))
        if self.scenario_code == "provider_failure":
            raise ProviderUnavailableError("mock provider is unavailable")
        if self.scenario_code in {"missing", "holiday"}:
            return ()

        trading_date = (
            end - timedelta(days=1) if self.scenario_code == "stale" else end
        )
        prices = self._daily_close_prices()
        observed_at = self._now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("mock current time must be timezone-aware")
        bars = []
        for index, symbol in enumerate(normalized):
            if symbol not in prices:
                continue
            if self.scenario_code == "partial" and index > 0:
                continue
            if self.scenario_code == "missing_underlying" and index == 0:
                continue
            close = (
                Decimal("0.01000000")
                if self.scenario_code == "boundary"
                else prices[symbol]
            )
            bars.append(
                DailyCloseBar(
                    symbol=symbol,
                    trading_date=trading_date,
                    close=close,
                    market_timestamp=datetime.combine(
                        trading_date, datetime.min.time(), tzinfo=UTC
                    ).replace(hour=4),
                    observed_at=observed_at.astimezone(UTC),
                    source=self.provider_code,
                    source_feed=self.daily_close_feed,
                    currency="USD",
                    quality=(
                        DailyCloseQuality.STALE
                        if self.scenario_code == "stale"
                        else DailyCloseQuality.REALTIME
                    ),
                )
            )
        return tuple(bars)

    @staticmethod
    def _daily_close_prices() -> Dict[str, Decimal]:
        return {
            "SNDK": Decimal("1740"),
            "SNXX": Decimal("17.36"),
            "NVDA": Decimal("170.00"),
            "NVDL": Decimal("80.00"),
            "TSLA": Decimal("340.00"),
            "TSLL": Decimal("18.00"),
            "QQQ": Decimal("480.00"),
            "QLD": Decimal("120.00"),
            "TQQQ": Decimal("82.50"),
            "SQQQ": Decimal("31.20"),
            "SOXX": Decimal("250.00"),
            "SOXL": Decimal("45.00"),
            "SOXS": Decimal("20.00"),
        }

    @staticmethod
    def _overnight_prices() -> Dict[str, Tuple[Decimal, Decimal]]:
        return {
            "SNDK": (Decimal("1702.35"), Decimal("1704.20")),
            "SNXX": (Decimal("20.02"), Decimal("20.08")),
            "NVDA": (Decimal("170.00"), Decimal("170.15")),
            "NVDL": (Decimal("80.00"), Decimal("80.14")),
            "TSLA": (Decimal("340.00"), Decimal("340.50")),
            "TSLL": (Decimal("18.00"), Decimal("18.04")),
            "QQQ": (Decimal("480.00"), Decimal("480.20")),
            "QLD": (Decimal("120.00"), Decimal("120.10")),
            "TQQQ": (Decimal("82.50"), Decimal("82.62")),
            "SQQQ": (Decimal("31.20"), Decimal("31.16")),
            "SOXX": (Decimal("250.00"), Decimal("250.30")),
            "SOXL": (Decimal("45.00"), Decimal("45.12")),
            "SOXS": (Decimal("20.00"), Decimal("19.95")),
        }

    def search_instruments(self, query: str, limit: int) -> Sequence[Instrument]:
        normalized_query = query.strip().upper()
        matches = [
            instrument
            for instrument in self._instruments.values()
            if normalized_query in instrument.symbol
            or normalized_query in instrument.name.upper()
        ]
        matches.sort(
            key=lambda instrument: (
                not instrument.symbol.startswith(normalized_query),
                instrument.symbol,
            )
        )
        return tuple(matches[:limit])

    def get_instrument(self, instrument_id: str) -> Instrument:
        try:
            return self._instruments[instrument_id]
        except KeyError as exc:
            raise ResourceNotFoundError("instrument was not found") from exc

    def get_leveraged_relationships(
        self, instrument_id: str
    ) -> Sequence[LeveragedRelationship]:
        selected = self.get_instrument(instrument_id)
        if selected.instrument_type == "leveraged_etf":
            selected_relationship = next(
                (
                    relationship
                    for relationship in self._relationships.values()
                    if relationship.leveraged_product.id == instrument_id
                ),
                None,
            )
            if selected_relationship is None:
                return ()
            underlying_id = selected_relationship.underlying.id
        else:
            underlying_id = instrument_id

        return tuple(
            relationship
            for relationship in self._relationships.values()
            if relationship.underlying.id == underlying_id
        )

    def get_relationship(self, relationship_id: str) -> LeveragedRelationship:
        try:
            return self._relationships[relationship_id]
        except KeyError as exc:
            raise ResourceNotFoundError("leveraged product relationship was not found") from exc

    def get_profit_ratio_history(
        self, instrument_id: str, start: date, end: date
    ) -> ProfitRatioHistory:
        instrument = self.get_instrument(instrument_id)
        if not instrument.capabilities.profit_ratio:
            raise UnsupportedFeatureError(
                "Profit Ratio is not available for this mock instrument"
            )
        try:
            history = self._profit_histories[instrument_id]
        except KeyError as exc:
            raise UnsupportedFeatureError(
                "Profit Ratio is not available for this mock instrument"
            ) from exc

        ratio_points = tuple(
            point for point in history.ratio_points if start <= point.trading_date <= end
        )
        price_points = tuple(
            point for point in history.price_points if start <= point.trading_date <= end
        )
        return ProfitRatioHistory(
            instrument=history.instrument,
            methodology=history.methodology,
            ratio_points=ratio_points,
            price_points=price_points,
            provider=history.provider,
            as_of=history.as_of,
        )

    @staticmethod
    def _build_instruments() -> Dict[str, Instrument]:
        has_both = InstrumentCapabilities(
            leveraged_relationships=True, profit_ratio=True
        )
        leveraged_only = InstrumentCapabilities(
            leveraged_relationships=True, profit_ratio=False
        )
        return {
            "ins_qqq_xnas": Instrument(
                id="ins_qqq_xnas",
                symbol="QQQ",
                name="Invesco QQQ Trust",
                instrument_type="etf",
                exchange_mic="XNAS",
                currency="USD",
                status="active",
                capabilities=has_both,
            ),
            "ins_tqqq_xnas": Instrument(
                id="ins_tqqq_xnas",
                symbol="TQQQ",
                name="ProShares UltraPro QQQ",
                instrument_type="leveraged_etf",
                exchange_mic="XNAS",
                currency="USD",
                status="active",
                capabilities=leveraged_only,
            ),
            "ins_sqqq_xnas": Instrument(
                id="ins_sqqq_xnas",
                symbol="SQQQ",
                name="ProShares UltraPro Short QQQ",
                instrument_type="leveraged_etf",
                exchange_mic="XNAS",
                currency="USD",
                status="active",
                capabilities=leveraged_only,
            ),
            "ins_nvda_xnas": Instrument(
                id="ins_nvda_xnas",
                symbol="NVDA",
                name="NVIDIA Corporation",
                instrument_type="stock",
                exchange_mic="XNAS",
                currency="USD",
                status="active",
                capabilities=has_both,
            ),
            "ins_nvdl_xnas": Instrument(
                id="ins_nvdl_xnas",
                symbol="NVDL",
                name="GraniteShares 2x Long NVDA Daily ETF",
                instrument_type="leveraged_etf",
                exchange_mic="XNAS",
                currency="USD",
                status="active",
                capabilities=leveraged_only,
            ),
        }

    def _build_relationships(self) -> Dict[str, LeveragedRelationship]:
        relationships = (
            LeveragedRelationship(
                id="rel_qqq_tqqq_3x",
                underlying=self._instruments["ins_qqq_xnas"],
                leveraged_product=self._instruments["ins_tqqq_xnas"],
                leverage_factor=Decimal("3"),
                objective_period="daily",
                effective_from=date(2010, 2, 9),
            ),
            LeveragedRelationship(
                id="rel_qqq_sqqq_n3x",
                underlying=self._instruments["ins_qqq_xnas"],
                leveraged_product=self._instruments["ins_sqqq_xnas"],
                leverage_factor=Decimal("-3"),
                objective_period="daily",
                effective_from=date(2010, 2, 9),
            ),
            LeveragedRelationship(
                id="rel_nvda_nvdl_2x",
                underlying=self._instruments["ins_nvda_xnas"],
                leveraged_product=self._instruments["ins_nvdl_xnas"],
                leverage_factor=Decimal("2"),
                objective_period="daily",
                effective_from=date(2023, 12, 4),
            ),
        )
        return {relationship.id: relationship for relationship in relationships}

    def _build_profit_histories(self) -> Dict[str, ProfitRatioHistory]:
        methodology = ProfitRatioMethodology(
            id="mock-cost-basis-estimate",
            version="1",
            display_name="Mock estimated profitable cost-basis ratio",
        )
        values = (
            (date(2026, 8, 27), "0.702", "174.42"),
            (date(2026, 8, 28), "0.721", "176.38"),
            (date(2026, 8, 31), "0.715", "175.11"),
            (date(2026, 9, 1), "0.748", "178.06"),
            (date(2026, 9, 2), "0.763", "177.52"),
            (date(2026, 9, 3), "0.771", "168.37"),
            (date(2026, 9, 4), "0.826", "170.00"),
        )
        ratio_points = tuple(
            ProfitRatioPoint(
                timestamp=_at(day.year, day.month, day.day),
                trading_date=day,
                ratio=Decimal(ratio),
                quality="final",
            )
            for day, ratio, _ in values
        )
        price_points = tuple(
            PricePoint(
                timestamp=_at(day.year, day.month, day.day),
                trading_date=day,
                close=Decimal(close),
                adjustment="unadjusted",
            )
            for day, _, close in values
        )
        return {
            "ins_nvda_xnas": ProfitRatioHistory(
                instrument=self._instruments["ins_nvda_xnas"],
                methodology=methodology,
                ratio_points=ratio_points,
                price_points=price_points,
                provider=self.provider_code,
                as_of=_at(2026, 9, 5, 2),
            )
        }

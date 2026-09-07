from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable, Container

from trafriend_api.application.ports.market_data import LeveragedRelationshipCatalog
from trafriend_api.application.ports.ranking import (
    MarketRankingRepository,
    RankingMarketDataProvider,
    RankingSessionCalendar,
)
from trafriend_api.domain.universe import (
    MarketRanking,
    RankingAsset,
    RankingBuildReport,
    RankingCompletenessStatus,
    RankingPeriodStatus,
    RankingType,
)

UTC = timezone.utc
LISTED_EXCHANGES = frozenset({"AMEX", "ARCA", "BATS", "NASDAQ", "NYSE", "NYSEARCA"})
EXCLUDED_NAME_PATTERN = re.compile(
    r"\b(?:ETF|ETN|EXCHANGE[- ]TRADED|FUND|PORTFOLIO|WARRANTS?|RIGHTS?|"
    r"UNITS?|PREFERRED|ACQUISITION CORP(?:ORATION)?|BLANK CHECK)\b",
    re.IGNORECASE,
)
LEVERAGED_NAME_PATTERN = re.compile(
    r"(?:\b(?:2X|3X|ULTRA|ULTRAPRO)\b.*\b(?:BULL|BEAR|SHORT|DAILY)\b|"
    r"\b(?:BULL|BEAR|SHORT|DAILY)\b.*\b(?:2X|3X|ULTRA|ULTRAPRO)\b)",
    re.IGNORECASE,
)
ASSET_MANAGER_TRUST_PATTERN = re.compile(
    r"\b(?:SPDR|ISHARES|INVESCO|PROSHARES|DIREXION|VANGUARD|GRAYSCALE)\b"
    r".*\bTRUST\b",
    re.IGNORECASE,
)
EXCLUDED_SYMBOL_SUFFIXES = (".WS", ".WT", ".RT", ".R", ".U")


class MarketRankingService:
    """Build a reproducible full-universe ranking from authoritative daily bars."""

    def __init__(
        self,
        provider: RankingMarketDataProvider,
        calendar: RankingSessionCalendar,
        repository: MarketRankingRepository,
        catalog: LeveragedRelationshipCatalog,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._calendar = calendar
        self._repository = repository
        self._catalog = catalog
        self._now = now

    def build_september_2026(self) -> RankingBuildReport:
        calculated_at = self._utc_now()
        completed_dates = tuple(
            self._calendar.completed_trading_dates_in_month(
                calculated_at, year=2026, month=9
            )
        )
        if not completed_dates:
            raise ValueError("September 2026 has no completed trading sessions yet")

        excluded_symbols = self._curated_etf_symbols()
        assets = tuple(
            asset
            for asset in self._provider.list_active_us_equities()
            if is_eligible_operating_equity(asset, excluded_symbols)
        )
        if not assets:
            raise ValueError("the provider returned no eligible U.S. equity candidates")

        bars = self._provider.get_daily_ranking_bars(
            tuple(asset.symbol for asset in assets),
            min(completed_dates),
            max(completed_dates),
        )
        bars_by_symbol = defaultdict(list)
        for bar in bars:
            bars_by_symbol[bar.symbol].append(bar)

        expected_dates = set(completed_dates)
        complete: list[tuple[RankingAsset, Decimal]] = []
        for asset in assets:
            symbol_bars = bars_by_symbol[asset.symbol]
            observed_dates = [bar.trading_date for bar in symbol_bars]
            if (
                set(observed_dates) != expected_dates
                or len(observed_dates) != len(expected_dates)
                or any(
                    bar.source != self._provider.provider_code
                    or bar.source_feed != self._provider.source_feed
                    for bar in symbol_bars
                )
            ):
                continue
            dollar_volume = sum(
                (bar.vwap * bar.volume for bar in symbol_bars),
                start=Decimal("0"),
            )
            complete.append((asset, dollar_volume))

        ranked = sorted(complete, key=lambda item: (-item[1], item[0].symbol))[:100]
        if len(ranked) < 100:
            raise ValueError("fewer than 100 complete U.S. equity candidates were available")

        source = (
            f"{self._provider.provider_code}:{self._provider.source_feed}:"
            "daily_vwap_x_volume"
        )
        period_status = (
            RankingPeriodStatus.FINAL
            if max(completed_dates) == date(2026, 9, 30)
            else RankingPeriodStatus.SEPTEMBER_TO_DATE
        )
        rows = tuple(
            MarketRanking(
                ranking_period="2026-09",
                period_start=min(completed_dates),
                period_end=max(completed_dates),
                period_status=period_status,
                ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
                rank=rank,
                symbol=asset.symbol,
                display_name=asset.name,
                exchange=asset.exchange,
                trading_metric=dollar_volume,
                calculated_at=calculated_at,
                source=source,
                completeness_status=RankingCompletenessStatus.COMPLETE,
                sessions_observed=len(completed_dates),
                sessions_expected=len(completed_dates),
            )
            for rank, (asset, dollar_volume) in enumerate(ranked, start=1)
        )
        persisted = self._repository.replace_verified_rows(rows)
        return RankingBuildReport(
            ranking_period="2026-09",
            completed_trading_dates=completed_dates,
            candidate_assets=len(assets),
            complete_assets=len(complete),
            incomplete_assets=len(assets) - len(complete),
            persisted_rows=persisted,
            rows=rows,
        )

    def _curated_etf_symbols(self) -> frozenset[str]:
        excluded = set()
        for underlying in self._catalog.list_underlyings():
            if underlying.instrument_type != "stock":
                excluded.add(underlying.symbol)
            for relationship in self._catalog.get_leveraged_relationships(underlying.id):
                excluded.add(relationship.leveraged_product.symbol)
        return frozenset(excluded)

    def _utc_now(self) -> datetime:
        timestamp = self._now()
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("ranking calculation time must be timezone-aware")
        return timestamp.astimezone(UTC)


def is_eligible_operating_equity(
    asset: RankingAsset, excluded_symbols: Container[str]
) -> bool:
    """Apply only exclusions supported by Alpaca's asset fields or explicit names."""

    if asset.status != "active" or not asset.tradable:
        return False
    if asset.exchange not in LISTED_EXCHANGES:
        return False
    if asset.symbol in excluded_symbols:
        return False
    if asset.symbol.endswith(EXCLUDED_SYMBOL_SUFFIXES):
        return False
    if EXCLUDED_NAME_PATTERN.search(asset.name):
        return False
    if LEVERAGED_NAME_PATTERN.search(asset.name):
        return False
    if ASSET_MANAGER_TRUST_PATTERN.search(asset.name):
        return False
    return True

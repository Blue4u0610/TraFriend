from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.daily_close import DailyCloseAnchor, DailyCloseAnchorStatus
from trafriend_api.domain.errors import MarketDataProviderError, ProviderAuthenticationError
from trafriend_api.domain.models import (
    Instrument,
    InstrumentCapabilities,
    LeveragedRelationship,
)
from trafriend_api.domain.universe import DEFAULT_SUPPORTED_UNIVERSE
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.market_data.alpaca import AlpacaMarketDataProvider
from trafriend_api.infrastructure.persistence import InMemoryDailyCloseAnchorRepository
from trafriend_api.settings import Settings

UTC = timezone.utc
PAIR_CASES = (
    ("rel_sndk_snxx_2x", "SNDK", "SNXX", Decimal("1.05")),
    ("rel_qqq_tqqq_3x", "QQQ", "TQQQ", Decimal("1.02")),
)


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
        daily_bars_feed=settings.alpaca_daily_bars_feed,
        daily_bars_quality=settings.alpaca_daily_bars_quality,
        timeout_seconds=30,
    )


def _signed_leverage(underlying: str, product: str) -> Decimal:
    group = DEFAULT_SUPPORTED_UNIVERSE.group_for(underlying)
    for candidate in group.leveraged_products:
        if candidate.symbol == product:
            return candidate.signed_leverage
    raise ValueError(f"{underlying}/{product} is not a configured relationship")


def _relationship(
    relationship_id: str, underlying: str, product: str
) -> LeveragedRelationship:
    capabilities = InstrumentCapabilities(
        leveraged_relationships=True, profit_ratio=False
    )
    return LeveragedRelationship(
        id=relationship_id,
        underlying=Instrument(
            id=f"diagnostic_{underlying.lower()}",
            symbol=underlying,
            name=underlying,
            instrument_type="etf" if underlying != "SNDK" else "stock",
            exchange_mic="XNAS",
            currency="USD",
            status="active",
            capabilities=capabilities,
        ),
        leveraged_product=Instrument(
            id=f"diagnostic_{product.lower()}",
            symbol=product,
            name=product,
            instrument_type="leveraged_etf",
            exchange_mic="XNAS",
            currency="USD",
            status="active",
            capabilities=capabilities,
        ),
        leverage_factor=_signed_leverage(underlying, product),
        objective_period="daily",
        effective_from=date.min,
    )


def _print_anchor(anchor: DailyCloseAnchor) -> None:
    print(f"\n{anchor.relationship_id}")
    print(f"Anchor Type: {anchor.anchor_type}")
    print(f"Trading Date: {anchor.trading_date.isoformat()}")
    print(f"Session Closed At: {anchor.session_closed_at.isoformat()}")
    print(f"Anchor Status: {anchor.status.value}")
    for label, value in (
        ("Underlying", anchor.underlying),
        ("Leveraged Product", anchor.leveraged_product),
    ):
        print(f"{label} Symbol: {value.symbol}")
        print(f"{label} Close: {value.close if value.close is not None else 'N/A'}")
        print(
            f"{label} Market Timestamp: "
            f"{value.market_timestamp.isoformat() if value.market_timestamp else 'N/A'}"
        )
        print(f"{label} Observed At: {value.observed_at.isoformat()}")
        print(f"{label} Feed: {value.source_feed}")
        print(f"{label} Currency: {value.currency}")
        print(f"{label} Quality: {value.quality.value}")
        print(f"{label} Status: {value.status.value}")


def _print_calculation(
    anchor: DailyCloseAnchor,
    relationship: LeveragedRelationship,
    target_multiple: Decimal,
) -> None:
    if anchor.status != DailyCloseAnchorStatus.COMPLETE:
        print("Calculation: UNAVAILABLE")
        return
    assert anchor.underlying.close is not None
    target = anchor.underlying.close * target_multiple
    result = calculate_theoretical_target(
        relationship=relationship,
        anchor=anchor,
        input_side="underlying",
        target_price=target,
    )
    print(f"Underlying Target: {target}")
    print(f"Underlying Return: {result.underlying_return}")
    print(f"Leveraged Return: {result.leveraged_return}")
    print(f"Leveraged Theoretical Target: {result.theoretical_target_price}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    if argv:
        print("This diagnostic accepts no arguments.", file=sys.stderr)
        return 2
    try:
        provider = _build_provider(Settings.from_environment())
        service = DailyCloseAnchorService(
            provider=provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryDailyCloseAnchorRepository(),
            now=lambda: datetime.now(UTC),
        )
        complete = True
        for relationship_id, underlying, product, target_multiple in PAIR_CASES:
            anchor = service.capture(relationship_id, underlying, product)
            _print_anchor(anchor)
            _print_calculation(
                anchor,
                _relationship(relationship_id, underlying, product),
                target_multiple,
            )
            complete = complete and anchor.status == DailyCloseAnchorStatus.COMPLETE
        return 0 if complete else 1
    except (MarketDataProviderError, ValueError) as exc:
        print(f"Daily close validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.domain.calculator import calculate_theoretical_target
from trafriend_api.domain.daily_close import DailyCloseAnchorStatus
from trafriend_api.domain.errors import (
    AnchorConflictError,
    MarketDataProviderError,
    ProviderAuthenticationError,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.persistence import PostgreSQLDailyCloseAnchorRepository
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.scripts.validate_daily_close_anchor import (
    _build_provider,
    _relationship,
    _signed_leverage,
)
from trafriend_api.settings import Settings

UTC = timezone.utc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one immutable Alpaca Daily Close Anchor in PostgreSQL."
    )
    parser.add_argument("--underlying", required=True)
    parser.add_argument("--leveraged-etf", required=True)
    parser.add_argument("--relationship-id")
    return parser


def _default_relationship_id(
    underlying: str, leveraged_product: str, signed_leverage: Decimal
) -> str:
    magnitude = format(abs(signed_leverage).normalize(), "f").replace(".", "p")
    direction = "n" if signed_leverage < 0 else ""
    return (
        f"rel_{underlying.lower()}_{leveraged_product.lower()}_"
        f"{direction}{magnitude}x"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    underlying = args.underlying.strip().upper()
    leveraged_product = args.leveraged_etf.strip().upper()
    try:
        settings = Settings.from_environment()
        if settings.database_url is None:
            raise ValueError("DATABASE_URL is required")
        if settings.alpaca_key_id is None or settings.alpaca_secret_key is None:
            raise ProviderAuthenticationError(
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY first"
            )

        signed_leverage = _signed_leverage(underlying, leveraged_product)
        relationship_id = args.relationship_id or _default_relationship_id(
            underlying, leveraged_product, signed_leverage
        )
        database_url = settings.database_url.get_secret_value()
        engine = create_database_engine(database_url)
        repository = PostgreSQLDailyCloseAnchorRepository(engine)
        service = DailyCloseAnchorService(
            provider=_build_provider(settings),
            calendar=NyseTradingCalendar(),
            repository=repository,
            now=lambda: datetime.now(UTC),
        )
        result = service.capture_with_result(
            relationship_id,
            underlying,
            leveraged_product,
            signed_leverage,
        )
        anchor = result.anchor
        print(f"Capture Result: {result.outcome.value}")
        print(f"Anchor ID: {anchor.id}")
        print(f"Anchor Version: {anchor.version}")
        print(f"Anchor Status: {anchor.status.value}")
        print(f"Trading Date: {anchor.trading_date.isoformat()}")
        print(f"{underlying} Close: {anchor.underlying.close or 'N/A'}")
        print(f"{leveraged_product} Close: {anchor.leveraged_product.close or 'N/A'}")
        if anchor.status != DailyCloseAnchorStatus.COMPLETE:
            print("Persisted: NO")
            engine.dispose()
            return 1
        print(
            "Logical Identity Row Count: "
            f"{repository.count_identity(underlying, leveraged_product, anchor.trading_date)}"
        )

        engine.dispose()
        recreated_engine = create_database_engine(database_url)
        recreated_repository = PostgreSQLDailyCloseAnchorRepository(recreated_engine)
        recreated = recreated_repository.latest(relationship_id)
        relationship = _relationship(relationship_id, underlying, leveraged_product)
        target_multiple = (
            Decimal("1.05") if (underlying, leveraged_product) == ("SNDK", "SNXX")
            else Decimal("1.02")
        )
        assert recreated.underlying.close is not None
        calculation = calculate_theoretical_target(
            relationship,
            recreated,
            "underlying",
            recreated.underlying.close * target_multiple,
        )
        print(
            "Anchor Survived Repository/Application Recreation: "
            f"{'YES' if recreated.id == anchor.id else 'NO'}"
        )
        print(f"Calculated Leveraged Target: {calculation.theoretical_target_price}")
        print(f"Calculated Leveraged Return: {calculation.leveraged_return}")
        recreated_engine.dispose()
        return 0
    except (AnchorConflictError, MarketDataProviderError, ValueError) as exc:
        print(f"Daily Close Anchor capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

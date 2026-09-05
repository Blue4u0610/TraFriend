from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Tuple


@dataclass(frozen=True)
class SupportedLeveragedProduct:
    symbol: str
    signed_leverage: Decimal


@dataclass(frozen=True)
class SupportedAssetGroup:
    underlying_symbol: str
    leveraged_products: Tuple[SupportedLeveragedProduct, ...]

    @property
    def symbols(self) -> Tuple[str, ...]:
        return (self.underlying_symbol,) + tuple(
            product.symbol for product in self.leveraged_products
        )


class SupportedUniverse:
    def __init__(self, groups: Iterable[SupportedAssetGroup]) -> None:
        self._groups = tuple(groups)

    @property
    def groups(self) -> Tuple[SupportedAssetGroup, ...]:
        return self._groups

    @property
    def symbols(self) -> Tuple[str, ...]:
        return tuple(
            dict.fromkeys(symbol for group in self._groups for symbol in group.symbols)
        )

    def group_for(self, symbol: str) -> SupportedAssetGroup:
        normalized = symbol.strip().upper()
        for group in self._groups:
            if normalized in group.symbols:
                return group
        raise KeyError(f"unsupported overnight symbol: {normalized}")


DEFAULT_SUPPORTED_UNIVERSE = SupportedUniverse(
    (
        SupportedAssetGroup(
            "SNDK", (SupportedLeveragedProduct("SNXX", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "NVDA", (SupportedLeveragedProduct("NVDL", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "TSLA", (SupportedLeveragedProduct("TSLL", Decimal("2")),)
        ),
        SupportedAssetGroup(
            "QQQ",
            (
                SupportedLeveragedProduct("QLD", Decimal("2")),
                SupportedLeveragedProduct("TQQQ", Decimal("3")),
                SupportedLeveragedProduct("SQQQ", Decimal("-3")),
            ),
        ),
        SupportedAssetGroup(
            "SOXX",
            (
                SupportedLeveragedProduct("SOXL", Decimal("3")),
                SupportedLeveragedProduct("SOXS", Decimal("-3")),
            ),
        ),
    )
)

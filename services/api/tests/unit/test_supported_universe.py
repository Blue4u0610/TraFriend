from decimal import Decimal

import pytest

from trafriend_api.domain.universe import DEFAULT_SUPPORTED_UNIVERSE


def test_underlying_can_have_multiple_leveraged_products() -> None:
    qqq = DEFAULT_SUPPORTED_UNIVERSE.group_for("TQQQ")

    assert qqq.underlying_symbol == "QQQ"
    assert {product.symbol for product in qqq.leveraged_products} == {
        "QLD",
        "TQQQ",
        "SQQQ",
    }
    assert {product.signed_leverage for product in qqq.leveraged_products} == {
        Decimal("2"),
        Decimal("3"),
        Decimal("-3"),
    }


def test_supported_universe_contains_requested_initial_pairs() -> None:
    assert {"SNDK", "SNXX", "NVDA", "NVDL", "TSLA", "TSLL"}.issubset(
        set(DEFAULT_SUPPORTED_UNIVERSE.symbols)
    )


def test_unsupported_overnight_symbol_is_explicit() -> None:
    with pytest.raises(KeyError, match="unsupported overnight symbol"):
        DEFAULT_SUPPORTED_UNIVERSE.group_for("AAPL")

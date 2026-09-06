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


def test_supported_universe_contains_exact_configured_relationships() -> None:
    relationships = {
        (group.underlying_symbol, product.symbol): product.signed_leverage
        for group in DEFAULT_SUPPORTED_UNIVERSE.groups
        for product in group.leveraged_products
    }

    assert relationships == {
        ("SNDK", "SNXX"): Decimal("2"),
        ("NVDA", "NVDL"): Decimal("2"),
        ("TSLA", "TSLL"): Decimal("2"),
        ("QQQ", "QLD"): Decimal("2"),
        ("QQQ", "TQQQ"): Decimal("3"),
        ("QQQ", "SQQQ"): Decimal("-3"),
        ("SOXX", "SOXL"): Decimal("3"),
        ("SOXX", "SOXS"): Decimal("-3"),
    }


def test_unsupported_symbol_is_explicit() -> None:
    with pytest.raises(KeyError, match="unsupported overnight symbol"):
        DEFAULT_SUPPORTED_UNIVERSE.group_for("AAPL")

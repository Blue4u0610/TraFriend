from decimal import Decimal

import pytest

from trafriend_api.scripts.validate_daily_close_anchor import (
    _relationship,
    _signed_leverage,
    main,
)


def test_diagnostic_uses_curated_signed_leverage_metadata() -> None:
    assert _signed_leverage("SNDK", "SNXX") == Decimal("2")
    assert _signed_leverage("QQQ", "TQQQ") == Decimal("3")
    assert _relationship("rel", "QQQ", "TQQQ").leverage_factor == Decimal("3")

    with pytest.raises(ValueError, match="not a configured relationship"):
        _signed_leverage("QQQ", "SNXX")


def test_diagnostic_rejects_arguments_without_contacting_provider(capsys) -> None:
    assert main(("unexpected",)) == 2
    assert "accepts no arguments" in capsys.readouterr().err

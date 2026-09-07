import pytest

from trafriend_api.scripts.calculate_mtd_rankings import parse_period


def test_parse_mtd_ranking_period() -> None:
    assert parse_period("2026-09") == (2026, 9)
    assert parse_period("2027-01") == (2027, 1)


@pytest.mark.parametrize("value", ("2026-00", "2026-13", "09-2026", "2026-9"))
def test_parse_mtd_ranking_period_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_period(value)

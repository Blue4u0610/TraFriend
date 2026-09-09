import json
from datetime import date
from types import SimpleNamespace

import pytest

from trafriend_api.application.services.daily_price import DailyPriceCaptureReport
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent
from trafriend_api.scripts import capture_qqq_price_history as command
from trafriend_api.settings import Settings


@pytest.mark.parametrize(
    "status,expected",
    [
        ("COMPLETE", 0),
        ("NOT_DUE", 0),
        ("PARTIAL_RETRYABLE", 2),
        ("CONFLICT", 1),
    ],
)
def test_daily_price_cli_is_independent_and_uses_safe_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    expected: int,
) -> None:
    report = DailyPriceCaptureReport(
        date(2026, 9, 4),
        date(2026, 9, 4),
        status,
        1,
        1,
        1 if status == "COMPLETE" else 0,
        0,
        1 if status == "PARTIAL_RETRYABLE" else 0,
        1 if status == "CONFLICT" else 0,
        (),
    )
    member = NasdaqConstituent("ins_nvda_xnas", "NVDA", "Nvidia", date(2026, 9, 4), "fixture")
    settings = Settings(
        database_url="postgresql://fixture:fixture@localhost/trafriend_dev",
        alpaca_key_id="fixture-key",
        alpaca_secret_key="fixture-secret",
    )
    closed: list[str] = []
    monkeypatch.setattr(command.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(
        command,
        "create_database_engine",
        lambda _url: SimpleNamespace(dispose=lambda: closed.append("database")),
    )
    monkeypatch.setattr(command, "PostgreSQLProfitRatioRepository", lambda _engine: object())
    monkeypatch.setattr(command, "PostgreSQLDailyPriceRepository", lambda _engine: object())
    monkeypatch.setattr(command, "ensure_qqq_constituents", lambda _engine: (member,))
    monkeypatch.setattr(
        command,
        "AlpacaProfitRatioCaptureProvider",
        lambda **_kwargs: SimpleNamespace(close=lambda: closed.append("provider")),
    )
    monkeypatch.setattr(
        command,
        "DailyPriceCaptureService",
        lambda **_kwargs: SimpleNamespace(capture=lambda _start, _end: report),
    )
    assert command.main(["--start", "2026-09-04", "--end", "2026-09-04"]) == expected
    output = capsys.readouterr().out
    data = json.loads(output)
    assert data["dataset"] == "INDEPENDENT_DAILY_PRICE_OHLC"
    assert data["profit_ratio_required"] is False and data["status"] == status
    assert "fixture-key" not in output and "fixture-secret" not in output
    assert "postgresql://" not in output
    assert closed == ["provider", "database"]


def test_daily_price_cli_missing_environment_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(command.Settings, "from_environment", lambda: Settings())
    assert command.main(["--start", "2026-09-04", "--end", "2026-09-04"]) == 1
    assert json.loads(capsys.readouterr().out) == {"status": "FAILED", "error_class": "ValueError"}


def test_daily_price_cli_rejects_unbounded_range_without_environment_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject() -> Settings:
        pytest.fail("invalid range must not access environment or providers")

    monkeypatch.setattr(command.Settings, "from_environment", reject)
    with pytest.raises(SystemExit) as error:
        command.main(["--start", "2026-01-01", "--end", "2026-09-04"])
    assert error.value.code == 2

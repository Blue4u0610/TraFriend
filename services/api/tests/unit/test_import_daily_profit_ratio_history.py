import json
from datetime import date
from types import SimpleNamespace

import pytest

from trafriend_api.application.ports.profit_ratio import ProfitRatioPersistenceOutcome
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent
from trafriend_api.scripts import import_daily_profit_ratio_history as command
from trafriend_api.settings import Settings


def test_import_daily_history_is_bounded_idempotent_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        database_url="postgresql://fixture:secret@localhost/trafriend_dev",
    )
    repository = SimpleNamespace(
        list_constituents=lambda: (
            NasdaqConstituent(
                "ins_sndk_xnas", "SNDK", "Sandisk", date(2026, 9, 4), "fixture"
            ),
        ),
        save_daily=lambda _item: ProfitRatioPersistenceOutcome.INSERTED,
    )
    disposed: list[bool] = []
    monkeypatch.setattr(command.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(
        command,
        "create_database_engine",
        lambda _url: SimpleNamespace(dispose=lambda: disposed.append(True)),
    )
    monkeypatch.setattr(command, "PostgreSQLProfitRatioRepository", lambda _engine: repository)

    assert command.main([]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "COMPLETE"
    assert payload["rows"] == 30 and payload["inserted"] == 30
    assert "secret" not in output and "postgresql://" not in output
    assert disposed == [True]


def test_import_daily_history_rejects_unreviewed_columns_before_writing(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("symbol,ratio\nSNDK,0.5\n")
    monkeypatch.setattr(
        command.Settings,
        "from_environment",
        lambda: Settings(database_url="postgresql://fixture:secret@localhost/trafriend_dev"),
    )
    monkeypatch.setattr(
        command,
        "create_database_engine",
        lambda _url: SimpleNamespace(dispose=lambda: None),
    )
    monkeypatch.setattr(
        command,
        "PostgreSQLProfitRatioRepository",
        lambda _engine: SimpleNamespace(list_constituents=lambda: ()),
    )
    assert command.main(["--file", str(source)]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "FAILED",
        "error_class": "ValueError",
    }

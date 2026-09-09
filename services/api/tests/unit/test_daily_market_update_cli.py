from datetime import date
from types import SimpleNamespace

from trafriend_api.application.services.daily_price import DailyPriceCaptureReport
from trafriend_api.application.services.market_update import DailyMarketUpdateReport
from trafriend_api.application.services.universe import DailyCaptureReport
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent
from trafriend_api.scripts import run_daily_market_update as command
from trafriend_api.settings import Settings


def test_production_command_uses_inherited_remote_database_without_local_dependency(
    monkeypatch, capsys
) -> None:
    database_url = "postgresql://render-user:render-secret@dpg-example.internal/prod_db"
    settings = Settings(
        environment="production",
        cors_origins=["https://trafriend.example"],
        database_url=database_url,
        alpaca_key_id="alpaca-key",
        alpaca_secret_key="alpaca-secret",
    )
    engine = SimpleNamespace(dispose=lambda: None)
    member = NasdaqConstituent(
        "ins_aapl_xnas",
        "AAPL",
        "Apple",
        date(2026, 9, 8),
        "test",
    )
    close_report = DailyCaptureReport("2026-09-08", "COMPLETE", (), (), ())
    ohlc_report = DailyPriceCaptureReport(
        date(2026, 9, 8),
        date(2026, 9, 8),
        "COMPLETE",
        1,
        1,
        1,
        0,
        0,
        0,
        (),
    )
    report = DailyMarketUpdateReport(
        status="COMPLETE",
        trading_date="2026-09-08",
        ranking_period="2026-09",
        ranking_status="UPDATED",
        ranking_rows=100,
        daily_close_status="COMPLETE",
        daily_close_report=close_report,
        ohlc_status="INSERTED",
        ohlc_report=ohlc_report,
    )
    seen_urls: list[str] = []
    provider = SimpleNamespace(close=lambda: None)

    monkeypatch.setattr(command.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(
        command,
        "create_database_engine",
        lambda url: (seen_urls.append(url), engine)[1],
    )
    monkeypatch.setattr(command, "ensure_qqq_constituents", lambda _engine: (member,))
    monkeypatch.setattr(
        command, "AlpacaProfitRatioCaptureProvider", lambda **_kwargs: provider
    )
    monkeypatch.setattr(command, "PostgreSQLProfitRatioRepository", lambda _engine: object())
    monkeypatch.setattr(command, "PostgreSQLDailyPriceRepository", lambda _engine: object())
    monkeypatch.setattr(command, "PostgreSQLMarketRankingRepository", lambda _engine: object())
    monkeypatch.setattr(command, "build_ranking_service", lambda *_args: object())
    monkeypatch.setattr(
        command,
        "build_application_services",
        lambda *_args, **_kwargs: SimpleNamespace(universe=object()),
    )
    monkeypatch.setattr(command, "DailyPriceCaptureService", lambda **_kwargs: object())
    monkeypatch.setattr(
        command,
        "DailyMarketUpdateService",
        lambda **_kwargs: SimpleNamespace(run=lambda: report),
    )

    assert command.main() == 0
    output = capsys.readouterr().out
    assert seen_urls == [database_url]
    assert "Data Target: PRODUCTION" in output
    assert "Database Host: dpg-example.internal" in output
    assert "Database Name: prod_db" in output
    assert "OHLC: INSERTED" in output
    assert "render-secret" not in output
    assert "alpaca-secret" not in output
    assert "localhost" not in output

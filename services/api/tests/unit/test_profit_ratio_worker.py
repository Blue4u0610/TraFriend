import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from trafriend_api.application.services.daily_price import DailyPriceCaptureReport
from trafriend_api.application.services.profit_ratio import ProfitRatioCaptureReport
from trafriend_api.domain.errors import ProviderUnavailableError
from trafriend_api.domain.profit_ratio_daily import NasdaqConstituent, ProfitRatioPhase
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.scripts import capture_profit_ratio
from trafriend_api.settings import Settings


@pytest.mark.parametrize(("price_status", "expected_exit", "prefetch_failure"), [
    ("COMPLETE", 0, False), ("PARTIAL_RETRYABLE", 2, False), ("COMPLETE", 2, True),
])
def test_existing_scheduled_runner_captures_prices_despite_missing_ratio_inputs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    price_status: str, expected_exit: int, prefetch_failure: bool,
) -> None:
    day = date(2026, 9, 4)
    session = ProfitRatioExchangeCalendar().session(day)
    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(capture_profit_ratio, "datetime", SimpleNamespace(now=lambda _tz: now))
    settings = Settings(database_url="postgresql+psycopg://test.invalid/db",
                        alpaca_key_id="test-key", alpaca_secret_key="test-secret")
    monkeypatch.setattr(capture_profit_ratio.Settings, "from_environment", lambda: settings)
    engine = MagicMock()
    monkeypatch.setattr(capture_profit_ratio, "create_database_engine", lambda _: engine)
    repository = MagicMock()
    repository.list_constituents.return_value = (
        NasdaqConstituent("ins_nvda_xnas", "NVDA", "Synthetic NVIDIA", day, "mock-qqq"),
    )
    monkeypatch.setattr(capture_profit_ratio, "PostgreSQLProfitRatioRepository",
                        lambda _: repository)
    provider = MagicMock()
    if prefetch_failure:
        repository.latest.return_value = None
        provider.prime_history.side_effect = ProviderUnavailableError("ratio prefetch failed")
    monkeypatch.setattr(capture_profit_ratio, "AlpacaProfitRatioCaptureProvider",
                        lambda **_kwargs: provider)
    calendar = MagicMock()
    calendar.sessions.return_value = (session,)
    monkeypatch.setattr(capture_profit_ratio, "ProfitRatioExchangeCalendar", lambda: calendar)
    ratio_service = MagicMock()
    ratio_service.capture.side_effect = [
        ProfitRatioCaptureReport(
            day, phase, "PARTIAL_RETRYABLE" if prefetch_failure else "DATA_INSUFFICIENT",
            existing=int(not prefetch_failure), data_insufficient=int(not prefetch_failure),
            unavailable=int(prefetch_failure),
        ) for phase in ProfitRatioPhase
    ]
    ratio_factory = MagicMock(return_value=ratio_service)
    monkeypatch.setattr(capture_profit_ratio, "ProfitRatioService", ratio_factory)
    prices = MagicMock()
    prices.capture.return_value = DailyPriceCaptureReport(
        day, day, price_status, 1, 1, 1 if price_status == "COMPLETE" else 0,
        0, int(price_status != "COMPLETE"), 0, (),
    )
    price_factory = MagicMock(return_value=prices)
    monkeypatch.setattr(capture_profit_ratio, "DailyPriceCaptureService", price_factory)

    assert capture_profit_ratio.main(["--start", str(day), "--end", str(day)]) == expected_exit
    payload = json.loads(capsys.readouterr().out)
    prices.capture.assert_called_once_with(day, day)
    ratio_factory.assert_called_once_with(
        repository, calendar, None if prefetch_failure else provider
    )
    assert payload["daily_prices"]["status"] == price_status
    assert payload["data_insufficient"] == (0 if prefetch_failure else 2)
    assert payload["status"] == (
        "DATA_INSUFFICIENT"
        if price_status == "COMPLETE" and not prefetch_failure else "PARTIAL_RETRYABLE"
    )
    provider.close.assert_called_once()
    engine.dispose.assert_called_once()

from trafriend_api.domain.daily_close import DailyCloseQuality
from trafriend_api.settings import Settings


def test_documented_alpaca_environment_names_take_precedence(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "documented-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "documented-secret")
    monkeypatch.setenv("TRAFRIEND_ALPACA_KEY_ID", "legacy-key")
    monkeypatch.setenv("TRAFRIEND_ALPACA_SECRET_KEY", "legacy-secret")

    settings = Settings.from_environment()

    assert settings.alpaca_key_id is not None
    assert settings.alpaca_secret_key is not None
    assert settings.alpaca_key_id.get_secret_value() == "documented-key"
    assert settings.alpaca_secret_key.get_secret_value() == "documented-secret"
    assert "documented-secret" not in repr(settings)


def test_mock_remains_default_without_alpaca_credentials(monkeypatch) -> None:
    for name in (
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "TRAFRIEND_ALPACA_KEY_ID",
        "TRAFRIEND_ALPACA_SECRET_KEY",
        "TRAFRIEND_OVERNIGHT_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_environment()

    assert settings.overnight_provider == "mock"
    assert settings.alpaca_key_id is None
    assert settings.alpaca_secret_key is None


def test_daily_close_feed_and_quality_are_backend_configurable(monkeypatch) -> None:
    monkeypatch.setenv("TRAFRIEND_ALPACA_DAILY_BARS_FEED", "iex")
    monkeypatch.setenv("TRAFRIEND_ALPACA_DAILY_BARS_QUALITY", "REALTIME")

    settings = Settings.from_environment()

    assert settings.alpaca_daily_bars_feed == "iex"
    assert settings.alpaca_daily_bars_quality == DailyCloseQuality.REALTIME

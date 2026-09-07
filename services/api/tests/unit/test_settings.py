import pytest

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


def test_daily_close_provider_defaults_to_mock_and_can_select_alpaca(monkeypatch) -> None:
    monkeypatch.delenv("TRAFRIEND_DAILY_CLOSE_PROVIDER", raising=False)
    assert Settings.from_environment().daily_close_provider == "mock"

    monkeypatch.setenv("TRAFRIEND_DAILY_CLOSE_PROVIDER", "ALPACA")
    assert Settings.from_environment().daily_close_provider == "alpaca"


def test_database_url_is_secret_and_optional(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://app:private-password@localhost/trafriend_dev",
    )

    settings = Settings.from_environment()

    assert settings.database_url is not None
    assert settings.database_url.get_secret_value().endswith("/trafriend_dev")
    assert "private-password" not in repr(settings)

    monkeypatch.delenv("DATABASE_URL")
    assert Settings.from_environment().database_url is None


def test_production_requires_database_and_explicit_safe_cors(monkeypatch) -> None:
    monkeypatch.setenv("TRAFRIEND_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TRAFRIEND_CORS_ORIGINS", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings.from_environment()

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://app:private-password@db.example/trafriend_prod"
    )
    monkeypatch.setenv("TRAFRIEND_CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="wildcard CORS"):
        Settings.from_environment()

    monkeypatch.setenv("TRAFRIEND_CORS_ORIGINS", "http://localhost:3000")
    with pytest.raises(ValueError, match="localhost CORS"):
        Settings.from_environment()


def test_production_accepts_configured_https_origins(monkeypatch) -> None:
    monkeypatch.setenv("TRAFRIEND_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:secret@db/trafriend_prod")
    monkeypatch.setenv(
        "TRAFRIEND_CORS_ORIGINS",
        "https://trafriend.com/,https://www.trafriend.com",
    )

    settings = Settings.from_environment()

    assert settings.cors_origins == [
        "https://trafriend.com",
        "https://www.trafriend.com",
    ]

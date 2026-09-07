import os
from typing import List, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from trafriend_api.domain.daily_close import DailyCloseQuality
from trafriend_api.domain.overnight import DataQuality


class Settings(BaseModel):
    environment: str = "development"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    overnight_provider: str = "mock"
    alpaca_key_id: Optional[SecretStr] = None
    alpaca_secret_key: Optional[SecretStr] = None
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    alpaca_trading_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_snapshot_feed: str = "overnight"
    alpaca_bars_feed: str = "boats"
    alpaca_snapshot_quality: DataQuality = DataQuality.REALTIME
    alpaca_bars_quality: DataQuality = DataQuality.DELAYED
    alpaca_daily_bars_feed: str = "sip"
    alpaca_daily_bars_quality: DailyCloseQuality = DailyCloseQuality.DELAYED
    daily_close_provider: str = "mock"
    database_url: Optional[SecretStr] = None

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: List[str]) -> List[str]:
        normalized: List[str] = []
        for origin in origins:
            value = origin.strip().rstrip("/")
            if not value:
                continue
            if value == "*":
                normalized.append(value)
                continue
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS origins must be absolute HTTP(S) origins")
            normalized.append(value)
        if len(set(normalized)) != len(normalized):
            raise ValueError("CORS origins must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        environment = self.environment.strip().lower()
        if environment == "production":
            if self.database_url is None:
                raise ValueError("DATABASE_URL is required in production")
            if not self.cors_origins:
                raise ValueError("TRAFRIEND_CORS_ORIGINS is required in production")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS is not allowed in production")
            if any(
                urlsplit(origin).hostname in {"localhost", "127.0.0.1"}
                for origin in self.cors_origins
            ):
                raise ValueError("localhost CORS origins are not allowed in production")
        return self

    @classmethod
    def from_environment(cls) -> "Settings":
        environment = os.getenv("TRAFRIEND_ENV", "development")
        raw_origins = os.getenv("TRAFRIEND_CORS_ORIGINS")
        if raw_origins is None:
            raw_origins = (
                ""
                if environment.strip().lower() == "production"
                else "http://localhost:3000,http://127.0.0.1:3000"
            )
        return cls(
            environment=environment,
            cors_origins=[origin.strip() for origin in raw_origins.split(",") if origin.strip()],
            overnight_provider=os.getenv("TRAFRIEND_OVERNIGHT_PROVIDER", "mock"),
            alpaca_key_id=(
                SecretStr(
                    os.getenv("ALPACA_API_KEY")
                    or os.environ["TRAFRIEND_ALPACA_KEY_ID"]
                )
                if os.getenv("ALPACA_API_KEY")
                or os.getenv("TRAFRIEND_ALPACA_KEY_ID")
                else None
            ),
            alpaca_secret_key=(
                SecretStr(
                    os.getenv("ALPACA_SECRET_KEY")
                    or os.environ["TRAFRIEND_ALPACA_SECRET_KEY"]
                )
                if os.getenv("ALPACA_SECRET_KEY")
                or os.getenv("TRAFRIEND_ALPACA_SECRET_KEY")
                else None
            ),
            alpaca_data_base_url=os.getenv(
                "TRAFRIEND_ALPACA_DATA_BASE_URL", "https://data.alpaca.markets"
            ),
            alpaca_trading_base_url=os.getenv(
                "TRAFRIEND_ALPACA_TRADING_BASE_URL",
                "https://paper-api.alpaca.markets",
            ),
            alpaca_snapshot_feed=os.getenv(
                "TRAFRIEND_ALPACA_SNAPSHOT_FEED", "overnight"
            ),
            alpaca_bars_feed=os.getenv("TRAFRIEND_ALPACA_BARS_FEED", "boats"),
            alpaca_snapshot_quality=DataQuality(
                os.getenv("TRAFRIEND_ALPACA_SNAPSHOT_QUALITY", "REALTIME").upper()
            ),
            alpaca_bars_quality=DataQuality(
                os.getenv("TRAFRIEND_ALPACA_BARS_QUALITY", "DELAYED").upper()
            ),
            alpaca_daily_bars_feed=os.getenv(
                "TRAFRIEND_ALPACA_DAILY_BARS_FEED", "sip"
            ),
            alpaca_daily_bars_quality=DailyCloseQuality(
                os.getenv(
                    "TRAFRIEND_ALPACA_DAILY_BARS_QUALITY", "DELAYED"
                ).upper()
            ),
            daily_close_provider=os.getenv(
                "TRAFRIEND_DAILY_CLOSE_PROVIDER", "mock"
            ).lower(),
            database_url=(
                SecretStr(os.environ["DATABASE_URL"])
                if os.getenv("DATABASE_URL")
                else None
            ),
        )

from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from trafriend_api.application.ports.overnight_market_data import (
    OvernightMarketDataProvider,
)
from trafriend_api.domain.errors import ProviderUnavailableError
from trafriend_api.domain.overnight import DataQuality
from trafriend_api.infrastructure.market_data.alpaca import AlpacaMarketDataProvider

UTC = timezone.utc


def test_alpaca_batches_latest_quotes_and_normalizes_midpoints() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "quotes": {
                    "SNDK": {
                        "bp": 1704.10,
                        "ap": 1704.30,
                        "t": "2026-09-08T00:05:01.123456789Z",
                    },
                    "SNXX": {
                        "bp": 20.07,
                        "ap": 20.09,
                        "t": "2026-09-08T00:05:01.223456789Z",
                    },
                }
            },
        )

    client = httpx.Client(
        base_url="https://data.alpaca.markets", transport=httpx.MockTransport(handler)
    )
    provider = AlpacaMarketDataProvider(
        "test-key",
        "test-secret",
        client=client,
        now=lambda: datetime(2026, 9, 8, 0, 5, 2, tzinfo=UTC),
    )

    quotes = provider.get_overnight_snapshot(
        ("SNDK", "SNXX"), datetime(2026, 9, 8, 0, 5, tzinfo=UTC)
    )

    assert len(requests) == 1
    assert isinstance(provider, OvernightMarketDataProvider)
    assert parse_qs(requests[0].url.query.decode())["symbols"] == ["SNDK,SNXX"]
    assert requests[0].headers["APCA-API-KEY-ID"] == "test-key"
    assert [quote.price for quote in quotes] == [Decimal("1704.20"), Decimal("20.08")]
    assert all(quote.quality == DataQuality.REALTIME for quote in quotes)
    assert quotes[0].market_timestamp.microsecond == 123456


def test_alpaca_batches_one_minute_boats_bars() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "bars": {
                    "SNDK": [{"o": 1702.35, "t": "2026-09-08T00:00:00Z"}],
                    "SNXX": [{"o": 20.02, "t": "2026-09-08T00:01:00Z"}],
                },
                "next_page_token": None,
            },
        )

    client = httpx.Client(
        base_url="https://data.alpaca.markets", transport=httpx.MockTransport(handler)
    )
    provider = AlpacaMarketDataProvider(
        "test-key",
        "test-secret",
        client=client,
        now=lambda: datetime(2026, 9, 8, 0, 16, tzinfo=UTC),
    )

    bars = provider.get_overnight_bars(
        ("SNDK", "SNXX"),
        datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 8, 0, 15, tzinfo=UTC),
        "1Min",
    )

    assert len(requests) == 1
    query = parse_qs(requests[0].url.query.decode())
    assert query["symbols"] == ["SNDK,SNXX"]
    assert query["feed"] == ["boats"]
    assert [bar.open_price for bar in bars] == [Decimal("1702.35"), Decimal("20.02")]
    assert all(bar.quality == DataQuality.DELAYED for bar in bars)


def test_alpaca_rejects_malformed_requested_quote() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "quotes": {
                    "SNDK": {
                        "bp": "not-a-price",
                        "ap": 1704.30,
                        "t": "2026-09-08T00:05:01Z",
                    }
                }
            },
        )

    client = httpx.Client(
        base_url="https://data.alpaca.markets", transport=httpx.MockTransport(handler)
    )
    provider = AlpacaMarketDataProvider("test-key", "test-secret", client=client)

    with pytest.raises(ProviderUnavailableError, match="malformed data"):
        provider.get_latest_quotes(("SNDK",))

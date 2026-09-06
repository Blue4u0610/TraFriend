from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from trafriend_api.application.ports.daily_close import DailyCloseMarketDataProvider
from trafriend_api.application.ports.overnight_market_data import (
    HistoricalOvernightMarketDataProvider,
    OvernightMarketDataProvider,
)
from trafriend_api.domain.daily_close import DailyCloseQuality
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
                    "SNDK": [
                        {
                            "o": 1702.35,
                            "h": 1703.00,
                            "l": 1701.80,
                            "c": 1702.80,
                            "v": 14,
                            "t": "2026-09-08T00:00:00Z",
                        }
                    ],
                    "SNXX": [
                        {
                            "o": 20.02,
                            "h": 20.05,
                            "l": 20.01,
                            "c": 20.04,
                            "v": 21,
                            "t": "2026-09-08T00:01:00Z",
                        }
                    ],
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

    detailed_bars = provider.get_historical_overnight_bars(
        ("SNDK", "SNXX"),
        datetime(2026, 9, 8, 0, 0, tzinfo=UTC),
        datetime(2026, 9, 8, 0, 15, tzinfo=UTC),
        "1Min",
    )

    assert isinstance(provider, HistoricalOvernightMarketDataProvider)
    assert detailed_bars[0].high_price == Decimal("1703.0")
    assert detailed_bars[0].low_price == Decimal("1701.8")
    assert detailed_bars[0].close_price == Decimal("1702.8")
    assert detailed_bars[0].volume == Decimal("14")


def test_alpaca_batches_historical_boats_quotes_and_paginates() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        query = parse_qs(request.url.query.decode())
        if "page_token" not in query:
            return httpx.Response(
                200,
                json={
                    "quotes": {
                        "SNDK": [
                            {
                                "bp": 1550.00,
                                "ap": 1552.00,
                                "t": "2026-09-04T00:04:59.900000000Z",
                            }
                        ],
                        "SNXX": [],
                    },
                    "next_page_token": "next-page",
                },
            )
        return httpx.Response(
            200,
            json={
                "quotes": {
                    "SNDK": [],
                    "SNXX": [
                        {
                            "bp": 20.00,
                            "ap": 20.10,
                            "t": "2026-09-04T00:05:00.100000000Z",
                        }
                    ],
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
        now=lambda: datetime(2026, 9, 4, 0, 20, tzinfo=UTC),
    )

    quotes = provider.get_historical_overnight_quotes(
        ("SNDK", "SNXX"),
        datetime(2026, 9, 4, 0, 4, tzinfo=UTC),
        datetime(2026, 9, 4, 0, 6, tzinfo=UTC),
    )

    assert len(requests) == 2
    first_query = parse_qs(requests[0].url.query.decode())
    second_query = parse_qs(requests[1].url.query.decode())
    assert first_query["symbols"] == ["SNDK,SNXX"]
    assert first_query["feed"] == ["boats"]
    assert first_query["start"] == ["2026-09-04T00:04:00Z"]
    assert first_query["end"] == ["2026-09-04T00:06:00Z"]
    assert second_query["page_token"] == ["next-page"]
    assert [quote.symbol for quote in quotes] == ["SNDK", "SNXX"]
    assert [quote.midpoint for quote in quotes] == [
        Decimal("1551.0"),
        Decimal("20.05"),
    ]
    assert all(quote.quality == DataQuality.DELAYED for quote in quotes)


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


def test_alpaca_batches_unadjusted_sip_daily_close_bars() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "bars": {
                    "SNDK": [{"c": 1740, "t": "2026-09-04T04:00:00Z"}],
                    "SNXX": [{"c": 17.36, "t": "2026-09-04T04:00:00Z"}],
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
        now=lambda: datetime(2026, 9, 4, 21, tzinfo=UTC),
    )

    bars = provider.get_daily_close_bars(
        ("SNDK", "SNXX"), date(2026, 9, 4), date(2026, 9, 4)
    )

    assert isinstance(provider, DailyCloseMarketDataProvider)
    assert len(requests) == 1
    query = parse_qs(requests[0].url.query.decode())
    assert query["symbols"] == ["SNDK,SNXX"]
    assert query["timeframe"] == ["1Day"]
    assert query["feed"] == ["sip"]
    assert query["adjustment"] == ["raw"]
    assert query["start"] == ["2026-09-04T04:00:00Z"]
    assert query["end"] == ["2026-09-05T04:00:00Z"]
    assert [bar.close for bar in bars] == [Decimal("1740"), Decimal("17.36")]
    assert all(bar.trading_date == date(2026, 9, 4) for bar in bars)
    assert all(bar.quality == DailyCloseQuality.DELAYED for bar in bars)

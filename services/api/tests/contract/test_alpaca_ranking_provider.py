from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs

import httpx

from trafriend_api.infrastructure.market_data.alpaca import AlpacaRankingDataProvider


def test_alpaca_ranking_provider_loads_assets_and_batches_vwap_bars() -> None:
    data_requests = []

    def trading_handler(request: httpx.Request) -> httpx.Response:
        query = parse_qs(request.url.query.decode())
        assert query == {"status": ["active"], "asset_class": ["us_equity"]}
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAA",
                    "name": "Alpha Corporation",
                    "exchange": "NASDAQ",
                    "status": "active",
                    "tradable": True,
                },
                {
                    "symbol": "BBB",
                    "name": "Beta Corporation",
                    "exchange": "NYSE",
                    "status": "active",
                    "tradable": True,
                },
                {
                    "symbol": "CCC",
                    "name": "Gamma Corporation",
                    "exchange": "NYSE",
                    "status": "active",
                    "tradable": True,
                },
            ],
        )

    def data_handler(request: httpx.Request) -> httpx.Response:
        data_requests.append(request)
        symbols = parse_qs(request.url.query.decode())["symbols"][0].split(",")
        return httpx.Response(
            200,
            json={
                "bars": {
                    symbol: [
                        {
                            "t": "2026-09-01T04:00:00Z",
                            "v": 1000,
                            "vw": "12.3456",
                        }
                    ]
                    for symbol in symbols
                },
                "next_page_token": None,
            },
        )

    trading_client = httpx.Client(
        base_url="https://paper-api.alpaca.markets",
        transport=httpx.MockTransport(trading_handler),
    )
    data_client = httpx.Client(
        base_url="https://data.alpaca.markets",
        transport=httpx.MockTransport(data_handler),
    )
    provider = AlpacaRankingDataProvider(
        "test-key",
        "test-secret",
        batch_size=2,
        trading_client=trading_client,
        data_client=data_client,
        now=lambda: datetime(2026, 9, 1, 21, tzinfo=timezone.utc),
    )

    assets = provider.list_active_us_equities()
    bars = provider.get_daily_ranking_bars(
        tuple(asset.symbol for asset in assets),
        date(2026, 9, 1),
        date(2026, 9, 1),
    )

    assert [asset.symbol for asset in assets] == ["AAA", "BBB", "CCC"]
    assert len(data_requests) == 2
    first_query = parse_qs(data_requests[0].url.query.decode())
    assert first_query["symbols"] == ["AAA,BBB"]
    assert first_query["feed"] == ["sip"]
    assert first_query["timeframe"] == ["1Day"]
    assert first_query["adjustment"] == ["raw"]
    assert first_query["end"] == ["2026-09-01T20:40:00Z"]
    assert bars[0].vwap == Decimal("12.3456")
    assert bars[0].volume == Decimal("1000")


def test_alpaca_ranking_provider_omits_bar_without_vwap() -> None:
    def data_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "bars": {
                    "AAA": [{"t": "2026-09-01T04:00:00Z", "v": 1000}]
                },
                "next_page_token": None,
            },
        )

    provider = AlpacaRankingDataProvider(
        "test-key",
        "test-secret",
        data_client=httpx.Client(
            base_url="https://data.alpaca.markets",
            transport=httpx.MockTransport(data_handler),
        ),
    )

    assert provider.get_daily_ranking_bars(
        ("AAA",), date(2026, 9, 1), date(2026, 9, 1)
    ) == ()

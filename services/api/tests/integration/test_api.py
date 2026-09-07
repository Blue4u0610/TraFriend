from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from trafriend_api.application.services.daily_close_anchor import DailyCloseAnchorService
from trafriend_api.application.services.universe import UniverseService
from trafriend_api.domain.universe import (
    MarketRanking,
    RankingPeriodStatus,
    RankingType,
)
from trafriend_api.infrastructure.calendar import NyseTradingCalendar
from trafriend_api.infrastructure.catalog import InMemoryLeveragedRelationshipCatalog
from trafriend_api.infrastructure.market_data.mock import MockMarketDataProvider
from trafriend_api.infrastructure.persistence import (
    InMemoryDailyCloseAnchorRepository,
    InMemoryMarketRankingRepository,
)
from trafriend_api.main import create_app
from trafriend_api.settings import Settings


def test_health_uses_mock_provider(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "trafriend-api",
        "market_data_provider": "mock",
    }
    assert response.headers["X-Request-ID"].startswith("req_")


def test_cors_allows_only_the_configured_origin() -> None:
    app = create_app(Settings(cors_origins=["https://trafriend.example"]))
    with TestClient(app) as cors_client:
        allowed = cors_client.options(
            "/health",
            headers={
                "Origin": "https://trafriend.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        rejected = cors_client.options(
            "/health",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == (
        "https://trafriend.example"
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_instrument_search_and_relationship_resolution(client: TestClient) -> None:
    search = client.get("/api/v1/instruments/search", params={"query": "TQQQ"})
    assert search.status_code == 200
    assert search.json()["data"][0]["id"] == "ins_tqqq_xnas"

    relationships = client.get(
        "/api/v1/instruments/ins_tqqq_xnas/leveraged-products"
    )
    assert relationships.status_code == 200
    data = relationships.json()["data"]
    assert data["underlying"]["symbol"] == "QQQ"
    assert {item["leverage_factor"] for item in data["relationships"]} == {
        "2",
        "3",
        "-3",
    }


def test_universe_search_workspace_and_multi_product_calculation(
    client: TestClient,
) -> None:
    search = client.get("/api/v1/universe/search", params={"q": "QQQ"})
    assert search.status_code == 200
    assert search.json()["data"][0]["symbol"] == "QQQ"

    workspace = client.get("/api/v1/underlyings/QQQ")
    assert workspace.status_code == 200
    rows = workspace.json()["data"]["rows"]
    assert [row["relationship"]["leveraged_product"]["symbol"] for row in rows] == [
        "QLD",
        "TQQQ",
        "SQQQ",
    ]
    assert {row["anchor_source"] for row in rows} == {"CACHE"}

    calculation = client.post(
        "/api/v1/underlyings/QQQ/calculations",
        json={"target_price": "504.00"},
    )
    assert calculation.status_code == 200
    results = {
        row["relationship"]["leveraged_product"]["symbol"]: row
        for row in calculation.json()["data"]["rows"]
    }
    assert results["QLD"]["theoretical_target_price"] == "132.0000"
    assert results["TQQQ"]["theoretical_target_price"] == "94.8750"
    assert results["SQQQ"]["theoretical_target_price"] == "26.5200"


def test_universe_search_endpoints_keep_underlyings_and_products_separate(
    client: TestClient,
) -> None:
    underlying = client.get(
        "/api/v1/universe/underlyings/search", params={"q": "QQ"}
    )
    products = client.get(
        "/api/v1/universe/leveraged-products/search", params={"q": "QQ"}
    )

    assert underlying.status_code == 200
    assert products.status_code == 200
    assert [item["symbol"] for item in underlying.json()["data"]] == ["QQQ"]
    assert {item["symbol"] for item in products.json()["data"]} == {
        "QLD",
        "TQQQ",
        "SQQQ",
    }
    assert all(
        item["instrument_type"] != "leveraged_etf"
        for item in underlying.json()["data"]
    )
    assert all(
        item["instrument_type"] == "leveraged_etf"
        for item in products.json()["data"]
    )


def test_popular_endpoint_is_explicitly_not_populated(client: TestClient) -> None:
    response = client.get("/api/v1/popular")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["period_status"] == "SEPTEMBER_TO_DATE"
    assert data["population_status"] == "NOT_POPULATED"
    assert data["rows"] == []


def test_popular_api_keeps_ranked_stock_with_zero_supported_products() -> None:
    now = datetime(2026, 9, 4, 21, tzinfo=timezone.utc)
    provider = MockMarketDataProvider(now=lambda: now)
    relationships = {
        relationship.id: relationship
        for instrument in provider.search_instruments("", 25)
        for relationship in provider.get_leveraged_relationships(instrument.id)
    }
    ranking = MarketRanking(
        ranking_period="2026-09",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 4),
        period_status=RankingPeriodStatus.SEPTEMBER_TO_DATE,
        ranking_type=RankingType.DOLLAR_TRADING_VOLUME,
        rank=1,
        symbol="WMT",
        display_name="Walmart Inc.",
        exchange="NYSE",
        trading_metric=Decimal("1000000"),
        calculated_at=now,
        source="verified-test-fixture",
    )
    app = create_app(Settings())
    app.state.universe_service = UniverseService(
        catalog=InMemoryLeveragedRelationshipCatalog(relationships.values()),
        ranking_repository=InMemoryMarketRankingRepository((ranking,)),
        anchor_service=DailyCloseAnchorService(
            provider=provider,
            calendar=NyseTradingCalendar(),
            repository=InMemoryDailyCloseAnchorRepository(),
            now=lambda: now,
        ),
    )

    with TestClient(app) as popular_client:
        response = popular_client.get("/api/v1/popular")

    assert response.status_code == 200
    assert response.json()["data"]["rows"] == [
        {
            "rank": 1,
            "symbol": "WMT",
            "name": "Walmart Inc.",
            "trading_metric": "1000000",
            "calculated_at": "2026-09-04T21:00:00Z",
            "source": "verified-test-fixture",
            "completeness_status": "COMPLETE",
            "sessions_observed": 0,
            "sessions_expected": 0,
            "supported_leveraged_products": 0,
        }
    ]
    assert provider.daily_close_request_log == []


def test_forward_calculation_uses_active_mock_close_anchor(client: TestClient) -> None:
    anchor_response = client.get(
        "/api/v1/leveraged-etf/relationships/rel_nvda_nvdl_2x/anchor"
    )
    assert anchor_response.status_code == 200
    anchor = anchor_response.json()["data"]
    assert anchor["anchor_type"] == "DAILY_CLOSE_ANCHOR"
    assert anchor["status"] == "COMPLETE"
    assert anchor["underlying"]["close"] == "170.00"
    assert anchor["leveraged_product"]["close"] == "80.00"

    response = client.post(
        "/api/v1/leveraged-etf/calculations",
        json={
            "relationship_id": "rel_nvda_nvdl_2x",
            "anchor_version_id": anchor["id"],
            "input_side": "underlying",
            "target_price": "180.00",
        },
    )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["output"]["symbol"] == "NVDL"
    assert result["output"]["theoretical_target_price"].startswith("89.4117647")
    assert result["anchor"]["provider"] == "mock"
    assert result["anchor"]["anchor_type"] == "DAILY_CLOSE_ANCHOR"
    assert result["formula_version"] == "leveraged-daily-close-linear/v2"
    assert result["warnings"][0]["code"] == "THEORETICAL_SINGLE_DAY_ONLY"


def test_sndk_snxx_relationship_is_available_to_calculator(client: TestClient) -> None:
    anchor_response = client.get(
        "/api/v1/leveraged-etf/relationships/rel_sndk_snxx_2x/anchor"
    )
    assert anchor_response.status_code == 200
    anchor = anchor_response.json()["data"]

    response = client.post(
        "/api/v1/leveraged-etf/calculations",
        json={
            "relationship_id": "rel_sndk_snxx_2x",
            "anchor_version_id": anchor["id"],
            "input_side": "underlying",
            "target_price": "1827.00",
        },
    )

    assert response.status_code == 200
    result = response.json()["data"]
    assert result["leveraged_return"] == "0.10"
    assert result["output"]["theoretical_target_price"] == "19.0960"


def test_calculator_api_read_makes_zero_market_data_provider_calls(
    monkeypatch,
) -> None:
    app = create_app(Settings())
    calls = {"relationship": 0, "daily_bars": 0}

    def fail_relationship(*args, **kwargs):
        calls["relationship"] += 1
        raise AssertionError("calculator API called the relationship provider")

    def fail_daily_bars(*args, **kwargs):
        calls["daily_bars"] += 1
        raise AssertionError("calculator API called the daily-bar provider")

    monkeypatch.setattr(MockMarketDataProvider, "get_relationship", fail_relationship)
    monkeypatch.setattr(MockMarketDataProvider, "get_daily_close_bars", fail_daily_bars)

    with TestClient(app) as isolated_client:
        anchor_response = isolated_client.get(
            "/api/v1/leveraged-etf/relationships/rel_sndk_snxx_2x/anchor"
        )
        anchor = anchor_response.json()["data"]
        calculation = isolated_client.post(
            "/api/v1/leveraged-etf/calculations",
            json={
                "relationship_id": "rel_sndk_snxx_2x",
                "anchor_version_id": anchor["id"],
                "input_side": "underlying",
                "target_price": "1827.00",
            },
        )

    assert calculation.status_code == 200
    assert calls == {"relationship": 0, "daily_bars": 0}


def test_calculation_rejects_inactive_anchor_version(client: TestClient) -> None:
    response = client.post(
        "/api/v1/leveraged-etf/calculations",
        json={
            "relationship_id": "rel_nvda_nvdl_2x",
            "anchor_version_id": "anchor_old",
            "input_side": "underlying",
            "target_price": "180.00",
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ANCHOR_VERSION_INACTIVE"


def test_profit_ratio_latest_and_history(client: TestClient) -> None:
    latest = client.get("/api/v1/profit-ratio/instruments/ins_nvda_xnas/latest")
    assert latest.status_code == 200
    assert latest.json()["data"]["ratio"] == "0.826"

    history = client.get(
        "/api/v1/profit-ratio/instruments/ins_nvda_xnas/history",
        params={"start": "2026-09-01", "end": "2026-09-04"},
    )
    assert history.status_code == 200
    data = history.json()["data"]
    assert len(data["profit_ratio_series"]) == 4
    assert len(data["price_series"]) == 4
    assert data["provider"] == "mock"

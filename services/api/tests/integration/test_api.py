from fastapi.testclient import TestClient


def test_health_uses_mock_provider(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "trafriend-api",
        "market_data_provider": "mock",
    }
    assert response.headers["X-Request-ID"].startswith("req_")


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
    assert {item["leverage_factor"] for item in data["relationships"]} == {"3", "-3"}


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

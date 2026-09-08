from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trafriend_api.scripts.capture_profit_ratio import exit_code
from trafriend_api.scripts.export_profit_ratio_contract import contract_artifacts


def test_generated_profit_ratio_contract_matches_api() -> None:
    root = Path(__file__).resolve().parents[4]
    schema, types = contract_artifacts()
    assert (root / "services/api/openapi-profit-ratio.json").read_text() == schema
    assert (root / "apps/web/src/lib/api/generated/profit-ratio.ts").read_text() == types


def test_capture_exit_codes_do_not_retry_structural_model_input_absence() -> None:
    assert exit_code(["NOT_DUE", "COMPLETE", "DATA_INSUFFICIENT"]) == 0
    assert exit_code(["PARTIAL_RETRYABLE"]) == 2
    assert exit_code(["CONFLICT"]) == 1
    assert exit_code(["EMPTY_UNIVERSE"]) == 1


@pytest.mark.parametrize("requested", ["1900-01-01", "9999-01-01"])
def test_daily_history_rejects_dates_outside_calendar_coverage(
    client: TestClient, requested: str,
) -> None:
    response = client.get(
        "/api/v1/profit-ratio/symbols/NVDA/daily",
        params={"start": requested, "end": requested},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PROFIT_RATIO_CALENDAR_RANGE_UNSUPPORTED"

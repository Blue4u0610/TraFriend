from datetime import date
from typing import Any

import httpx
import pytest

from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.infrastructure.catalog.qqq_constituents import (
    QQQ_HOLDINGS_SOURCE,
    QQQ_HOLDINGS_URL,
    fetch_qqq_constituents,
)


def _payload() -> dict[str, Any]:
    # Small synthetic contract data; no licensed full holdings snapshot.
    return {
        "cusip": "QQQ",
        "effectiveDate": "2026-09-07",
        "effectiveBusinessDate": "2026-09-04",
        "totalNumberOfHoldings": 3,
        "holdings": [
            {
                "ticker": "BBB",
                "issuerName": "Beta &amp; Company",
                "cusip": "000000002",
                "securityTypeCode": "ADR",
                "currency": "USD",
            },
            {
                "ticker": "AAA",
                "issuerName": "Alpha Company",
                "cusip": "000000001",
                "securityTypeCode": "COM",
                "currency": "USD",
            },
            {"ticker": "USD", "securityTypeCode": "CURR"},
        ],
    }


def _client(payload: object) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == QQQ_HOLDINGS_URL
        assert "APCA-API-KEY-ID" not in request.headers
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_qqq_holdings_normalizes_equities_and_reuses_canonical_identity() -> None:
    with _client(_payload()) as client:
        members = fetch_qqq_constituents(
            client=client, instrument_ids={"AAA": "ins_aaa_xnas"}
        )
        assert not client.is_closed
    assert [member.symbol for member in members] == ["AAA", "BBB"]
    assert [member.instrument_id for member in members] == [
        "ins_aaa_xnas", "ins_cusip_000000002"
    ]
    assert members[1].name == "Beta & Company"
    assert all(member.as_of == date(2026, 9, 4) for member in members)
    assert all(member.source == QQQ_HOLDINGS_SOURCE for member in members)


@pytest.mark.parametrize("security_type", ["IFUT", "CURR", "CURRCOL", "SYN"])
def test_qqq_holdings_excludes_only_known_non_equities(security_type: str) -> None:
    payload = _payload()
    payload["holdings"][2] = {"ticker": None, "securityTypeCode": security_type}
    with _client(payload) as client:
        assert len(fetch_qqq_constituents(client=client)) == 2


@pytest.mark.parametrize("security_type", ["COM", "ADR", "DRNY"])
def test_qqq_holdings_accepts_documented_equity_classes(security_type: str) -> None:
    payload = _payload()
    payload["holdings"][0]["securityTypeCode"] = security_type
    with _client(payload) as client:
        assert len(fetch_qqq_constituents(client=client)) == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("cusip", "OTHER"),
        ("effectiveBusinessDate", None),
        ("effectiveBusinessDate", "2026-09-31"),
        ("effectiveBusinessDate", "2026-09-08"),
        ("effectiveDate", "20260907"),
        ("totalNumberOfHoldings", 2),
        ("totalNumberOfHoldings", True),
        ("holdings", []),
        ("holdings", {}),
        ("holdings", [None, None, None]),
    ],
)
def test_qqq_holdings_rejects_malformed_coverage(key: str, value: object) -> None:
    payload = _payload()
    payload[key] = value
    with _client(payload) as client, pytest.raises(ProviderUnavailableError):
        fetch_qqq_constituents(client=client)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ticker", None),
        ("ticker", "bad symbol"),
        ("issuerName", ""),
        ("issuerName", "A" * 241),
        ("issuerName", "Alpha\nCompany"),
        ("cusip", None),
        ("cusip", "not-a-cusip"),
        ("currency", "EUR"),
        ("securityTypeCode", "NEW_UNKNOWN_CLASS"),
        ("securityTypeCode", []),
    ],
)
def test_qqq_holdings_rejects_malformed_equity_metadata(key: str, value: object) -> None:
    payload = _payload()
    payload["holdings"][0][key] = value
    with _client(payload) as client, pytest.raises(ProviderUnavailableError):
        fetch_qqq_constituents(client=client)


@pytest.mark.parametrize("duplicate_key", ["ticker", "cusip"])
def test_qqq_holdings_rejects_duplicate_security(duplicate_key: str) -> None:
    payload = _payload()
    payload["holdings"][0][duplicate_key] = payload["holdings"][1][duplicate_key]
    with _client(payload) as client, pytest.raises(ProviderUnavailableError, match="duplicate"):
        fetch_qqq_constituents(client=client)


def test_qqq_holdings_rejects_conflicting_canonical_ids() -> None:
    with _client(_payload()) as client, pytest.raises(ProviderUnavailableError, match="duplicate"):
        fetch_qqq_constituents(
            client=client, instrument_ids={"AAA": "same_id", "BBB": "same_id"}
        )


def test_qqq_holdings_rejects_empty_equity_coverage() -> None:
    payload = _payload()
    payload["holdings"] = [{"securityTypeCode": "CURR"}]
    payload["totalNumberOfHoldings"] = 1
    with _client(payload) as client, pytest.raises(ProviderUnavailableError, match="no supported"):
        fetch_qqq_constituents(client=client)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (503, ProviderUnavailableError),
    ],
)
def test_qqq_holdings_normalizes_http_errors(status: int, error: type[Exception]) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, text="vendor detail"))
    )
    with client, pytest.raises(error) as caught:
        fetch_qqq_constituents(client=client)
    assert "vendor detail" not in str(caught.value)


def test_qqq_holdings_normalizes_transport_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private transport detail", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderUnavailableError) as caught:
            fetch_qqq_constituents(client=client)
    assert "private transport detail" not in str(caught.value)


@pytest.mark.parametrize("body", [b"not json", b"x" * 1_000_001])
def test_qqq_holdings_rejects_invalid_response_body(body: bytes) -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    )
    with client, pytest.raises(ProviderUnavailableError):
        fetch_qqq_constituents(client=client)

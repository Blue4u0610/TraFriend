from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable

import httpx
import pytest

from trafriend_api.domain.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from trafriend_api.domain.profit_ratio_daily import (
    ProfitRatioPhase,
    ProfitRatioSession,
    calculate_endpoint,
)
from trafriend_api.infrastructure.market_data.alpaca.profit_ratio import (
    AlpacaProfitRatioCaptureProvider,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)
SESSION = ProfitRatioSession(
    date(2026, 9, 8),
    datetime(2026, 9, 8, 13, 30, tzinfo=UTC),
    datetime(2026, 9, 8, 20, tzinfo=UTC),
    date(2026, 9, 4),
)


def _bars(adjustment: str) -> list[dict[str, object]]:
    if adjustment == "raw":
        prices = (("180", "200"), ("110", "121"))
    else:
        prices = (("45", "50"), ("55", "60.5"))
    return [
        {"t": timestamp, "o": price[0], "c": price[1]}
        for timestamp, price in zip(
            ("2026-09-04T04:00:00Z", "2026-09-08T04:00:00Z"), prices
        )
    ]


def _provider(
    handler: Callable[[httpx.Request], httpx.Response], now: datetime = NOW
) -> AlpacaProfitRatioCaptureProvider:
    return AlpacaProfitRatioCaptureProvider(
        "test-key", "test-secret", {"AAA": "ins_aaa", "BBB": "ins_bbb"},
        client=httpx.Client(
            base_url="https://data.alpaca.markets", transport=httpx.MockTransport(handler)
        ),
        now=lambda: now,
    )


def test_alpaca_price_batches_raw_and_split_with_consistent_return_basis() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v2/stocks/bars"
        assert request.url.params["symbols"] == "AAA,BBB"
        assert request.url.params["feed"] == "sip"
        assert request.url.params["timeframe"] == "1Day"
        assert request.url.params["start"] == "2026-09-04T00:00:00-04:00"
        return httpx.Response(200, json={
            "bars": {symbol: _bars(request.url.params["adjustment"])
                     for symbol in ("AAA", "BBB")},
            "next_page_token": None,
        })

    provider = _provider(handler)
    inputs = provider.get_capture_inputs(["AAA", "BBB"], SESSION, ProfitRatioPhase.CLOSE)
    assert len(requests) == 2
    assert {request.url.params["adjustment"] for request in requests} == {"raw", "split"}
    assert [item.price.symbol for item in inputs] == ["AAA", "BBB"]
    for item in inputs:
        assert item.price.price == Decimal("121")
        assert item.price.previous_close == Decimal("100")
        assert item.price.price / item.price.previous_close - 1 == Decimal("0.21")
        assert item.price.market_timestamp == SESSION.closed_at
        assert item.price.observed_at == NOW
        assert item.price.source_feed == "sip"
        assert item.quality == "DELAYED"
        assert item.float_snapshot is None
        assert item.prior_distribution is None
        assert item.minutes == ()
        assert item.corporate_actions_verified is False
        assert item.minute_coverage_complete is False
        assert calculate_endpoint(item, SESSION).ratio is None


def test_alpaca_primed_history_paginates_once_and_reuses_prices_for_both_phases() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = request.url.params.get("page_token")
        assert page in (None, "next-page")
        values = _bars(request.url.params["adjustment"])
        return httpx.Response(200, json={
            "bars": {"AAA": values[:1] if page is None else values[1:]},
            "next_page_token": "next-page" if page is None else None,
        })

    provider = _provider(handler)
    provider.prime_history(["AAA"], date(2026, 9, 4), date(2026, 9, 8))
    opening = provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)
    closing = provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.CLOSE)
    assert len(requests) == 4
    assert opening[0].price.price == Decimal("110")
    assert opening[0].price.market_timestamp == SESSION.opened_at
    assert closing[0].price.price == Decimal("121")
    assert opening[0].price.previous_close == closing[0].price.previous_close == Decimal("100")


def test_alpaca_missing_symbol_is_not_fabricated_or_replaced_with_prior_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        values = _bars(request.url.params["adjustment"])
        return httpx.Response(200, json={"bars": {"AAA": values, "BBB": values[:1]}})

    inputs = _provider(handler).get_capture_inputs(["AAA", "BBB"], SESSION, ProfitRatioPhase.OPEN)
    assert [item.price.symbol for item in inputs] == ["AAA"]


def test_alpaca_absent_previous_adjusted_bar_keeps_previous_close_null() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        values = _bars(request.url.params["adjustment"])
        if request.url.params["adjustment"] == "split":
            values = values[1:]
        return httpx.Response(200, json={"bars": {"AAA": values}})

    inputs = _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.CLOSE)
    assert inputs[0].price.previous_close is None
    assert inputs[0].price.price == Decimal("121")


@pytest.mark.parametrize("phase", list(ProfitRatioPhase))
def test_alpaca_enforces_20_minute_publication_gate_before_http(phase: ProfitRatioPhase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("provider should not be called before publication delay")

    provider = _provider(handler, SESSION.instant(phase) + timedelta(minutes=19, seconds=59))
    with pytest.raises(ValueError, match="publication delay"):
        provider.get_capture_inputs(["AAA"], SESSION, phase)


@pytest.mark.parametrize("phase", list(ProfitRatioPhase))
def test_alpaca_accepts_exact_publication_boundary(phase: ProfitRatioPhase) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {"AAA": _bars(request.url.params["adjustment"])}})

    provider = _provider(handler, SESSION.instant(phase) + timedelta(minutes=20))
    assert len(provider.get_capture_inputs(["AAA"], SESSION, phase)) == 1


@pytest.mark.parametrize("timestamp", [
    "2026-09-03T04:00:00Z",  # Earlier than the requested previous session.
    "2026-09-09T04:00:00Z",  # Different future trading date.
    "2026-09-08T22:00:00Z",  # Same date, beyond the requested OPEN and current time.
    "2026-09-08T04:00:00",  # No timezone.
])
def test_alpaca_rejects_out_of_window_or_unaware_daily_timestamp(timestamp: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {"AAA": [
            {"t": timestamp, "o": "110", "c": "121"}
        ]}})

    provider = _provider(handler, SESSION.opened_at + timedelta(minutes=20))
    with pytest.raises(ProviderUnavailableError):
        provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "0", "-1", None])
def test_alpaca_rejects_invalid_price(value: object) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {"AAA": [
            {"t": "2026-09-08T04:00:00Z", "o": value, "c": "121"}
        ]}})

    with pytest.raises(ProviderUnavailableError):
        _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)


def test_alpaca_rejects_duplicate_daily_bar_across_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "bars": {"AAA": _bars("raw")},
            "next_page_token": None if request.url.params.get("page_token") else "second",
        })

    with pytest.raises(ProviderUnavailableError, match="duplicate"):
        _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)


def test_alpaca_rejects_cyclic_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": {}, "next_page_token": "same"})

    with pytest.raises(ProviderUnavailableError, match="pagination"):
        _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)


def test_alpaca_new_missing_response_cannot_reuse_previously_cached_symbol() -> None:
    available = True

    def handler(request: httpx.Request) -> httpx.Response:
        bars = {"AAA": _bars(request.url.params["adjustment"])} if available else {}
        return httpx.Response(200, json={"bars": bars})

    provider = _provider(handler)
    assert len(provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)) == 1
    available = False
    assert provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN) == ()


def test_alpaca_failed_adjusted_reload_does_not_mix_new_raw_with_old_split_cache() -> None:
    failing_reload = False

    def handler(request: httpx.Request) -> httpx.Response:
        adjustment = request.url.params["adjustment"]
        if failing_reload and adjustment == "split":
            return httpx.Response(503)
        values = _bars(adjustment)
        if failing_reload:
            values[1]["o"] = "150"
        return httpx.Response(200, json={"bars": {"AAA": values}})

    provider = _provider(handler)
    provider.prime_history(["AAA"], date(2026, 9, 4), date(2026, 9, 8))
    failing_reload = True
    with pytest.raises(ProviderUnavailableError):
        provider.prime_history(["AAA"], date(2026, 9, 4), date(2026, 9, 8))
    opening = provider.get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)
    assert opening[0].price.price == Decimal("110")
    assert opening[0].price.previous_close == Decimal("100")


@pytest.mark.parametrize("symbols", [[], ["UNKNOWN"]])
def test_alpaca_rejects_symbols_outside_stored_universe_without_http(symbols: list[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("unknown/empty symbol requests must not reach provider")

    with pytest.raises(ValueError):
        _provider(handler).get_capture_inputs(symbols, SESSION, ProfitRatioPhase.OPEN)


@pytest.mark.parametrize("payload", [None, [], {}, {"bars": None}, {"bars": {"AAA": None}}])
def test_alpaca_rejects_malformed_payload(payload: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(ProviderUnavailableError):
        _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)


@pytest.mark.parametrize(("status", "error"), [
    (401, ProviderAuthenticationError), (403, ProviderAuthenticationError),
    (429, ProviderRateLimitError), (500, ProviderUnavailableError),
])
def test_alpaca_provider_error_is_sanitized(status: int, error: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="private vendor response")

    with pytest.raises(error) as caught:
        _provider(handler).get_capture_inputs(["AAA"], SESSION, ProfitRatioPhase.OPEN)
    assert "private vendor response" not in str(caught.value)


def test_alpaca_prime_history_rejects_not_yet_completed_date() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("future historical range must not reach provider")

    provider = _provider(handler, SESSION.opened_at)
    with pytest.raises(ValueError, match="completed historical"):
        provider.prime_history(["AAA"], date(2026, 9, 4), date(2026, 9, 8))

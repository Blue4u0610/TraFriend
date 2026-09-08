from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

import httpx
import pytest

from trafriend_api.domain.errors import ProviderUnavailableError
from trafriend_api.infrastructure.calendar.profit_ratio import ProfitRatioExchangeCalendar
from trafriend_api.infrastructure.market_data.alpaca.profit_ratio import (
    AlpacaProfitRatioCaptureProvider,
)

NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
SESSION = ProfitRatioExchangeCalendar().session(date(2026, 9, 8))


def values(adjustment: str) -> list[dict[str, str]]:
    if adjustment == "raw":
        prices = (("180", "220", "170", "200"), ("110", "124", "108", "121"))
    else:
        prices = (("45", "55", "42.5", "50"), ("55", "62", "54", "60.5"))
    return [
        {"t": timestamp, "o": row[0], "h": row[1], "l": row[2], "c": row[3]}
        for timestamp, row in zip(("2026-09-04T04:00:00Z", "2026-09-08T04:00:00Z"), prices)
    ]


def provider(
    handler: Callable[[httpx.Request], httpx.Response], now: datetime = NOW
) -> AlpacaProfitRatioCaptureProvider:
    return AlpacaProfitRatioCaptureProvider(
        "fake-key",
        "fake-secret",
        {"AAA": "ins_aaa", "BBB": "ins_bbb"},
        client=httpx.Client(
            base_url="https://data.alpaca.markets", transport=httpx.MockTransport(handler)
        ),
        now=lambda: now,
    )


def test_batch_daily_ohlc_is_actual_raw_source_with_split_basis_price_return() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["feed"] == "sip"
        assert request.url.params["timeframe"] == "1Day"
        assert request.url.params["symbols"] == "AAA,BBB"
        assert request.url.params["end"] == "2026-09-08T20:01:00+00:00"
        return httpx.Response(
            200,
            json={
                "bars": {
                    symbol: values(request.url.params["adjustment"]) for symbol in ("AAA", "BBB")
                }
            },
        )

    bars = provider(handler).get_daily_price_bars(["AAA", "BBB"], [SESSION])
    assert len(requests) == 2 and len(bars) == 2
    for bar in bars:
        assert (bar.open, bar.high, bar.low, bar.close) == tuple(
            map(Decimal, ("110", "124", "108", "121"))
        )
        assert bar.previous_close == Decimal("100") and bar.price_change_return == Decimal("0.21")
        assert bar.provider == "alpaca" and bar.source_feed == "sip"
        assert bar.quality == "DELAYED" and bar.adjustment == "raw"
        assert bar.market_timestamp == datetime(2026, 9, 8, 4, tzinfo=timezone.utc)
        assert bar.observed_at == NOW
        assert bar.session_closed_at == SESSION.closed_at


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"h": "NaN"},
        {"h": "100"},
        {"l": "125"},
        {"o": "0"},
        {"t": "2026-09-08T04:00:00"},
        {"t": "2026-09-08T13:30:00Z"},
    ],
)
def test_missing_or_malformed_candle_does_not_destroy_valid_sibling(bad: dict[str, str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        source = values(request.url.params["adjustment"])
        broken = dict(source[-1])
        if not bad:
            broken.pop("h")
            broken.pop("l")
        else:
            broken.update(bad)
        return httpx.Response(200, json={"bars": {"AAA": source, "BBB": [broken]}})

    bars = provider(handler).get_daily_price_bars(["AAA", "BBB"], [SESSION])
    assert [bar.symbol for bar in bars] == ["AAA"]


def test_missing_previous_adjusted_close_does_not_suppress_genuine_candle() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        source = values(request.url.params["adjustment"])
        return httpx.Response(200, json={"bars": {"AAA": source[1:]}})

    bars = provider(handler).get_daily_price_bars(["AAA"], [SESSION])
    assert len(bars) == 1 and bars[0].previous_close is None
    assert bars[0].price_change_return is None and bars[0].high == Decimal("124")


def test_missing_symbol_is_not_substituted_from_a_previous_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        source = values(request.url.params["adjustment"])
        return httpx.Response(200, json={"bars": {"AAA": source[:1]}})

    assert provider(handler).get_daily_price_bars(["AAA"], [SESSION]) == ()


def test_candles_before_close_publication_delay_never_call_http() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("intraday prices must not be requested as complete daily candles")

    with pytest.raises(ValueError, match="completed session"):
        provider(handler, SESSION.closed_at + timedelta(minutes=19)).get_daily_price_bars(
            ["AAA"], [SESSION]
        )


def test_daily_price_pagination_keeps_complete_history_and_rejects_duplicate_symbol_date() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        source = values(request.url.params["adjustment"])
        more = not request.url.params.get("page_token")
        return httpx.Response(
            200,
            json={
                "bars": {
                    "AAA": source[:1] if more else source[1:],
                    "BBB": source[1:],
                },
                "next_page_token": "second" if more else None,
            },
        )

    bars = provider(handler).get_daily_price_bars(["AAA", "BBB"], [SESSION])
    assert len(requests) == 4 and [bar.symbol for bar in bars] == ["AAA"]


def test_new_missing_response_cannot_reuse_previously_cached_ohlc() -> None:
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "bars": {"AAA": values(request.url.params["adjustment"])} if requests <= 2 else {}
            },
        )

    adapter = provider(handler)
    assert len(adapter.get_daily_price_bars(["AAA"], [SESSION])) == 1
    assert adapter.get_daily_price_bars(["AAA"], [SESSION]) == ()


def test_raw_candle_remains_available_when_split_bar_duplicate_invalidates_only_return() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        source = values(request.url.params["adjustment"])
        if request.url.params["adjustment"] == "split":
            source += [source[-1], source[-1]]
        return httpx.Response(200, json={"bars": {"AAA": source}})

    bars = provider(handler).get_daily_price_bars(["AAA"], [SESSION])
    assert len(bars) == 1 and bars[0].previous_close is None


def test_inclusive_provider_end_does_not_request_following_day_midnight() -> None:
    ends: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ends.append(request.url.params["end"])
        return httpx.Response(200, json={"bars": {"AAA": values(request.url.params["adjustment"])}})

    adapter = provider(handler)
    adapter.prime_history(["AAA"], date(2026, 9, 4), date(2026, 9, 8))
    assert ends == ["2026-09-08T23:59:59.999999-04:00"] * 2


def test_invalid_response_shape_remains_a_normalized_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bars": []})

    with pytest.raises(ProviderUnavailableError):
        provider(handler).get_daily_price_bars(["AAA"], [SESSION])

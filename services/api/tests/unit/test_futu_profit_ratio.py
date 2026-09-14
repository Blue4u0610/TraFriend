import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest
from futu import RET_OK, BasicProperty, FeaturedProperty, SimpleField

from trafriend_api.domain.errors import ProviderUnavailableError
from trafriend_api.domain.profit_ratio_daily import (
    NasdaqConstituent,
    ProfitRatioCaptureInput,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioSession,
)
from trafriend_api.infrastructure.market_data.futu.profit_ratio import (
    FutuOpenDProfitRatioProvider,
)
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)
from trafriend_api.scripts import capture_futu_profit_ratio
from trafriend_api.scripts.capture_futu_profit_ratio import _due_phase
from trafriend_api.settings import Settings

UTC = timezone.utc
DAY = date(2026, 9, 8)
SESSION = ProfitRatioSession(
    DAY,
    datetime(2026, 9, 8, 13, 30, tzinfo=UTC),
    datetime(2026, 9, 8, 20, tzinfo=UTC),
    date(2026, 9, 4),
)
NOW = SESSION.opened_at + timedelta(minutes=21)


class Context:
    def __init__(self) -> None:
        self.screen_calls = 0
        self.snapshot_calls = 0
        self.closed = False
        self.fail_screen = False

    def get_stock_screen(self, request: Any) -> tuple[int, object]:
        self.screen_calls += 1
        if self.fail_screen:
            return -1, "private vendor failure"
        queries = request._queries
        retrieves = request._retrieves
        assert any(kind == "simpleFieldQuery" for kind, _value in queries)
        assert not any(
            kind == "simpleFieldQuery"
            and value["simpleField"] == int(SimpleField.INDEX_ID)
            for kind, value in queries
        )
        assert any(
            kind == "featuredPropertyQuery"
            and value["property"]["name"] == int(FeaturedProperty.CHIPS_PROFIT_RATIO)
            for kind, value in queries
        )
        assert ("basicProperty", {"name": int(BasicProperty.CODE)}) in retrieves
        return RET_OK, (
            True,
            2,
            [
                {
                    "stock_id": 1,
                    "results": [
                        {
                            "type": "basic",
                            "property": {"name": int(BasicProperty.CODE)},
                            "sval": "US.SNDK",
                        },
                        {
                            "type": "featured",
                            "property": {
                                "name": int(FeaturedProperty.CHIPS_PROFIT_RATIO)
                            },
                            "dval": 0.81234,
                        },
                    ],
                },
                {
                    "stock_id": 2,
                    "results": [
                        {
                            "type": "basic",
                            "property": {"name": int(BasicProperty.CODE)},
                            "sval": "US.NVDA",
                        }
                    ],
                },
            ],
        )

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        self.snapshot_calls += 1
        assert codes == ["US.SNDK"]
        return RET_OK, pd.DataFrame(
            [
                {
                    "code": "US.SNDK",
                    "update_time": "2026-09-08 09:50:00",
                    "last_price": 101.25,
                    "open_price": 100.25,
                    "prev_close_price": 100,
                }
            ]
        )

    def close(self) -> None:
        self.closed = True


class PaginatedContext(Context):
    def __init__(self) -> None:
        super().__init__()
        self.page_starts: list[int] = []

    def get_stock_screen(self, request: Any) -> tuple[int, object]:
        self.screen_calls += 1
        self.page_starts.append(request.page_from)
        symbol = "SNDK" if request.page_from == 0 else "NVDA"
        return RET_OK, (
            request.page_from != 0,
            400,
            [
                {
                    "stock_id": self.screen_calls,
                    "results": [
                        {
                            "type": "basic",
                            "property": {"name": int(BasicProperty.CODE)},
                            "sval": symbol,
                        },
                        {
                            "type": "featured",
                            "property": {
                                "name": int(FeaturedProperty.CHIPS_PROFIT_RATIO)
                            },
                            "dval": 0.5,
                        },
                    ],
                }
            ],
        )

    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        self.snapshot_calls += 1
        assert codes == ["US.SNDK", "US.NVDA"]
        return RET_OK, pd.DataFrame(
            [
                {
                    "code": code,
                    "update_time": "2026-09-08 09:50:00",
                    "last_price": 100,
                    "open_price": 99.5,
                    "prev_close_price": 99,
                }
                for code in codes
            ]
        )


class CloseContext(Context):
    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        self.snapshot_calls += 1
        return RET_OK, pd.DataFrame(
            [
                {
                    "code": code,
                    "update_time": "2026-09-08 16:20:00.197",
                    "last_price": 101.25,
                    "open_price": 100.25,
                    "prev_close_price": 100,
                }
                for code in codes
            ]
        )


class StaleContext(CloseContext):
    def get_market_snapshot(self, codes: list[str]) -> tuple[int, object]:
        ret, frame = super().get_market_snapshot(codes)
        frame.loc[:, "update_time"] = "2026-09-04 16:20:00.197"
        return ret, frame


def test_futu_provider_batches_screen_and_snapshot_without_fabricating_missing_ratio() -> None:
    context = Context()
    provider = FutuOpenDProfitRatioProvider(
        "127.0.0.1",
        11111,
        {"SNDK": "ins_sndk", "NVDA": "ins_nvda"},
        context_factory=lambda _host, _port: context,
        now=lambda: NOW,
    )

    captures = provider.get_capture_inputs(
        ["SNDK", "NVDA"], SESSION, ProfitRatioPhase.OPEN
    )

    assert len(captures) == 1
    assert captures[0].price.symbol == "SNDK"
    assert captures[0].reported_ratio == Decimal("0.81234")
    assert captures[0].price.price == Decimal("100.25")
    assert captures[0].price.previous_close == Decimal("100")
    assert captures[0].price.market_timestamp == datetime(
        2026, 9, 8, 13, 30, tzinfo=UTC
    )
    assert captures[0].quality == "UNKNOWN"
    assert context.screen_calls == context.snapshot_calls == 1
    provider.close()
    assert context.closed


def test_futu_provider_paginates_until_every_requested_symbol_is_found() -> None:
    context = PaginatedContext()
    provider = FutuOpenDProfitRatioProvider(
        "127.0.0.1",
        11111,
        {"SNDK": "ins_sndk", "NVDA": "ins_nvda"},
        context_factory=lambda _host, _port: context,
        now=lambda: NOW,
    )

    captures = provider.get_capture_inputs(
        ["SNDK", "NVDA"], SESSION, ProfitRatioPhase.OPEN
    )

    assert [capture.price.symbol for capture in captures] == ["SNDK", "NVDA"]
    assert all(capture.reported_ratio == Decimal("0.5") for capture in captures)
    assert context.page_starts == [0, 200]
    assert context.screen_calls == 2
    assert context.snapshot_calls == 1


def test_futu_provider_uses_regular_close_and_accepts_fractional_snapshot_seconds() -> None:
    context = CloseContext()
    provider = FutuOpenDProfitRatioProvider(
        "127.0.0.1",
        11111,
        {"SNDK": "ins_sndk"},
        context_factory=lambda _host, _port: context,
        now=lambda: SESSION.closed_at + timedelta(minutes=21),
    )

    captures = provider.get_capture_inputs(["SNDK"], SESSION, ProfitRatioPhase.CLOSE)

    assert len(captures) == 1
    assert captures[0].price.price == Decimal("101.25")
    assert captures[0].price.market_timestamp == SESSION.closed_at


def test_futu_provider_does_not_fall_back_to_a_previous_session_snapshot() -> None:
    provider = FutuOpenDProfitRatioProvider(
        "127.0.0.1",
        11111,
        {"SNDK": "ins_sndk"},
        context_factory=lambda _host, _port: StaleContext(),
        now=lambda: SESSION.closed_at + timedelta(minutes=21),
    )

    assert provider.get_capture_inputs(["SNDK"], SESSION, ProfitRatioPhase.CLOSE) == ()


def test_futu_provider_normalizes_vendor_failure() -> None:
    context = Context()
    context.fail_screen = True
    provider = FutuOpenDProfitRatioProvider(
        "127.0.0.1",
        11111,
        {"SNDK": "ins_sndk"},
        context_factory=lambda _host, _port: context,
        now=lambda: NOW,
    )
    with pytest.raises(ProviderUnavailableError, match="stock screening"):
        provider.get_capture_inputs(["SNDK"], SESSION, ProfitRatioPhase.OPEN)


def test_futu_ratio_validation_rejects_out_of_range_and_nonfinite_values() -> None:
    assert FutuOpenDProfitRatioProvider._ratio(-1) is None
    assert FutuOpenDProfitRatioProvider._ratio(1.01) is None
    assert FutuOpenDProfitRatioProvider._ratio("NaN") is None
    assert FutuOpenDProfitRatioProvider._ratio(0) == Decimal(0)
    assert FutuOpenDProfitRatioProvider._ratio(1) == Decimal(1)


def test_due_phase_uses_exchange_instants_and_bounded_windows() -> None:
    assert _due_phase(NOW, SESSION.opened_at, SESSION.closed_at) == ProfitRatioPhase.OPEN
    assert _due_phase(
        SESSION.closed_at + timedelta(minutes=20), SESSION.opened_at, SESSION.closed_at
    ) == ProfitRatioPhase.CLOSE
    assert _due_phase(
        SESSION.opened_at + timedelta(hours=2), SESSION.opened_at, SESSION.closed_at
    ) is None


def test_futu_worker_holiday_is_not_due_and_opend_is_not_called(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    holiday = datetime(2026, 9, 7, 14, tzinfo=UTC)
    monkeypatch.setattr(
        capture_futu_profit_ratio, "datetime", SimpleNamespace(now=lambda _tz: holiday)
    )
    monkeypatch.setattr(
        capture_futu_profit_ratio.Settings,
        "from_environment",
        lambda: Settings(database_url="postgresql://unused.invalid/test"),
    )
    monkeypatch.setattr(
        capture_futu_profit_ratio,
        "create_database_engine",
        lambda _url: pytest.fail("holiday capture must not contact PostgreSQL"),
    )
    monkeypatch.setattr(
        capture_futu_profit_ratio,
        "FutuOpenDProfitRatioProvider",
        lambda **_kwargs: pytest.fail("holiday capture must not contact OpenD"),
    )

    assert capture_futu_profit_ratio.main([]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "NOT_DUE",
        "trading_date": "2026-09-07",
    }


def test_futu_worker_uses_fresh_clock_after_provider_capture(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provider_observed_at = NOW + timedelta(seconds=1)
    clock_values = iter((NOW, NOW, provider_observed_at + timedelta(seconds=1)))

    class Clock:
        @staticmethod
        def now(_timezone: object) -> datetime:
            return next(clock_values)

    class Engine:
        disposed = False

        def dispose(self) -> None:
            self.disposed = True

    class Provider:
        closed = False

        def get_capture_inputs(
            self,
            symbols: list[str],
            session: ProfitRatioSession,
            phase: ProfitRatioPhase,
        ) -> tuple[ProfitRatioCaptureInput, ...]:
            assert symbols == ["SNDK"]
            return (
                ProfitRatioCaptureInput(
                    price=ProfitRatioPriceObservation(
                        instrument_id="ins_sndk",
                        symbol="SNDK",
                        trading_date=session.trading_date,
                        phase=phase,
                        price=Decimal("100.25"),
                        previous_close=Decimal("100"),
                        market_timestamp=session.opened_at,
                        observed_at=provider_observed_at,
                        provider="futu",
                        source_feed="stock-screen-v2+market-snapshot",
                    ),
                    quality="UNKNOWN",
                    reported_ratio=Decimal("0.5"),
                    methodology_key="FUTU_CHIPS_PROFIT_RATIO",
                    methodology_version="1",
                ),
            )

        def close(self) -> None:
            self.closed = True

    engine = Engine()
    provider = Provider()
    repository = InMemoryProfitRatioRepository(
        (NasdaqConstituent("ins_sndk", "SNDK", "Sandisk", DAY, "test"),)
    )
    monkeypatch.setattr(capture_futu_profit_ratio, "datetime", Clock)
    monkeypatch.setattr(
        capture_futu_profit_ratio.Settings,
        "from_environment",
        lambda: Settings(database_url="postgresql://app:secret@db/trafriend_prod"),
    )
    monkeypatch.setattr(
        capture_futu_profit_ratio,
        "require_writable_database_target",
        lambda _url, _environment: SimpleNamespace(
            environment=SimpleNamespace(value="PRODUCTION"),
            host="db",
            database="trafriend_prod",
        ),
    )
    monkeypatch.setattr(capture_futu_profit_ratio, "create_database_engine", lambda _url: engine)
    monkeypatch.setattr(
        capture_futu_profit_ratio,
        "PostgreSQLProfitRatioRepository",
        lambda _engine: repository,
    )
    monkeypatch.setattr(
        capture_futu_profit_ratio,
        "FutuOpenDProfitRatioProvider",
        lambda **_kwargs: provider,
    )

    assert capture_futu_profit_ratio.main([]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "COMPLETE"
    assert payload["inserted"] == 1
    assert payload["unavailable"] == 0
    assert provider.closed
    assert engine.disposed

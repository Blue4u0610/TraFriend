from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import Optional, Sequence

import pytest

from trafriend_api.application.ports.profit_ratio import (
    ProfitRatioCaptureProvider,
    ProfitRatioPersistenceOutcome,
    ProfitRatioSessionCalendar,
)
from trafriend_api.application.services.profit_ratio import ProfitRatioService
from trafriend_api.domain.errors import MarketDataProviderError, ResourceNotFoundError
from trafriend_api.domain.profit_ratio_daily import (
    ChipDistribution,
    CostBin,
    FloatSnapshot,
    NasdaqConstituent,
    ProfitRatioCaptureInput,
    ProfitRatioConflictError,
    ProfitRatioMinute,
    ProfitRatioObservation,
    ProfitRatioPhase,
    ProfitRatioPriceObservation,
    ProfitRatioRecord,
    ProfitRatioSession,
    ProfitRatioStatus,
    calculate_endpoint,
)
from trafriend_api.infrastructure.market_data.mock.profit_ratio import (
    build_mock_profit_ratio_repository,
)
from trafriend_api.infrastructure.persistence.in_memory_profit_ratio import (
    InMemoryProfitRatioRepository,
)

UTC = timezone.utc
DAY = date(2026, 9, 8)
SESSION = ProfitRatioSession(
    DAY,
    datetime(2026, 9, 8, 13, 30, tzinfo=UTC),
    datetime(2026, 9, 8, 20, tzinfo=UTC),
    date(2026, 9, 4),
)
NOW = SESSION.closed_at + timedelta(minutes=21)
MEMBER = NasdaqConstituent("ins_sndk_xnas", "SNDK", "Sandisk", DAY, "mock-constituents")
SECOND = NasdaqConstituent("ins_aapl_xnas", "AAPL", "Apple", DAY, "mock-constituents")


def price(
    phase: ProfitRatioPhase = ProfitRatioPhase.OPEN,
    amount: str = "100",
    member: NasdaqConstituent = MEMBER,
) -> ProfitRatioPriceObservation:
    return ProfitRatioPriceObservation(
        instrument_id=member.instrument_id,
        symbol=member.symbol,
        trading_date=DAY,
        phase=phase,
        price=Decimal(amount),
        previous_close=Decimal("100"),
        market_timestamp=SESSION.instant(phase),
        observed_at=NOW,
        provider="mock",
        source_feed="mock-regular",
    )


def model_input(phase: ProfitRatioPhase = ProfitRatioPhase.OPEN) -> ProfitRatioCaptureInput:
    return ProfitRatioCaptureInput(
        price=price(phase),
        quality="MOCK",
        float_snapshot=FloatSnapshot(
            MEMBER.instrument_id,
            Decimal("1000"),
            DAY,
            DAY,
            "mock-dated-float",
            NOW,
        ),
        prior_distribution=ChipDistribution(
            MEMBER.instrument_id,
            SESSION.previous_trading_date,
            (CostBin(Decimal("90"), Decimal("0.4")), CostBin(Decimal("100"), Decimal("0.6"))),
            "mock-validated-seed",
            True,
        ),
        minutes=(ProfitRatioMinute(SESSION.opened_at, Decimal("110"), Decimal("1000")),),
        corporate_actions_verified=True,
        minute_coverage_complete=True,
    )


def record(
    phase: ProfitRatioPhase = ProfitRatioPhase.OPEN,
    ratio: Optional[Decimal] = None,
    amount: str = "100",
) -> ProfitRatioRecord:
    observed_price = price(phase, amount)
    return ProfitRatioRecord(
        observation=ProfitRatioObservation(
            id="test-observation",
            instrument_id=MEMBER.instrument_id,
            symbol=MEMBER.symbol,
            trading_date=DAY,
            phase=phase,
            ratio=ratio,
            market_timestamp=observed_price.market_timestamp,
            observed_at=NOW,
            provider="mock",
            source_feed="mock-regular",
            quality="MOCK",
            status=ProfitRatioStatus.ESTIMATED
            if ratio is not None
            else ProfitRatioStatus.DATA_INSUFFICIENT,
            reason_code="" if ratio is not None else "VALIDATED_PRIOR_DISTRIBUTION_MISSING",
        ),
        price=observed_price,
    )


class Calendar(ProfitRatioSessionCalendar):
    def __init__(self, session: ProfitRatioSession = SESSION) -> None:
        self.value = session

    def session(self, trading_date: date) -> ProfitRatioSession:
        if trading_date != self.value.trading_date:
            raise ValueError("not a trading session")
        return self.value

    def sessions(self, start: date, end: date) -> Sequence[ProfitRatioSession]:
        return (self.value,) if start <= self.value.trading_date <= end else ()


class Provider(ProfitRatioCaptureProvider):
    def __init__(self, inputs: Sequence[ProfitRatioCaptureInput] = ()) -> None:
        self.inputs = inputs
        self.calls: list[tuple[str, ...]] = []
        self.fail = False

    def get_capture_inputs(
        self, symbols: Sequence[str], session: ProfitRatioSession, phase: ProfitRatioPhase
    ) -> Sequence[ProfitRatioCaptureInput]:
        self.calls.append(tuple(symbols))
        if self.fail:
            raise MarketDataProviderError("provider failure")
        return self.inputs


def service(
    provider: Provider,
    repository: Optional[InMemoryProfitRatioRepository] = None,
    now: datetime = NOW,
) -> ProfitRatioService:
    return ProfitRatioService(
        repository=repository or InMemoryProfitRatioRepository((MEMBER, SECOND)),
        calendar=Calendar(),
        provider=provider,
        now=lambda: now,
    )


def test_open_uses_only_validated_previous_session_distribution() -> None:
    opening = model_input()
    result = calculate_endpoint(opening, SESSION)
    assert result.ratio == Decimal("0.4")
    # Today's later trades must never retroactively alter the opening observation.
    assert calculate_endpoint(replace(opening, minutes=()), SESSION).ratio == result.ratio
    assert result.distribution == opening.prior_distribution


def test_break_even_cost_is_not_counted_profitable() -> None:
    inputs = model_input()
    assert calculate_endpoint(replace(inputs, price=price(amount="90")), SESSION).ratio == 0
    assert calculate_endpoint(replace(inputs, price=price(amount="101")), SESSION).ratio == 1


def test_close_turnover_uses_decimal_exponential_and_keeps_probability_mass() -> None:
    result = calculate_endpoint(model_input(ProfitRatioPhase.CLOSE), SESSION)
    assert result.ratio is not None
    with localcontext() as context:
        context.prec = 50
        expected = Decimal("0.4") * Decimal(-1).exp()
        assert result.ratio == expected
        assert result.distribution is not None
        assert sum((item.weight for item in result.distribution.bins), Decimal(0)) == 1
    assert result.distribution.trading_date == DAY


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("prior_distribution", None, "VALIDATED_PRIOR_DISTRIBUTION_MISSING"),
        ("float_snapshot", None, "EFFECTIVE_DATED_FLOAT_MISSING"),
        ("corporate_actions_verified", False, "CORPORATE_ACTION_BASIS_UNVERIFIED"),
        ("minute_coverage_complete", False, "REGULAR_SESSION_MINUTES_INCOMPLETE"),
        ("minutes", (), "REGULAR_SESSION_MINUTES_INCOMPLETE"),
    ],
)
def test_missing_required_input_never_fabricates_ratio(
    field: str, value: object, reason: str
) -> None:
    result = calculate_endpoint(
        replace(model_input(ProfitRatioPhase.CLOSE), **{field: value}), SESSION
    )
    assert result.ratio is None
    assert result.reason_code == reason


def test_invalid_seed_is_not_promoted_to_real_cost_distribution() -> None:
    inputs = model_input()
    assert inputs.prior_distribution is not None
    result = calculate_endpoint(
        replace(
            inputs,
            prior_distribution=replace(
                inputs.prior_distribution,
                seed_validated=False,
            ),
        ),
        SESSION,
    )
    assert result.ratio is None


@pytest.mark.parametrize("difference", [-4, 1])
def test_prior_state_cannot_skip_sessions_or_use_future_state(difference: int) -> None:
    inputs = model_input()
    assert inputs.prior_distribution is not None
    result = calculate_endpoint(
        replace(
            inputs,
            prior_distribution=replace(
                inputs.prior_distribution,
                trading_date=SESSION.previous_trading_date + timedelta(days=difference),
            ),
        ),
        SESSION,
    )
    assert result.reason_code == "PRIOR_DISTRIBUTION_MISMATCH"
    assert result.ratio is None


def test_future_or_undated_float_is_not_valid_model_input() -> None:
    inputs = model_input()
    assert inputs.float_snapshot is not None
    for snapshot in (
        replace(
            inputs.float_snapshot,
            effective_from=DAY - timedelta(days=4),
            effective_to=DAY - timedelta(days=1),
        ),
        replace(inputs.float_snapshot, observed_at=NOW + timedelta(seconds=1)),
    ):
        result = calculate_endpoint(replace(inputs, float_snapshot=snapshot), SESSION)
        assert result.ratio is None
        assert result.reason_code == "FLOAT_DATE_MISMATCH"


@pytest.mark.parametrize("timestamp", [SESSION.opened_at - timedelta(minutes=1), SESSION.closed_at])
def test_overnight_or_after_close_minutes_are_rejected(timestamp: datetime) -> None:
    inputs = model_input(ProfitRatioPhase.CLOSE)
    result = calculate_endpoint(
        replace(inputs, minutes=(ProfitRatioMinute(timestamp, Decimal("99"), Decimal("10")),)),
        SESSION,
    )
    assert result.reason_code == "MINUTE_SESSION_OR_ORDER_INVALID"


def test_duplicate_and_out_of_order_minutes_are_rejected() -> None:
    inputs = model_input(ProfitRatioPhase.CLOSE)
    first = inputs.minutes[0]
    later = replace(first, market_timestamp=first.market_timestamp + timedelta(minutes=1))
    for minutes in ((first, first), (later, first)):
        assert calculate_endpoint(replace(inputs, minutes=minutes), SESSION).ratio is None


@pytest.mark.parametrize("value", ["-0.1", "1.01", "NaN", "Infinity"])
def test_invalid_ratio_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        record(ratio=Decimal(value))


def test_null_status_cannot_contain_ratio() -> None:
    with pytest.raises(ValueError, match="fabricated"):
        replace(record().observation, ratio=Decimal("0.5"))


def test_naive_timestamp_and_nonpositive_price_are_rejected() -> None:
    with pytest.raises(ValueError):
        replace(price(), observed_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):
        price(amount="0")


def test_cost_distribution_requires_verified_source_and_normalized_weights() -> None:
    with pytest.raises(ValueError):
        ChipDistribution(
            MEMBER.instrument_id, DAY, (CostBin(Decimal(1), Decimal("0.5")),), "x", True
        )
    with pytest.raises(ValueError):
        ChipDistribution(MEMBER.instrument_id, DAY, (CostBin(Decimal(1), Decimal(1)),), "", True)


def test_capture_saves_real_price_but_null_ratio_without_prerequisites() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    provider = Provider((ProfitRatioCaptureInput(price()),))
    report = service(provider, repository).capture(DAY, ProfitRatioPhase.OPEN)
    assert report.inserted == 1
    assert report.data_insufficient == 1
    assert report.unavailable == 0
    assert report.status == "DATA_INSUFFICIENT"
    stored = repository.latest(MEMBER.instrument_id, DAY, ProfitRatioPhase.OPEN)
    assert stored is not None and stored.price.price == Decimal("100")
    assert stored.observation.ratio is None


def test_capture_retry_avoids_provider_calls_and_does_not_duplicate() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    provider = Provider((ProfitRatioCaptureInput(price()),))
    application = service(provider, repository)
    application.capture(DAY, ProfitRatioPhase.OPEN)
    retry = application.capture(DAY, ProfitRatioPhase.OPEN)
    assert retry.existing == 1 and retry.inserted == 0
    assert len(provider.calls) == 1
    assert len(repository.history(MEMBER.instrument_id, DAY, DAY)) == 1


def test_insufficient_observation_can_append_estimated_version_without_overwrite() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    original = repository.save(record())
    upgraded = repository.save(record(ratio=Decimal("0.4")))
    assert original.record.observation.version == 1
    assert original.record.observation.ratio is None
    assert upgraded.outcome == ProfitRatioPersistenceOutcome.UPGRADED
    assert upgraded.record.observation.version == 2
    assert len(repository._records[(MEMBER.instrument_id, DAY, ProfitRatioPhase.OPEN)]) == 2
    assert len(repository.history(MEMBER.instrument_id, DAY, DAY)) == 1


def test_explicit_retry_can_compute_with_new_verified_inputs() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record())
    provider = Provider((model_input(),))
    application = service(provider, repository)
    result = application.capture(DAY, ProfitRatioPhase.OPEN, retry_insufficient=True)
    assert result.upgraded == 1 and result.status == "COMPLETE"
    assert len(provider.calls) == 1


def test_immutable_ratio_and_price_conflicts_are_explicit() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record(ratio=Decimal("0.4")))
    for different in (record(ratio=Decimal("0.5")), record(ratio=Decimal("0.4"), amount="101")):
        with pytest.raises(ProfitRatioConflictError):
            repository.save(different)


def test_ratio_upgrade_cannot_change_original_price() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record())
    with pytest.raises(ProfitRatioConflictError):
        repository.save(record(ratio=Decimal("0.4"), amount="101"))


def test_identical_retry_ignores_observation_time_and_retains_id() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    original = record()
    repository.save(original)
    later = replace(
        original,
        observation=replace(
            original.observation, id="retry", observed_at=NOW + timedelta(minutes=1)
        ),
        price=replace(original.price, observed_at=NOW + timedelta(minutes=1)),
    )
    saved = repository.save(later)
    assert saved.outcome == ProfitRatioPersistenceOutcome.EXISTING
    assert saved.record == original


@pytest.mark.parametrize("phase", [ProfitRatioPhase.OPEN, ProfitRatioPhase.CLOSE])
def test_capture_waits_for_calendar_boundary_and_publication_delay(phase: ProfitRatioPhase) -> None:
    provider = Provider()
    application = service(provider, now=SESSION.instant(phase) + timedelta(minutes=19))
    report = application.capture(DAY, phase)
    assert report.status == "NOT_DUE" and provider.calls == []


def test_early_close_uses_actual_calendar_close_not_wall_clock() -> None:
    shortened = replace(SESSION, closed_at=SESSION.closed_at - timedelta(hours=3))
    provider = Provider()
    application = ProfitRatioService(
        InMemoryProfitRatioRepository((MEMBER,)),
        Calendar(shortened),
        provider,
        now=lambda: shortened.closed_at + timedelta(minutes=21),
    )
    assert application.capture(DAY, ProfitRatioPhase.CLOSE).status == "PARTIAL_RETRYABLE"
    assert provider.calls == [(MEMBER.symbol,)]


def test_weekend_and_holiday_sessions_never_fetch_provider() -> None:
    provider = Provider()
    application = service(provider)
    for non_session in (date(2026, 9, 6), date(2026, 9, 7)):
        with pytest.raises(ValueError, match="not a trading"):
            application.capture(non_session, ProfitRatioPhase.OPEN)
    assert provider.calls == []


def test_supported_symbol_without_price_is_retryable_but_valid_sibling_persists() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER, SECOND))
    provider = Provider((ProfitRatioCaptureInput(price()),))
    result = service(provider, repository).capture(DAY, ProfitRatioPhase.OPEN)
    assert result.status == "PARTIAL_RETRYABLE"
    assert result.inserted == 1 and result.unavailable == 1
    assert repository.latest(MEMBER.instrument_id, DAY, ProfitRatioPhase.OPEN) is not None


def test_provider_failure_is_retryable_and_does_not_write_fake_record() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    provider = Provider()
    provider.fail = True
    report = service(provider, repository).capture(DAY, ProfitRatioPhase.OPEN)
    assert report.status == "PARTIAL_RETRYABLE" and report.unavailable == 1
    assert repository.history(MEMBER.instrument_id, DAY, DAY) == ()


@pytest.mark.parametrize("bad_field", ["date", "future", "feed", "phase", "quality", "identity"])
def test_invalid_or_lagging_provider_response_never_persists(bad_field: str) -> None:
    captured = ProfitRatioCaptureInput(price())
    if bad_field == "date":
        captured = replace(captured, price=replace(captured.price, trading_date=date(2026, 9, 4)))
    elif bad_field == "future":
        captured = replace(
            captured, price=replace(captured.price, observed_at=NOW + timedelta(days=1))
        )
    elif bad_field == "feed":
        captured = replace(
            captured, price=replace(captured.price, provider="alpaca", source_feed="iex")
        )
    elif bad_field == "phase":
        captured = replace(captured, price=price(ProfitRatioPhase.CLOSE))
    elif bad_field == "identity":
        captured = replace(captured, price=replace(captured.price, instrument_id="another"))
    else:
        captured = replace(captured, quality="STALE")
    repository = InMemoryProfitRatioRepository((MEMBER,))
    report = service(Provider((captured,)), repository).capture(DAY, ProfitRatioPhase.OPEN)
    assert report.unavailable == 1 and report.inserted == 0


def test_provider_observed_timestamp_after_request_start_is_valid() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    times = iter((NOW, NOW + timedelta(seconds=1)))
    observed = replace(price(), observed_at=NOW + timedelta(milliseconds=500))
    application = ProfitRatioService(
        repository,
        Calendar(),
        Provider((ProfitRatioCaptureInput(observed),)),
        now=lambda: next(times),
    )
    assert application.capture(DAY, ProfitRatioPhase.OPEN).inserted == 1


def test_search_is_qqq_metadata_only_and_reads_never_call_provider() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER, SECOND))
    repository.save(record())
    provider = Provider()
    provider.fail = True
    application = service(provider, repository)
    assert application.search("sand") == (MEMBER,)
    assert application.search("aapl")[0] == SECOND
    assert application.search("QQQ") == ()
    assert application.daily("sndk", DAY, DAY).rows[0].open_price == Decimal("100")
    assert provider.calls == []


def test_chart_returns_true_open_close_endpoints_and_close_to_close_price_return() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record(ratio=Decimal("0.4"), amount="99"))
    repository.save(record(ProfitRatioPhase.CLOSE, Decimal("0.6"), "110"))
    result = service(Provider(), repository).daily("SNDK", DAY, DAY)
    row = result.rows[0]
    assert row.open_ratio == Decimal("0.4") and row.close_ratio == Decimal("0.6")
    assert row.price_change_return == Decimal("0.1")
    assert row.ratio_change == Decimal("0.2")
    assert row.status == "COMPLETE" and result.gaps == ()
    assert not hasattr(row, "high") and not hasattr(row, "low")


def test_missing_close_remains_not_due_without_previous_day_fallback() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record())
    history = service(Provider(), repository, SESSION.opened_at + timedelta(hours=1)).daily(
        "SNDK",
        DAY,
        DAY,
    )
    assert history.rows[0].close_ratio is None and history.rows[0].close_price is None
    assert history.rows[0].close_reason_code == "NOT_DUE"
    assert any(
        gap.phase == ProfitRatioPhase.CLOSE and gap.reason_code == "NOT_DUE" for gap in history.gaps
    )


def test_mixed_provenance_is_not_combined_into_ratio_change() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record(ratio=Decimal("0.4")))
    closing = record(ProfitRatioPhase.CLOSE, Decimal("0.6"))
    repository.save(
        replace(
            closing,
            observation=replace(closing.observation, source_feed="different-feed"),
            price=replace(closing.price, source_feed="different-feed"),
        )
    )
    history = service(Provider(), repository).daily("SNDK", DAY, DAY)
    assert history.status == "PARTIAL"
    assert history.rows[0].ratio_change is None
    assert history.rows[0].status == "PROVENANCE_MISMATCH"


def test_unsupported_symbol_and_range_validation_never_call_provider() -> None:
    provider = Provider()
    application = service(provider)
    with pytest.raises(ResourceNotFoundError):
        application.daily("QQQ", DAY, DAY)
    with pytest.raises(ValueError):
        application.daily("SNDK", DAY, DAY - timedelta(days=1))
    with pytest.raises(ValueError):
        application.daily("SNDK", DAY - timedelta(days=367), DAY)
    with pytest.raises(ValueError):
        application.search("a" * 65)
    assert provider.calls == []


def test_future_sessions_do_not_create_fabricated_chart_rows() -> None:
    application = service(Provider(), now=SESSION.opened_at - timedelta(seconds=1))
    result = application.daily("SNDK", DAY, DAY)
    assert result.status == "EMPTY" and result.rows == () and result.gaps == ()


def test_membership_refresh_retains_previously_observed_data() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save(record())
    new_member = replace(SECOND, as_of=DAY + timedelta(days=1))
    repository.save_constituents((new_member,))
    assert repository.list_constituents() == (new_member,)
    assert repository.latest(MEMBER.instrument_id, DAY, ProfitRatioPhase.OPEN) is not None


def test_membership_snapshot_is_immutable_and_latest_date_wins() -> None:
    repository = InMemoryProfitRatioRepository((MEMBER,))
    repository.save_constituents((MEMBER,))
    repository.save_constituents((replace(SECOND, as_of=DAY - timedelta(days=1)),))
    assert repository.list_constituents() == (MEMBER,)
    with pytest.raises(ProfitRatioConflictError):
        repository.save_constituents((SECOND,))
    with pytest.raises(ValueError):
        repository.save_constituents(())


def test_mock_endpoint_repository_is_deterministic_and_explicitly_synthetic() -> None:
    left = build_mock_profit_ratio_repository()
    right = build_mock_profit_ratio_repository()
    members = left.list_constituents()
    assert {member.symbol for member in members} == {"NVDA", "AAPL", "TSLA"}
    assert all(member.source == "MOCK_NASDAQ_FIXTURE" for member in members)
    for member in members:
        records = left.history(member.instrument_id, date(2026, 9, 4), date(2026, 9, 4))
        assert len(records) == 2
        assert records == right.history(member.instrument_id, date(2026, 9, 4), date(2026, 9, 4))
        assert {item.observation.phase for item in records} == set(ProfitRatioPhase)
        assert all(
            item.observation.provider == "mock" and item.observation.quality == "MOCK"
            for item in records
        )
        assert all(item.observation.ratio is not None for item in records)

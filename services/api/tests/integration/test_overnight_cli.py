from trafriend_api.scripts.capture_overnight_reference import main


def test_cli_accepts_friendly_reference_type_and_prints_debug_data(capsys) -> None:
    exit_code = main(
        (
            "--provider",
            "mock",
            "--symbols",
            "SNDK,SNXX",
            "--date",
            "2026-09-08",
            "--reference-type",
            "overnight-snapshot",
            "--verbose",
        )
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Underlying: SNDK" in output
    assert "SNXX (+2x)" in output
    assert "Request Window ET:" in output
    assert "Request Window UTC:" in output
    assert "Synchronization Difference: 0.000 ms" in output
    assert "Overall Result: VALID" in output
    assert "test-secret" not in output


def test_cli_rejects_unsupported_symbol_without_provider_request(capsys) -> None:
    exit_code = main(
        (
            "--provider",
            "mock",
            "--symbols",
            "AAPL,APPX",
            "--date",
            "2026-09-08",
        )
    )

    error = capsys.readouterr().err
    assert exit_code == 2
    assert "Overall Result: UNAVAILABLE" in error
    assert "unsupported overnight symbol" in error


def test_cli_reports_market_holiday_as_unavailable(capsys) -> None:
    exit_code = main(
        (
            "--provider",
            "mock",
            "--symbols",
            "SNDK,SNXX",
            "--date",
            "2026-09-07",
            "--reference-type",
            "overnight-open",
        )
    )

    error = capsys.readouterr().err
    assert exit_code == 2
    assert "not an exchange trading day" in error

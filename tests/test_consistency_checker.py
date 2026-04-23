"""Unit tests for :mod:`agents.consistency_checker`."""

from __future__ import annotations

from agents.consistency_checker import check_consistency


def _base_application() -> dict[str, float | int | str]:
    return {
        "name": "Test Applicant",
        "loan_amount": 100_000,
        "annual_income": 80_000,
        "credit_score": 720,
        "employment_years": 5.0,
        "existing_debt": 10_000,
    }


def test_clean_application_passes() -> None:
    result = check_consistency(_base_application())

    assert result["status"] == "PASS"
    assert result["is_consistent"] is True
    assert result["consistency_score"] == 100
    assert result["flags"] == []


def test_critical_credit_score_flag() -> None:
    app = _base_application()
    app["credit_score"] = 250  # outside FICO range

    result = check_consistency(app)

    assert result["consistency_score"] < 100
    assert any("FICO" in flag for flag in result["flags"])


def test_multiple_critical_failures_trigger_fail_status() -> None:
    app = _base_application()
    app["annual_income"] = 0
    app["loan_amount"] = 0

    result = check_consistency(app)

    assert result["status"] == "FAIL"
    assert result["consistency_score"] < 50
    assert result["flag_count"] >= 2


def test_loan_to_income_ratio_high_severity() -> None:
    app = _base_application()
    app["loan_amount"] = 1_000_000
    app["annual_income"] = 100_000  # 10x income

    result = check_consistency(app)

    assert any("5" in flag and "income" in flag.lower() for flag in result["flags"])

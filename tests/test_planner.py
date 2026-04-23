"""Unit tests for :mod:`agents.planner_agent`."""

from __future__ import annotations

from agents.planner_agent import plan_assessment


def _clean_applicant() -> dict[str, float | int | str]:
    return {
        "name": "Test Applicant",
        "loan_amount": 100_000,
        "annual_income": 80_000,
        "credit_score": 720,
        "employment_years": 5.0,
        "existing_debt": 10_000,
    }


def test_clean_input_routes_to_full_assessment() -> None:
    plan = plan_assessment(_clean_applicant())

    assert plan["strategy"] == "full_assessment"
    assert plan["skipped_agents"] == []
    assert plan["signals"] == []


def test_extreme_loan_to_income_triggers_fast_reject() -> None:
    app = _clean_applicant()
    app["loan_amount"] = 2_000_000
    app["annual_income"] = 100_000  # 20x ratio

    plan = plan_assessment(app)

    assert plan["strategy"] == "fast_reject_expected"
    assert any("loan-to-income" in s.lower() for s in plan["signals"])
    assert "Credit Analyst" in plan["skipped_agents"]


def test_subprime_with_jumbo_loan_triggers_fast_reject() -> None:
    app = _clean_applicant()
    app["credit_score"] = 450
    app["loan_amount"] = 750_000
    app["annual_income"] = 300_000  # keeps LTI <10x so only sub-prime+jumbo fires

    plan = plan_assessment(app)

    assert plan["strategy"] == "fast_reject_expected"
    assert any("fico" in s.lower() for s in plan["signals"])


def test_zero_employment_with_large_loan_triggers_fast_reject() -> None:
    app = _clean_applicant()
    app["employment_years"] = 0
    app["loan_amount"] = 250_000

    plan = plan_assessment(app)

    assert plan["strategy"] == "fast_reject_expected"
    assert any("employment" in s.lower() for s in plan["signals"])

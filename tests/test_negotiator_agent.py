"""Tests for :mod:`agents.negotiator_agent`."""

from __future__ import annotations

from agents.negotiator_agent import propose_counter_offer


def _applicant() -> dict[str, float | int]:
    return {
        "loan_amount": 300_000,  # 3.75x income — over LTI ceiling
        "annual_income": 80_000,
        "credit_score": 720,
        "employment_years": 5.0,
        "existing_debt": 5_000,
    }


def test_approved_application_has_no_counter_offer() -> None:
    result = propose_counter_offer(_applicant(), {"decision": "APPROVED"})

    assert result["applicable"] is False


def test_high_lti_triggers_right_size_counter() -> None:
    result = propose_counter_offer(
        _applicant(),
        {"decision": "HUMAN_REVIEW", "reason": "LTI 3.75x exceeds 2x ceiling"},
    )

    assert result["applicable"] is True
    assert result["counter_offers"]
    primary = result["primary_counter"]
    assert primary is not None
    assert primary["type"] == "right_size_principal"
    assert primary["counter_loan_amount"] < _applicant()["loan_amount"]
    # New LTI must be within the personal-loan 2x ceiling.
    assert primary["new_lti_multiple"] <= 2.0
    assert result["would_approve_under_counter"] is True


def test_subprime_fico_recommends_alternative_lender_tier() -> None:
    data = {
        "loan_amount": 15_000,
        "annual_income": 80_000,
        "credit_score": 620,
        "employment_years": 5.0,
        "existing_debt": 5_000,
    }
    result = propose_counter_offer(
        data, {"decision": "AUTO_REJECTED", "reason": "FICO below prime floor"}
    )

    types = {o["type"] for o in result["counter_offers"]}
    assert "alternative_lender_tier" in types


def test_deep_subprime_recommends_credit_builder() -> None:
    data = {
        "loan_amount": 10_000,
        "annual_income": 60_000,
        "credit_score": 540,
        "employment_years": 3.0,
        "existing_debt": 2_000,
    }
    result = propose_counter_offer(
        data, {"decision": "AUTO_REJECTED", "reason": "FICO 540 below near-prime"}
    )

    types = {o["type"] for o in result["counter_offers"]}
    assert "credit_builder_deferred" in types


def test_thin_employment_recommends_co_borrower() -> None:
    data = {
        "loan_amount": 10_000,
        "annual_income": 80_000,
        "credit_score": 720,
        "employment_years": 0.2,
        "existing_debt": 1_000,
    }
    result = propose_counter_offer(
        data,
        {"decision": "HUMAN_REVIEW", "reason": "Employment tenure under threshold"},
    )

    types = {o["type"] for o in result["counter_offers"]}
    assert "co_borrower_or_defer" in types

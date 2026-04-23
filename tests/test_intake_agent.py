"""Tests for :mod:`agents.intake_agent`."""

from __future__ import annotations

from agents.intake_agent import enrich_applicant


def _applicant() -> dict[str, float | int | str]:
    return {
        "name": "Jane Doe",
        "loan_amount": 20_000,
        "annual_income": 80_000,
        "credit_score": 720,
        "employment_years": 5.0,
        "existing_debt": 5_000,
    }


def test_enrich_returns_all_tool_blocks() -> None:
    result = enrich_applicant(_applicant())

    for key in (
        "credit_report",
        "velocity_check",
        "sanctions_screening",
        "cash_flow_signal",
    ):
        assert key in result
    assert len(result["tools_invoked"]) == 4
    assert result["agent"] == "Intake"


def test_enrich_summary_mentions_fico_tier_and_ofac() -> None:
    result = enrich_applicant(_applicant())

    assert "FICO tier" in result["summary"]
    assert "OFAC" in result["summary"]


def test_enrich_is_deterministic() -> None:
    a = enrich_applicant(_applicant())
    b = enrich_applicant(_applicant())

    assert a["credit_report"]["tradelines_total"] == b["credit_report"]["tradelines_total"]
    assert (
        a["velocity_check"]["hard_inquiries_30d"]
        == b["velocity_check"]["hard_inquiries_30d"]
    )

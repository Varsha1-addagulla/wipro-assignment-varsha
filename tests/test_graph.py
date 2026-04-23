"""Integration-style test of the LangGraph orchestrator with mocked LLM."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.fixture()
def mocked_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch every agent's ``call_llm`` so no external call is made."""

    import agents.base_agent as base_agent

    def fake_call_llm(
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 300,
        *,
        json_mode: bool = True,
    ) -> str:
        if not json_mode:
            return "EXECUTIVE SUMMARY\n...stub report..."
        return json.dumps(
            {
                "analysis": "Meets Fannie Mae thresholds.",
                "confidence": 90,
                "recommendation": "approve",
                "key_factors": ["credit", "income", "employment"],
                "threshold_triggered": "n/a",
            }
        )

    monkeypatch.setattr(base_agent, "call_llm", fake_call_llm)

    for module_name in (
        "agents.credit_analyst",
        "agents.income_verifier",
        "agents.risk_assessor",
        "agents.fraud_detector",
        "agents.employment_verifier",
        "agents.debt_analyzer",
        "agents.report_writer",
    ):
        module = __import__(module_name, fromlist=["call_llm"])
        monkeypatch.setattr(module, "call_llm", fake_call_llm)


def _applicant() -> dict[str, Any]:
    return {
        "name": "Jane Doe",
        "loan_amount": 150_000.0,
        "annual_income": 100_000.0,
        "credit_score": 740,
        "employment_years": 4.0,
        "existing_debt": 10_000.0,
    }


def test_run_assessment_returns_all_keys(mocked_llm: None) -> None:
    from agents.graph import run_assessment

    result = run_assessment(_applicant())

    expected_keys = {
        "consistency_checker",
        "credit_analyst",
        "income_verifier",
        "risk_assessor",
        "fraud_detector",
        "employment_verifier",
        "debt_analyzer",
        "critic",
        "report",
    }
    assert expected_keys.issubset(result.keys())
    assert result["critic"]["decision"] in {
        "APPROVED",
        "HUMAN_REVIEW",
        "AUTO_REJECTED",
    }


def test_assess_endpoint_happy_path(client, mocked_llm) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/assess",
        data=_applicant(),
    )

    assert response.status_code == 200
    body = response.get_json()
    assert "critic" in body
    assert body["critic"]["decision"] in {
        "APPROVED",
        "HUMAN_REVIEW",
        "AUTO_REJECTED",
    }


def test_assess_endpoint_rejects_invalid_payload(client) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        "/assess",
        data={
            "name": "",
            "loan_amount": 0,
            "annual_income": 0,
            "credit_score": 0,
            "employment_years": 0,
            "existing_debt": 0,
        },
    )

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_healthz(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}

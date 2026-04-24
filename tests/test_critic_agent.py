"""Unit tests for :mod:`agents.critic_agent`."""

from __future__ import annotations

from typing import Any

from agents.critic_agent import make_decision


def _agent(confidence: float, recommendation: str = "approve") -> dict[str, Any]:
    return {"confidence": confidence, "recommendation": recommendation}


def _safe_applicant() -> dict[str, Any]:
    return {
        "name": "Test User",
        "loan_amount": 50_000.0,
        "annual_income": 100_000.0,
        "credit_score": 720,
        "employment_years": 5.0,
        "existing_debt": 0.0,
    }


def _results(
    confidences: dict[str, float], consistency_score: int = 100
) -> dict[str, Any]:
    results: dict[str, Any] = {
        "consistency_checker": {
            "consistency_score": consistency_score,
            "flag_count": 0,
        }
    }
    for key, conf in confidences.items():
        rec = "approve" if conf >= 75 else ("review" if conf >= 50 else "reject")
        results[key] = _agent(conf, rec)
    return results


def test_all_high_confidence_results_in_approved() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 90,
                "income_verifier": 88,
                "risk_assessor": 85,
                "fraud_detector": 92,
                "employment_verifier": 90,
                "debt_analyzer": 89,
            }
        ),
        _safe_applicant(),
    )

    assert decision["decision"] == "APPROVED"
    assert decision["average_confidence"] > 75


def test_mid_band_triggers_human_review() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 60,
                "income_verifier": 62,
                "risk_assessor": 58,
                "fraud_detector": 65,
                "employment_verifier": 55,
                "debt_analyzer": 60,
            }
        )
    )

    assert decision["decision"] == "HUMAN_REVIEW"
    assert 50 <= decision["average_confidence"] <= 75


def test_low_average_confidence_auto_rejects() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 30,
                "income_verifier": 35,
                "risk_assessor": 40,
                "fraud_detector": 45,
                "employment_verifier": 30,
                "debt_analyzer": 35,
            }
        )
    )

    assert decision["decision"] == "AUTO_REJECTED"


def test_consistency_hard_stop() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 95,
                "income_verifier": 95,
                "risk_assessor": 95,
                "fraud_detector": 95,
                "employment_verifier": 95,
                "debt_analyzer": 95,
            },
            consistency_score=10,
        )
    )

    assert decision["decision"] == "AUTO_REJECTED"
    assert "DATA INTEGRITY" in decision["reason"]


def test_fraud_hard_stop() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 95,
                "income_verifier": 95,
                "risk_assessor": 95,
                "fraud_detector": 15,
                "employment_verifier": 95,
                "debt_analyzer": 95,
            }
        )
    )

    assert decision["decision"] == "AUTO_REJECTED"
    assert "FRAUD" in decision["reason"]


def test_empty_results_returns_auto_rejected() -> None:
    decision = make_decision({})

    assert decision["decision"] == "AUTO_REJECTED"
    assert decision["average_confidence"] == 0.0


def test_two_or_more_reject_recommendations_override_high_average() -> None:
    results = _results(
        {
            "credit_analyst": 90,
            "income_verifier": 88,
            "risk_assessor": 20,  # reject
            "fraud_detector": 92,
            "employment_verifier": 25,  # reject
            "debt_analyzer": 89,
        }
    )
    results["consistency_checker"] = {"consistency_score": 100, "flag_count": 0}
    results["fraud_detector"]["confidence"] = 92

    decision = make_decision(results, _safe_applicant())

    assert decision["decision"] == "AUTO_REJECTED"
    assert "SPECIALIST CONSENSUS" in decision["reason"]


def test_dissent_count_still_listed() -> None:
    """With consensus reject, decision is AUTO_REJECT; dissenting_agents is still populated."""
    results = _results(
        {
            "credit_analyst": 90,
            "income_verifier": 88,
            "risk_assessor": 20,
            "fraud_detector": 92,
            "employment_verifier": 25,
            "debt_analyzer": 89,
        }
    )
    results["consistency_checker"] = {"consistency_score": 100, "flag_count": 0}
    results["fraud_detector"]["confidence"] = 92

    decision = make_decision(results, _safe_applicant())
    assert decision["recommendation_rejections"] >= 2
    assert isinstance(decision["dissenting_agents"], list)


def test_stated_income_debt_rejects_toxic_file_despite_model_scores() -> None:
    """(loan+debt) / annual >> 1.0: bank-style capacity, not token confidence."""
    results = _results(
        {
            "credit_analyst": 90,
            "income_verifier": 90,
            "risk_assessor": 90,
            "fraud_detector": 90,
            "employment_verifier": 90,
            "debt_analyzer": 90,
        }
    )
    toxic = {
        "name": "High Burden",
        "loan_amount": 75_000.0,
        "annual_income": 25_000.0,
        "credit_score": 650,
        "employment_years": 2.0,
        "existing_debt": 50_000.0,
    }
    decision = make_decision(results, toxic)
    assert decision["decision"] == "AUTO_REJECTED"
    assert "CAPACITY" in decision["reason"]


def test_subprime_fico_pulled_to_human_for_high_band() -> None:
    results = _results(
        {
            "credit_analyst": 90,
            "income_verifier": 90,
            "risk_assessor": 90,
            "fraud_detector": 90,
            "employment_verifier": 90,
            "debt_analyzer": 90,
        }
    )
    subprime = {**_safe_applicant(), "credit_score": 600}
    decision = make_decision(results, subprime)
    assert decision["decision"] == "HUMAN_REVIEW"
    assert "FICO" in decision["reason"]


def test_hard_stop_flag_set_on_consistency_fail() -> None:
    decision = make_decision(
        _results(
            {
                "credit_analyst": 95,
                "income_verifier": 95,
                "risk_assessor": 95,
                "fraud_detector": 95,
                "employment_verifier": 95,
                "debt_analyzer": 95,
            },
            consistency_score=10,
        )
    )

    assert decision["hard_stop_triggered"] is True

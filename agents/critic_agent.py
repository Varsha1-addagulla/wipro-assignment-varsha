"""
Critic Decision Agent — pure logic, no LLM calls.

Thresholds (after hard stops):
  avg_confidence < 50%        → AUTO_REJECTED
  50% ≤ avg ≤ 75%             → HUMAN_REVIEW
  avg_confidence > 75%        → APPROVED  (if capacity + recommendation gates pass)

Hard overrides (checked in order, before the confidence banding):
  consistency_score < 30      → AUTO_REJECTED (data integrity)
  fraud_detector confidence < 25 → AUTO_REJECTED
  Stated **capacity** (when ``applicant`` is passed from the graph):
    loan / annual_income       → if above ``_MAX_LTI`` → AUTO_REJECTED
    (loan + existing_debt) / annual_income
                               → if above ``_MAX_COMBINED_STRESS`` → AUTO_REJECTED
  Specialist **recommendation** consensus:
    two or more ``reject``    → AUTO_REJECTED (no auto-approve on LLM number alone)
  FICO (when applicant given):
    if the band would be APPROVED but FICO < ``_MIN_FICO_FOR_AUTO_APPROVE`` → HUMAN_REVIEW
"""

from __future__ import annotations

from typing import Any

_DECISION_TO_REC = {
    "APPROVED": "approve",
    "HUMAN_REVIEW": "review",
    "AUTO_REJECTED": "reject",
}

# --- Stated-input capacity (gross annual, no tax) — simple underwriting guardrails. ---
_MAX_LTI = 1.0  # new loan / gross annual: above = auto reject on capacity
_MAX_COMBINED_STRESS = 1.0  # (new loan + existing debt) / gross annual: above = reject
_MIN_FICO_FOR_AUTO_APPROVE = 620  # if band says APPROVED, pull sub-620 to human review

AGENT_KEYS = [
    "credit_analyst",
    "income_verifier",
    "risk_assessor",
    "fraud_detector",
    "employment_verifier",
    "debt_analyzer",
]
AGENT_LABELS = {
    "credit_analyst": "Credit Analyst",
    "income_verifier": "Income Verifier",
    "risk_assessor": "Risk Assessor",
    "fraud_detector": "Fraud Detector",
    "employment_verifier": "Employment Verifier",
    "debt_analyzer": "Debt Analyzer",
}


def make_decision(
    results: dict[str, Any],
    applicant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    confidences: dict[str, float] = {}
    recommendations: dict[str, str] = {}

    for key in AGENT_KEYS:
        if key in results:
            confidences[key] = float(results[key].get("confidence", 0))
            recommendations[key] = results[key].get("recommendation", "reject")

    if not confidences:
        return {
            "agent": "Critic Decision Agent",
            "decision": "AUTO_REJECTED",
            "average_confidence": 0.0,
            "individual_confidences": {},
            "recommendations": {},
            "reject_count": 0,
            "recommendation_rejections": 0,
            "dissent_count": 0,
            "dissenting_agents": [],
            "hard_stop_triggered": False,
            "reason": "No agent results available — cannot assess application.",
        }

    avg_confidence = sum(confidences.values()) / len(confidences)
    reject_recommendations = sum(1 for r in recommendations.values() if r == "reject")
    fraud_confidence = confidences.get("fraud_detector", 100.0)
    consistency = results.get("consistency_checker", {})
    consistency_score = float(consistency.get("consistency_score", 100))
    consistency_flags = consistency.get("flag_count", 0)

    decision: str
    reason: str
    hard_stop = False
    capacity_metrics: dict[str, float] = {}

    if consistency_score < 30:
        decision = "AUTO_REJECTED"
        hard_stop = True
        reason = (
            f"DATA INTEGRITY HARD STOP: Consistency score is {consistency_score:.0f}/100 "
            f"with {consistency_flags} critical flag(s). Application rejected before agent analysis."
        )
    elif fraud_confidence < 25.0:
        decision = "AUTO_REJECTED"
        hard_stop = True
        reason = (
            f"FRAUD HARD STOP: Fraud Detector confidence is {fraud_confidence:.1f}% "
            f"(threshold: 25%). Automatic rejection regardless of other scores."
        )
    elif applicant is not None and _capacity_blocks(applicant, capacity_metrics):
        decision = "AUTO_REJECTED"
        hard_stop = True
        lti = capacity_metrics.get("loan_to_annual_income", 0.0)
        stress = capacity_metrics.get("new_plus_debt_to_annual", 0.0)
        reason = (
            "CAPACITY HARD STOP: stated loan and debt versus gross annual income fail policy. "
            f"Loan / income = {lti:.2f} (max {_MAX_LTI:.2f}). "
            f"(Loan + existing debt) / income = {stress:.2f} (max {_MAX_COMBINED_STRESS:.2f})."
        )
    elif reject_recommendations >= 2:
        decision = "AUTO_REJECTED"
        hard_stop = True
        reason = (
            f"SPECIALIST CONSENSUS: {reject_recommendations} of {len(AGENT_KEYS)} agents "
            f"recommended reject — overriding high average score ({avg_confidence:.1f}%)."
        )
    elif avg_confidence < 50.0:
        decision = "AUTO_REJECTED"
        reason = (
            f"Average agent confidence of {avg_confidence:.1f}% falls below the 50% "
            f"approval threshold. Application automatically rejected."
        )
    elif avg_confidence <= 75.0:
        decision = "HUMAN_REVIEW"
        reason = (
            f"Average agent confidence of {avg_confidence:.1f}% falls in the 50–75% "
            f"range. Application flagged for human review."
        )
    else:
        decision = "APPROVED"
        fico = int(float(applicant.get("credit_score", 700) or 0)) if applicant else 700
        if fico < _MIN_FICO_FOR_AUTO_APPROVE:
            decision = "HUMAN_REVIEW"
            reason = (
                f"Model average {avg_confidence:.1f}% exceeds 75%, but FICO {fico} is below "
                f"the {_MIN_FICO_FOR_AUTO_APPROVE} floor for auto-approval — human review required."
            )
        else:
            reason = (
                f"Average agent confidence of {avg_confidence:.1f}% exceeds the 75% "
                f"threshold. Application approved for processing."
            )

    expected_rec = _DECISION_TO_REC[decision]
    dissenting_agents = [
        AGENT_LABELS.get(k, k)
        for k, rec in recommendations.items()
        if rec != expected_rec
    ]
    dissent_count = len(dissenting_agents)
    hard_stop_triggered = hard_stop or consistency_score < 30 or fraud_confidence < 25.0

    out: dict[str, Any] = {
        "agent": "Critic Decision Agent",
        "decision": decision,
        "average_confidence": round(avg_confidence, 1),
        "individual_confidences": {
            AGENT_LABELS.get(k, k): round(v, 1) for k, v in confidences.items()
        },
        "recommendations": {
            AGENT_LABELS.get(k, k): v for k, v in recommendations.items()
        },
        "reject_count": sum(1 for r in recommendations.values() if r == "reject"),
        "recommendation_rejections": reject_recommendations,
        "dissent_count": dissent_count,
        "dissenting_agents": dissenting_agents,
        "hard_stop_triggered": hard_stop_triggered,
        "reason": reason,
    }
    if capacity_metrics:
        out["capacity"] = {k: round(v, 4) for k, v in capacity_metrics.items()}
    return out


def _capacity_blocks(
    applicant: dict[str, Any], capacity_metrics: dict[str, float]
) -> bool:
    """Return True if stated loan + debt are impossible versus gross annual income."""

    try:
        income = float(applicant.get("annual_income", 0) or 0)
        loan = float(applicant.get("loan_amount", 0) or 0)
        debt = float(applicant.get("existing_debt", 0) or 0)
    except (TypeError, ValueError):
        return True

    if income <= 0 or loan < 0 or debt < 0:
        return True

    lti = loan / income
    new_plus = (loan + debt) / income
    capacity_metrics["loan_to_annual_income"] = lti
    capacity_metrics["new_plus_debt_to_annual"] = new_plus
    if lti > _MAX_LTI or new_plus > _MAX_COMBINED_STRESS:
        return True
    return False

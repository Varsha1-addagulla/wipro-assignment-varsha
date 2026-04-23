"""
Critic Decision Agent — pure logic, no LLM calls.

Thresholds:
  avg_confidence < 50%        → AUTO_REJECTED
  50% ≤ avg ≤ 75%             → HUMAN_REVIEW
  avg_confidence > 75%        → APPROVED

Hard overrides (checked first):
  consistency_score < 30      → AUTO_REJECTED (data integrity failure)
  fraud_detector confidence < 25 → AUTO_REJECTED
"""

AGENT_KEYS = ["credit_analyst", "income_verifier", "risk_assessor", "fraud_detector", "debt_analyzer"]
AGENT_LABELS = {
    "credit_analyst": "Credit Analyst",
    "income_verifier": "Income Verifier",
    "risk_assessor": "Risk Assessor",
    "fraud_detector": "Fraud Detector",
    "debt_analyzer": "Debt Analyzer",
}


def make_decision(results: dict) -> dict:
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
            "reason": "No agent results available — cannot assess application.",
        }

    avg_confidence = sum(confidences.values()) / len(confidences)
    reject_count = sum(1 for r in recommendations.values() if r == "reject")
    fraud_confidence = confidences.get("fraud_detector", 100.0)
    consistency = results.get("consistency_checker", {})
    consistency_score = float(consistency.get("consistency_score", 100))
    consistency_flags = consistency.get("flag_count", 0)

    if consistency_score < 30:
        decision = "AUTO_REJECTED"
        reason = (
            f"DATA INTEGRITY HARD STOP: Consistency score is {consistency_score:.0f}/100 "
            f"with {consistency_flags} critical flag(s). Application rejected before agent analysis."
        )
    elif fraud_confidence < 25.0:
        decision = "AUTO_REJECTED"
        reason = (
            f"FRAUD HARD STOP: Fraud Detector confidence is {fraud_confidence:.1f}% "
            f"(threshold: 25%). Automatic rejection regardless of other scores."
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
        reason = (
            f"Average agent confidence of {avg_confidence:.1f}% exceeds the 75% "
            f"threshold. Application approved for processing."
        )

    return {
        "agent": "Critic Decision Agent",
        "decision": decision,
        "average_confidence": round(avg_confidence, 1),
        "individual_confidences": {
            AGENT_LABELS.get(k, k): round(v, 1) for k, v in confidences.items()
        },
        "recommendations": {
            AGENT_LABELS.get(k, k): v for k, v in recommendations.items()
        },
        "reject_count": reject_count,
        "reason": reason,
    }

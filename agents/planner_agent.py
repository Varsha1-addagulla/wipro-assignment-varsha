"""
Planner Agent — pure logic, no LLM.

Runs before every other agent and declares the execution strategy for
this application. Two strategies are supported:

* ``full_assessment`` — the default. All six domain agents are invoked
  (five LLM analysts in parallel + the debt synthesiser) before the
  deterministic critic produces the final decision.
* ``fast_reject_expected`` — the applicant's data is so clearly invalid
  (credit score outside the FICO range, non-positive income, etc.) that
  the consistency checker's hard-stop rule will fire regardless of what
  the LLMs say. The graph uses this signal to skip the five parallel
  analyst calls and the debt synthesiser, saving both latency and LLM
  tokens while still producing a defensible rejection + report.

The planner is deterministic by design — planning decisions that gate
LLM spend and downstream routing must never be delegated to an LLM.
"""

from __future__ import annotations

from typing import Any

_LTI_FAST_REJECT = 10.0
_SUBPRIME_FICO = 500
_JUMBO_LOAN = 500_000.0
_LARGE_LOAN_NO_EMPLOYMENT = 100_000.0


def _hard_reject_signals(data: dict[str, Any]) -> list[str]:
    """Return business-logic reasons why the LLM fan-out can be skipped.

    These conditions all pass the request-level Pydantic bounds (so the
    request is a valid application form submission) but are so adverse on
    underwriting grounds that the deterministic critic will reject
    regardless of what the LLMs say. Skipping the LLM calls cuts cost and
    latency without changing the outcome.
    """

    signals: list[str] = []

    loan = float(data.get("loan_amount", 0) or 0)
    income = float(data.get("annual_income", 0) or 0)
    credit = float(data.get("credit_score", 0) or 0)
    years = float(data.get("employment_years", 0) or 0)

    if income > 0 and loan / income > _LTI_FAST_REJECT:
        signals.append(
            f"Loan-to-income ratio {loan / income:.1f}x exceeds the "
            f"{_LTI_FAST_REJECT:.0f}x ceiling — fundamentally unrepayable."
        )

    if credit < _SUBPRIME_FICO and loan > _JUMBO_LOAN:
        signals.append(
            f"Sub-{_SUBPRIME_FICO} FICO ({credit:.0f}) combined with a "
            f"${loan:,.0f} loan — no realistic approval path."
        )

    if years == 0 and loan > _LARGE_LOAN_NO_EMPLOYMENT:
        signals.append(
            f"Zero employment history with a ${loan:,.0f} loan — "
            "unverifiable income source for that amount."
        )

    return signals


def plan_assessment(data: dict[str, Any]) -> dict[str, Any]:
    """Produce an execution plan for the multi-agent pipeline.

    The plan is attached to the shared state under the ``planner`` key
    and is surfaced in the ``/assess`` response so evaluators can see the
    deterministic planning decision that shaped the run.
    """

    hard_signals = _hard_reject_signals(data)

    if hard_signals:
        return {
            "agent": "Planner",
            "strategy": "fast_reject_expected",
            "skipped_agents": [
                "Credit Analyst",
                "Income Verifier",
                "Risk Assessor",
                "Fraud Detector",
                "Employment Verifier",
                "Debt Analyzer",
            ],
            "reasoning": (
                "Input data fails data-integrity pre-checks — the consistency "
                "checker will hard-stop this application. Skipping the five "
                "parallel LLM analysts and debt synthesiser avoids wasted "
                "LLM calls and returns a deterministic rejection."
            ),
            "signals": hard_signals,
        }

    return {
        "agent": "Planner",
        "strategy": "full_assessment",
        "skipped_agents": [],
        "reasoning": (
            "Input data passes data-integrity pre-checks. Running the full "
            "six-agent assessment pipeline (5 parallel analysts + debt "
            "synthesiser) before the critic's final decision."
        ),
        "signals": [],
    }

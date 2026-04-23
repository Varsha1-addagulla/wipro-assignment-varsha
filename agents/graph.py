"""LangGraph orchestrator for the multi-agent loan risk assessment.

The graph encodes the same three-stage DAG used by the existing app:

    START
      -> consistency_checker                (pure rules, pre-assessment gate)
      -> [credit_analyst, income_verifier,
          risk_assessor, fraud_detector,
          employment_verifier]              (parallel LLM fan-out)
      -> debt_analyzer                      (synthesises parallel results)
      -> critic                             (pure-logic final decision)
      -> report                             (LLM narrative)
      -> END

All existing agent modules are reused as-is. This module only wraps them
as ``StateGraph`` nodes; it does not reimplement any business logic.

LangGraph runs the five analyst nodes in parallel because they each fan
out from ``consistency_checker`` and all converge on ``debt_analyzer``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.consistency_checker import check_consistency
from agents.credit_analyst import analyze_credit
from agents.critic_agent import make_decision
from agents.debt_analyzer import analyze_debt
from agents.employment_verifier import verify_employment
from agents.fraud_detector import detect_fraud
from agents.income_verifier import verify_income
from agents.report_writer import write_report
from agents.risk_assessor import assess_risk
from logging_config import get_logger

_LOG = get_logger(__name__)


class AssessmentState(TypedDict, total=False):
    """Shared state passed between graph nodes.

    Each node writes its own key; parallel nodes therefore never conflict
    on the same slot, so LangGraph's default "last-writer-wins" reducer is
    safe here without a custom reducer.
    """

    applicant: dict[str, Any]
    consistency_checker: dict[str, Any]
    credit_analyst: dict[str, Any]
    income_verifier: dict[str, Any]
    risk_assessor: dict[str, Any]
    fraud_detector: dict[str, Any]
    employment_verifier: dict[str, Any]
    debt_analyzer: dict[str, Any]
    critic: dict[str, Any]
    report: dict[str, Any]


def _safe(
    fn: Callable[..., dict[str, Any]], *args: Any, agent_label: str
) -> dict[str, Any]:
    """Run an agent and contain failures so the graph always completes.

    Returns a schema-compatible ``reject`` record on any failure so the
    critic still receives a valid result for every agent.
    """

    try:
        return fn(*args)
    except Exception as exc:
        # Orchestration-level safety net: every agent failure must degrade
        # gracefully so the critic still receives a complete result set.
        _LOG.warning("agent_failed", agent=agent_label, error=str(exc))
        return {
            "agent": agent_label,
            "analysis": f"Agent error: {exc}",
            "confidence": 0.0,
            "recommendation": "reject",
            "key_factors": ["Agent encountered an error"],
        }


# --- Nodes -------------------------------------------------------------------


def consistency_node(state: AssessmentState) -> dict[str, Any]:
    return {"consistency_checker": check_consistency(state["applicant"])}


def credit_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "credit_analyst": _safe(
            analyze_credit, state["applicant"], agent_label="Credit Analyst"
        )
    }


def income_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "income_verifier": _safe(
            verify_income, state["applicant"], agent_label="Income Verifier"
        )
    }


def risk_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "risk_assessor": _safe(
            assess_risk, state["applicant"], agent_label="Risk Assessor"
        )
    }


def fraud_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "fraud_detector": _safe(
            detect_fraud, state["applicant"], agent_label="Fraud Detector"
        )
    }


def employment_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "employment_verifier": _safe(
            verify_employment,
            state["applicant"],
            agent_label="Employment Verifier",
        )
    }


_PARALLEL_KEYS: tuple[str, ...] = (
    "credit_analyst",
    "income_verifier",
    "risk_assessor",
    "fraud_detector",
    "employment_verifier",
)


def debt_node(state: AssessmentState) -> dict[str, Any]:
    prior = {key: state.get(key, {}) for key in _PARALLEL_KEYS}
    return {
        "debt_analyzer": _safe(
            analyze_debt,
            state["applicant"],
            prior,
            agent_label="Debt Analyzer",
        )
    }


_CRITIC_KEYS: tuple[str, ...] = (
    "consistency_checker",
    *_PARALLEL_KEYS,
    "debt_analyzer",
)


def critic_node(state: AssessmentState) -> dict[str, Any]:
    results = {key: state.get(key, {}) for key in _CRITIC_KEYS}
    return {"critic": make_decision(results)}


_REPORT_KEYS: tuple[str, ...] = (*_CRITIC_KEYS, "critic")


def report_node(state: AssessmentState) -> dict[str, Any]:
    results = {key: state.get(key, {}) for key in _REPORT_KEYS}
    return {
        "report": _safe(
            write_report,
            state["applicant"],
            results,
            agent_label="Report Writer",
        )
    }


# --- Graph -------------------------------------------------------------------

# LangGraph treats TypedDict field names and node names as a single channel
# namespace, so node identifiers must not collide with state keys. Nodes get
# a ``_node`` suffix while the state keys (and therefore the /assess response
# shape consumed by the frontend) stay unchanged.
_NODE_CONSISTENCY = "consistency_node"
_NODE_CREDIT = "credit_node"
_NODE_INCOME = "income_node"
_NODE_RISK = "risk_node"
_NODE_FRAUD = "fraud_node"
_NODE_EMPLOYMENT = "employment_node"
_NODE_DEBT = "debt_node"
_NODE_CRITIC = "critic_node"
_NODE_REPORT = "report_node"

_PARALLEL_NODE_NAMES: tuple[str, ...] = (
    _NODE_CREDIT,
    _NODE_INCOME,
    _NODE_RISK,
    _NODE_FRAUD,
    _NODE_EMPLOYMENT,
)


def _build_graph() -> Any:
    graph = StateGraph(AssessmentState)

    graph.add_node(_NODE_CONSISTENCY, consistency_node)
    graph.add_node(_NODE_CREDIT, credit_node)
    graph.add_node(_NODE_INCOME, income_node)
    graph.add_node(_NODE_RISK, risk_node)
    graph.add_node(_NODE_FRAUD, fraud_node)
    graph.add_node(_NODE_EMPLOYMENT, employment_node)
    graph.add_node(_NODE_DEBT, debt_node)
    graph.add_node(_NODE_CRITIC, critic_node)
    graph.add_node(_NODE_REPORT, report_node)

    graph.add_edge(START, _NODE_CONSISTENCY)

    for name in _PARALLEL_NODE_NAMES:
        graph.add_edge(_NODE_CONSISTENCY, name)

    for name in _PARALLEL_NODE_NAMES:
        graph.add_edge(name, _NODE_DEBT)

    graph.add_edge(_NODE_DEBT, _NODE_CRITIC)
    graph.add_edge(_NODE_CRITIC, _NODE_REPORT)
    graph.add_edge(_NODE_REPORT, END)

    return graph.compile()


GRAPH = _build_graph()


def run_assessment(applicant: dict[str, Any]) -> dict[str, Any]:
    """Execute the orchestration graph and return the flat result dict
    used by the existing ``/assess`` response contract.
    """

    final_state: AssessmentState = GRAPH.invoke({"applicant": applicant})
    return {
        "consistency_checker": final_state.get("consistency_checker", {}),
        "credit_analyst": final_state.get("credit_analyst", {}),
        "income_verifier": final_state.get("income_verifier", {}),
        "risk_assessor": final_state.get("risk_assessor", {}),
        "fraud_detector": final_state.get("fraud_detector", {}),
        "employment_verifier": final_state.get("employment_verifier", {}),
        "debt_analyzer": final_state.get("debt_analyzer", {}),
        "critic": final_state.get("critic", {}),
        "report": final_state.get("report", {}),
    }

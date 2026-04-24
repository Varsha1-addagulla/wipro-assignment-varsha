"""LangGraph orchestrator for the multi-agent loan risk assessment.

Topology (see ARCHITECTURE for full discussion):

    START
      -> intake                           (pure-logic tool-use agent:
                                           credit bureau, velocity check,
                                           OFAC SDN, bank-statement signal)
      -> planner                          (pure-logic strategy selector)
      -> consistency_checker              (pure-logic data-integrity gate)
      -> [conditional routing]
           if strategy == fast_reject_expected or consistency hard-stops:
               -> critic
           else:
               -> [credit_analyst, income_verifier, risk_assessor,
                   fraud_detector, employment_verifier]   (parallel LLMs)
               -> debt_analyzer                           (LLM synthesis)
               -> critic
      -> negotiator                       (pure-logic counter-offer proposer;
                                           only emits structured offers when
                                           decision != APPROVED)
      -> report                           (LLM narrative)
      -> END

Every analyst runs inside :func:`_safe`, which:

* times the call and attaches ``latency_ms`` to the result,
* validates / coerces the LLM JSON against :class:`AnalystResponse`,
* converts unexpected exceptions into a schema-compatible ``reject``
  record so the critic always receives a complete result set.
"""

from __future__ import annotations

import time
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
from agents.intake_agent import enrich_applicant
from agents.negotiator_agent import propose_counter_offer
from agents.planner_agent import plan_assessment
from agents.report_writer import write_report
from agents.response_schemas import coerce_analyst_response
from agents.risk_assessor import assess_risk
from logging_config import get_logger

_LOG = get_logger(__name__)


class AssessmentState(TypedDict, total=False):
    """Shared state passed between graph nodes.

    Each node writes its own key; the five parallel analysts therefore
    never conflict on the same slot, so LangGraph's default "last writer
    wins" reducer is safe here without a custom reducer.
    """

    applicant: dict[str, Any]
    intake: dict[str, Any]
    planner: dict[str, Any]
    consistency_checker: dict[str, Any]
    credit_analyst: dict[str, Any]
    income_verifier: dict[str, Any]
    risk_assessor: dict[str, Any]
    fraud_detector: dict[str, Any]
    employment_verifier: dict[str, Any]
    debt_analyzer: dict[str, Any]
    critic: dict[str, Any]
    negotiation: dict[str, Any]
    report: dict[str, Any]


def _safe(
    fn: Callable[..., dict[str, Any]],
    *args: Any,
    agent_label: str,
    validate: bool = True,
) -> dict[str, Any]:
    """Run an agent with timing, schema validation, and error containment.

    Every analyst result carries a ``latency_ms`` field so operators (and
    the UI) can see which agent dominates the critical path.
    """

    started = time.perf_counter()
    try:
        raw = fn(*args)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _LOG.warning(
            "agent_failed",
            agent=agent_label,
            latency_ms=elapsed_ms,
            error=str(exc),
        )
        fallback = {
            "agent": agent_label,
            "analysis": f"Agent error: {exc}",
            "confidence": 0.0,
            "recommendation": "reject",
            "key_factors": ["Agent encountered an error"],
        }
        fallback["latency_ms"] = elapsed_ms
        return fallback

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if validate:
        try:
            raw = coerce_analyst_response(raw, agent_label=agent_label)
        except Exception as exc:
            _LOG.warning(
                "agent_response_invalid",
                agent=agent_label,
                latency_ms=elapsed_ms,
                error=str(exc),
            )
            raw = {
                "agent": agent_label,
                "analysis": f"Agent produced invalid response: {exc}",
                "confidence": 0.0,
                "recommendation": "reject",
                "key_factors": ["Malformed LLM output"],
            }

    raw["latency_ms"] = elapsed_ms
    return raw


# --- State / node naming -----------------------------------------------------

_PARALLEL_STATE_KEYS: tuple[str, ...] = (
    "credit_analyst",
    "income_verifier",
    "risk_assessor",
    "fraud_detector",
    "employment_verifier",
)

_CRITIC_STATE_KEYS: tuple[str, ...] = (
    "consistency_checker",
    *_PARALLEL_STATE_KEYS,
    "debt_analyzer",
)

_REPORT_STATE_KEYS: tuple[str, ...] = (
    *_CRITIC_STATE_KEYS,
    "critic",
    "planner",
    "intake",
    "negotiation",
)

# LangGraph treats TypedDict field names and node names as a single channel
# namespace, so node identifiers must not collide with state keys. Nodes get
# a ``_node`` suffix while the state keys (and therefore the /assess response
# shape consumed by the frontend) stay unchanged.
_NODE_INTAKE = "intake_node"
_NODE_PLANNER = "planner_node"
_NODE_CONSISTENCY = "consistency_node"
_NODE_CREDIT = "credit_node"
_NODE_INCOME = "income_node"
_NODE_RISK = "risk_node"
_NODE_FRAUD = "fraud_node"
_NODE_EMPLOYMENT = "employment_node"
_NODE_DEBT = "debt_node"
_NODE_CRITIC = "critic_node"
_NODE_NEGOTIATOR = "negotiator_node"
_NODE_REPORT = "report_node"

_PARALLEL_NODE_NAMES: tuple[str, ...] = (
    _NODE_CREDIT,
    _NODE_INCOME,
    _NODE_RISK,
    _NODE_FRAUD,
    _NODE_EMPLOYMENT,
)


# --- Nodes -------------------------------------------------------------------


def intake_node(state: AssessmentState) -> dict[str, Any]:
    return {"intake": enrich_applicant(state["applicant"])}


def planner_node(state: AssessmentState) -> dict[str, Any]:
    return {"planner": plan_assessment(state["applicant"])}


def consistency_node(state: AssessmentState) -> dict[str, Any]:
    result = check_consistency(state["applicant"])
    return {"consistency_checker": result}


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


def debt_node(state: AssessmentState) -> dict[str, Any]:
    prior = {key: state.get(key, {}) for key in _PARALLEL_STATE_KEYS}
    return {
        "debt_analyzer": _safe(
            analyze_debt,
            state["applicant"],
            prior,
            agent_label="Debt Analyzer",
        )
    }


def critic_node(state: AssessmentState) -> dict[str, Any]:
    results = {key: state.get(key, {}) for key in _CRITIC_STATE_KEYS}
    return {"critic": make_decision(results, state.get("applicant"))}


def negotiator_node(state: AssessmentState) -> dict[str, Any]:
    return {
        "negotiation": propose_counter_offer(
            state["applicant"], state.get("critic", {})
        )
    }


def report_node(state: AssessmentState) -> dict[str, Any]:
    results = {key: state.get(key, {}) for key in _REPORT_STATE_KEYS}
    return {
        "report": _safe(
            write_report,
            state["applicant"],
            results,
            agent_label="Report Writer",
            validate=False,
        )
    }


# --- Routing -----------------------------------------------------------------


def _route_after_consistency(state: AssessmentState) -> list[str]:
    """Choose whether to run the expensive LLM fan-out.

    Skips the five parallel analysts (and the debt synthesiser) when
    either the planner expects a fast reject or the consistency checker
    has already hard-failed the data. In both cases the critic's pure
    rules will produce an ``AUTO_REJECTED`` decision, so the LLM spend
    would be pure waste.
    """

    planner = state.get("planner", {})
    consistency = state.get("consistency_checker", {})

    if planner.get("strategy") == "fast_reject_expected":
        return [_NODE_CRITIC]
    if float(consistency.get("consistency_score", 100)) < 30:
        return [_NODE_CRITIC]

    return list(_PARALLEL_NODE_NAMES)


# --- Graph -------------------------------------------------------------------


def _build_graph() -> Any:
    graph = StateGraph(AssessmentState)

    graph.add_node(_NODE_INTAKE, intake_node)
    graph.add_node(_NODE_PLANNER, planner_node)
    graph.add_node(_NODE_CONSISTENCY, consistency_node)
    graph.add_node(_NODE_CREDIT, credit_node)
    graph.add_node(_NODE_INCOME, income_node)
    graph.add_node(_NODE_RISK, risk_node)
    graph.add_node(_NODE_FRAUD, fraud_node)
    graph.add_node(_NODE_EMPLOYMENT, employment_node)
    graph.add_node(_NODE_DEBT, debt_node)
    graph.add_node(_NODE_CRITIC, critic_node)
    graph.add_node(_NODE_NEGOTIATOR, negotiator_node)
    graph.add_node(_NODE_REPORT, report_node)

    graph.add_edge(START, _NODE_INTAKE)
    graph.add_edge(_NODE_INTAKE, _NODE_PLANNER)
    graph.add_edge(_NODE_PLANNER, _NODE_CONSISTENCY)

    graph.add_conditional_edges(
        _NODE_CONSISTENCY,
        _route_after_consistency,
        [*_PARALLEL_NODE_NAMES, _NODE_CRITIC],
    )

    for name in _PARALLEL_NODE_NAMES:
        graph.add_edge(name, _NODE_DEBT)

    graph.add_edge(_NODE_DEBT, _NODE_CRITIC)
    graph.add_edge(_NODE_CRITIC, _NODE_NEGOTIATOR)
    graph.add_edge(_NODE_NEGOTIATOR, _NODE_REPORT)
    graph.add_edge(_NODE_REPORT, END)

    return graph.compile()


GRAPH = _build_graph()


def run_assessment(applicant: dict[str, Any]) -> dict[str, Any]:
    """Execute the orchestration graph and return the flat result dict
    used by the ``/assess`` response contract.
    """

    final_state: AssessmentState = GRAPH.invoke({"applicant": applicant})
    return {
        "intake": final_state.get("intake", {}),
        "planner": final_state.get("planner", {}),
        "consistency_checker": final_state.get("consistency_checker", {}),
        "credit_analyst": final_state.get("credit_analyst", {}),
        "income_verifier": final_state.get("income_verifier", {}),
        "risk_assessor": final_state.get("risk_assessor", {}),
        "fraud_detector": final_state.get("fraud_detector", {}),
        "employment_verifier": final_state.get("employment_verifier", {}),
        "debt_analyzer": final_state.get("debt_analyzer", {}),
        "critic": final_state.get("critic", {}),
        "negotiation": final_state.get("negotiation", {}),
        "report": final_state.get("report", {}),
    }

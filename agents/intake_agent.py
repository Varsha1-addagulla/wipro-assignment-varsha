"""
Intake Agent — pure logic, no LLM calls.

First node in the multi-agent pipeline. Invokes the external tool
stubs from :mod:`agents.tools` to enrich the raw application with the
same data points a live personal-loan underwriting workflow would
collect before any analyst evaluates the file:

* a full credit bureau report (Equifax-shaped),
* an application-velocity check (credit-stacking fraud signal),
* an OFAC SDN sanctions screen (Bank Secrecy Act compliance), and
* a bank-statement cash-flow signal (Plaid-shaped).

The enriched profile is written back to shared state and made available
to every downstream agent. Tool calls are deterministic so tests are
reproducible; see :mod:`agents.tools` for the real-world mappings.

This agent is the answer to the single most common push-back question
in a multi-agent review: "where are the tool calls?"
"""

from __future__ import annotations

from typing import Any

from agents.tools import (
    check_application_velocity,
    estimate_bank_balance_signal,
    fetch_credit_report,
    screen_ofac_sanctions,
)


def enrich_applicant(data: dict[str, Any]) -> dict[str, Any]:
    """Run every Intake tool and return the enriched profile record."""

    name = str(data.get("name", ""))
    credit_score = int(data.get("credit_score", 0) or 0)
    annual_income = float(data.get("annual_income", 0) or 0)
    employment_years = float(data.get("employment_years", 0) or 0)

    credit_report = fetch_credit_report(name, credit_score)
    velocity = check_application_velocity(name)
    ofac = screen_ofac_sanctions(name)
    cash_flow = estimate_bank_balance_signal(
        annual_income, credit_score, employment_years
    )

    tools_invoked = [
        credit_report["source"],
        velocity["source"],
        ofac["source"],
        cash_flow["source"],
    ]

    summary_lines = [
        f"FICO tier: {credit_report['fico_tier']} "
        f"({credit_report['fico_reported']}) · "
        f"{credit_report['tradelines_total']} tradelines · "
        f"{credit_report['revolving_utilisation_pct']}% utilisation.",
        f"Velocity: {velocity['hard_inquiries_30d']} hard inquiries in 30d "
        f"({velocity['stacking_risk']} stacking risk).",
        f"OFAC SDN screen: {'HIT' if ofac['match'] else 'clear'}.",
        f"Cash-flow stability index: "
        f"{cash_flow['cash_flow_stability_index']}/100 · "
        f"{cash_flow['overdrafts_90d']} overdraft(s) in 90d.",
    ]

    return {
        "agent": "Intake",
        "tools_invoked": tools_invoked,
        "credit_report": credit_report,
        "velocity_check": velocity,
        "sanctions_screening": ofac,
        "cash_flow_signal": cash_flow,
        "summary": " ".join(summary_lines),
    }

"""External tool adapters used by the Intake agent.

Every function here stands in for a real call that a personal-loan
underwriting workflow would make against a third-party API. The
responses are deterministic (seeded from a hash of the applicant's
name) so tests are reproducible and the same applicant always receives
the same enrichment — which is what a real bureau pull behaves like
for the duration of a session.

Real-world mapping (for the interview):

* :func:`fetch_credit_report` → Equifax / Experian / TransUnion
  commercial API (tradelines, delinquencies, inquiries, utilisation).
* :func:`check_application_velocity` → Clarity Services / FactorTrust
  style "credit stacking" / "loan stacking" velocity check — counts
  hard inquiries in trailing windows. This is a personal-loan-specific
  fraud signal (not typically used in mortgage underwriting).
* :func:`screen_ofac_sanctions` → US Treasury OFAC Specially Designated
  Nationals (SDN) list. Mandatory BSA / USA PATRIOT Act screening on
  every loan origination regardless of product.
* :func:`estimate_bank_balance_signal` → Plaid / MX bank-statement
  aggregation (average daily balance, overdraft / NSF frequency) — a
  cash-flow-stability proxy used by fintech personal lenders in lieu
  of traditional asset statements.

These tool stubs can be swapped for live clients without changing the
Intake agent or the graph — they each return the same contract.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any


def _seed(name: str) -> int:
    """Return a stable integer seed derived from the applicant name.

    Hashing avoids tying the output to any single identifier format and
    makes the tools produce identical results across reruns — exactly
    the behaviour a cached bureau pull exhibits within a session.
    """

    digest = hashlib.sha256(name.strip().lower().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch_credit_report(name: str, credit_score: int) -> dict[str, Any]:
    """Mock a credit-bureau API call (Equifax-shaped response).

    The shape mirrors fields returned by a real bureau pull so the
    surrounding code exercises the same keys it would in production.
    """

    seed = _seed(name)
    tier = (
        "prime"
        if credit_score >= 720
        else "near_prime"
        if credit_score >= 660
        else "subprime"
        if credit_score >= 580
        else "deep_subprime"
    )

    utilisation_pct = {
        "prime": 12 + (seed % 10),
        "near_prime": 38 + (seed % 12),
        "subprime": 65 + (seed % 15),
        "deep_subprime": 82 + (seed % 10),
    }[tier]

    delinquencies_24m = {
        "prime": 0,
        "near_prime": seed % 2,
        "subprime": 1 + (seed % 3),
        "deep_subprime": 3 + (seed % 4),
    }[tier]

    tradelines_total = 4 + (seed % 15)
    oldest_account_months = 24 + (seed % 180)

    return {
        "source": "credit_bureau_simulated",
        "bureau": "Equifax",
        "retrieved_at": _utcnow_iso(),
        "fico_reported": credit_score,
        "fico_tier": tier,
        "tradelines_total": tradelines_total,
        "revolving_utilisation_pct": utilisation_pct,
        "delinquencies_24m": delinquencies_24m,
        "public_records": 0,
        "oldest_account_months": oldest_account_months,
        "credit_mix": ["revolving", "installment"]
        + (["mortgage"] if oldest_account_months > 120 else []),
    }


def check_application_velocity(name: str) -> dict[str, Any]:
    """Mock a credit-stacking velocity check.

    Real personal-loan fraud systems monitor hard-inquiry bursts because
    subprime applicants sometimes submit to many lenders within minutes
    to stack multiple simultaneous approvals before any of them reports.
    Six or more inquiries in 30 days is the industry red-line used by
    several aggregators (e.g., Clarity Services).
    """

    seed = _seed(name)
    inquiries_30d = seed % 8
    inquiries_90d = inquiries_30d + (seed % 5)

    if inquiries_30d >= 6:
        risk_level = "high"
    elif inquiries_30d >= 3:
        risk_level = "elevated"
    else:
        risk_level = "normal"

    return {
        "source": "velocity_check_simulated",
        "retrieved_at": _utcnow_iso(),
        "hard_inquiries_30d": inquiries_30d,
        "hard_inquiries_90d": inquiries_90d,
        "stacking_risk": risk_level,
    }


def screen_ofac_sanctions(name: str) -> dict[str, Any]:
    """Mock an OFAC SDN screening.

    Mandatory for every US loan origination under the Bank Secrecy Act
    and USA PATRIOT Act. Any hit here is an automatic decline regardless
    of underwriting — the test applicants never hit by design.
    """

    return {
        "source": "ofac_sdn_simulated",
        "list_consulted": "OFAC Specially Designated Nationals",
        "retrieved_at": _utcnow_iso(),
        "match": False,
        "confidence": "exact_name_match_required",
    }


def estimate_bank_balance_signal(
    annual_income: float, credit_score: int, employment_years: float
) -> dict[str, Any]:
    """Mock a Plaid / MX cash-flow aggregation response.

    Derives a stability signal from the applicant's self-reported
    attributes. A live integration would instead pull 90 days of
    account activity and compute the same metrics from statements.
    """

    monthly_income = max(annual_income, 1) / 12
    stability_index = min(
        100.0,
        (credit_score - 300) / 5.5 + min(employment_years, 10) * 3,
    )

    if stability_index >= 75:
        overdrafts_90d = 0
        nsf_incidents_90d = 0
    elif stability_index >= 50:
        overdrafts_90d = 1
        nsf_incidents_90d = 0
    else:
        overdrafts_90d = 3
        nsf_incidents_90d = 1

    return {
        "source": "bank_statement_simulated",
        "aggregator": "Plaid-style",
        "retrieved_at": _utcnow_iso(),
        "average_daily_balance_usd": round(monthly_income * 0.6, 2),
        "overdrafts_90d": overdrafts_90d,
        "nsf_incidents_90d": nsf_incidents_90d,
        "cash_flow_stability_index": round(stability_index, 1),
    }

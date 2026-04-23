"""
Negotiator Agent — pure logic, no LLM calls.

Runs after the critic. When the deterministic decision is not
``APPROVED`` the negotiator inspects the applicant's actual numbers
and produces concrete counter-offers drawn from real personal-loan
underwriting practice. Each counter-offer is then re-evaluated by the
same deterministic gates the critic uses, so a claim of "would approve
under counter-offer" is verifiable rather than rhetorical.

Counter-offer playbook (industry practice):

* High loan-to-income → right-size the principal to ≤ 1.5× annual
  income. This is the standard unsecured-lender resolution (SoFi,
  Marcus, LendingClub, Upgrade all underwrite within a narrow
  LTI band).
* High DTI → reduce the principal until DTI ≤ 40%. Personal loans
  are not governed by the Dodd-Frank QM 43% rule (that is mortgage
  only); 40–45% is the published ceiling across major prime personal
  lenders.
* FICO under the prime floor (660) but ≥ 580 → recommend a near-prime
  or subprime lender product tier (Avant, OneMain, Upstart).
* FICO under 580 → recommend a credit-builder loan first and a
  6-month deferred re-application (Self Financial / secured products).
* Employment under 6 months → recommend a co-borrower or a deferred
  decision (thin-employment resolution).

No counter is ever produced when the decision is already
``APPROVED`` — the response in that case is an ``applicable: False``
record so the UI can render nothing instead of a misleading card.
"""

from __future__ import annotations

from typing import Any

# Thresholds used by the counter-offer logic.
_LTI_TARGET = 1.5  # personal-loan right-sizing target
_LTI_CEILING = 2.0  # above this, always counter with right-sizing
_DTI_TARGET = 0.40  # 40% DTI — industry personal-loan ceiling
_DTI_TRIGGER = 0.43  # DTI above this triggers a counter
_FICO_PRIME_FLOOR = 660
_FICO_NEAR_PRIME_FLOOR = 580
_EMPLOYMENT_MIN_MONTHS = 6  # 0.5 years
_DEBT_SERVICE_FACTOR = 0.02  # 2% of existing debt treated as monthly service


def _monthly_income(annual_income: float) -> float:
    return max(annual_income, 0.0) / 12


def _monthly_payment(loan_amount: float) -> float:
    """Match the simple monthly-payment proxy used across the project."""

    if loan_amount <= 0:
        return 0.0
    return (loan_amount / 60) * 1.0417


def _dti(data: dict[str, Any], loan_amount_override: float | None = None) -> float:
    """Return DTI as a 0–1 fraction (NOT a percentage)."""

    loan = float(
        loan_amount_override
        if loan_amount_override is not None
        else data.get("loan_amount", 0) or 0
    )
    income = _monthly_income(float(data.get("annual_income", 0) or 0))
    if income <= 0:
        return 1.0
    existing = float(data.get("existing_debt", 0) or 0) * _DEBT_SERVICE_FACTOR
    return (existing + _monthly_payment(loan)) / income


def _lti(data: dict[str, Any], loan_amount_override: float | None = None) -> float:
    loan = float(
        loan_amount_override
        if loan_amount_override is not None
        else data.get("loan_amount", 0) or 0
    )
    income = float(data.get("annual_income", 0) or 0)
    return (loan / income) if income > 0 else 999.0


def _would_counter_approve(data: dict[str, Any], new_loan: float) -> bool:
    """Confirm the proposed counter actually clears the deterministic gates.

    Mirrors the hard-stop logic in :mod:`agents.critic_agent` — the
    counter only "qualifies" if DTI and LTI both clear the personal-loan
    ceilings on the right-sized loan.
    """

    return (
        _lti(data, new_loan) <= _LTI_CEILING
        and _dti(data, new_loan) <= _DTI_TRIGGER
        and int(data.get("credit_score", 0) or 0) >= _FICO_NEAR_PRIME_FLOOR
    )


def _right_size_loan(data: dict[str, Any]) -> float:
    """Compute the largest principal that clears both DTI and LTI.

    Uses the LTI target first (simpler ratio), then tightens to DTI if
    needed. The 5-year term, 2% existing-debt factor, and income figures
    all match the project's existing conventions so nothing changes
    underneath the critic.
    """

    income = float(data.get("annual_income", 0) or 0)
    if income <= 0:
        return 0.0

    lti_cap = _LTI_TARGET * income
    monthly_income = _monthly_income(income)
    existing_service = float(data.get("existing_debt", 0) or 0) * _DEBT_SERVICE_FACTOR
    dti_budget = max(_DTI_TARGET * monthly_income - existing_service, 0.0)
    # Invert the monthly-payment formula (x / 60) * 1.0417 → max principal.
    dti_cap = dti_budget * 60 / 1.0417 if dti_budget > 0 else 0.0

    return round(max(min(lti_cap, dti_cap), 0.0), -2) if dti_cap > 0 else 0.0


def propose_counter_offer(
    data: dict[str, Any], critic: dict[str, Any]
) -> dict[str, Any]:
    """Return a structured counter-offer record or an ``applicable=False`` stub."""

    decision = str(critic.get("decision", "")) if isinstance(critic, dict) else ""
    if decision == "APPROVED":
        return {
            "agent": "Negotiator",
            "applicable": False,
            "reason": "Application already approved — no counter-offer needed.",
        }

    credit_score = int(data.get("credit_score", 0) or 0)
    employment_years = float(data.get("employment_years", 0) or 0)
    loan = float(data.get("loan_amount", 0) or 0)
    income = float(data.get("annual_income", 0) or 0)

    offers: list[dict[str, Any]] = []
    primary: dict[str, Any] | None = None

    # 1. High LTI / DTI → right-size the principal.
    current_lti = _lti(data)
    current_dti = _dti(data)
    if current_lti > _LTI_CEILING or current_dti > _DTI_TRIGGER:
        right_sized = _right_size_loan(data)
        if right_sized > 0 and right_sized < loan:
            new_lti = _lti(data, right_sized)
            new_dti_pct = _dti(data, right_sized) * 100
            offer = {
                "type": "right_size_principal",
                "counter_loan_amount": right_sized,
                "original_loan_amount": loan,
                "new_lti_multiple": round(new_lti, 2),
                "new_dti_pct": round(new_dti_pct, 1),
                "message": (
                    f"Reduce principal to ${right_sized:,.0f} "
                    f"(LTI {new_lti:.2f}x, DTI {new_dti_pct:.1f}%) — "
                    "within standard personal-loan underwriting bands."
                ),
                "would_qualify": _would_counter_approve(data, right_sized),
            }
            offers.append(offer)
            if primary is None and offer["would_qualify"]:
                primary = offer

    # 2. FICO below prime but within near-prime range → alternative product.
    if (
        credit_score < _FICO_PRIME_FLOOR
        and credit_score >= _FICO_NEAR_PRIME_FLOOR
    ):
        offer = {
            "type": "alternative_lender_tier",
            "recommended_tier": "near-prime / subprime",
            "example_lenders": [
                "Upstart",
                "LendingClub",
                "Upgrade",
                "Avant",
                "OneMain Financial",
            ],
            "message": (
                f"FICO {credit_score} falls below the prime-lender floor "
                f"({_FICO_PRIME_FLOOR}). Route to a near-prime lender tier — "
                "same product, different underwriting box, higher APR."
            ),
            "would_qualify": True,
        }
        offers.append(offer)
        if primary is None:
            primary = offer

    # 3. FICO below near-prime → credit-builder + deferred re-application.
    if credit_score < _FICO_NEAR_PRIME_FLOOR:
        offer = {
            "type": "credit_builder_deferred",
            "recommended_product": "secured credit-builder loan",
            "defer_months": 6,
            "message": (
                f"FICO {credit_score} is below the near-prime floor "
                f"({_FICO_NEAR_PRIME_FLOOR}). Recommend a secured "
                "credit-builder product (e.g., Self Financial) and a "
                "deferred personal-loan re-application in 6 months."
            ),
            "would_qualify": False,
        }
        offers.append(offer)
        if primary is None:
            primary = offer

    # 4. Thin employment history → co-borrower / deferred resolution.
    if employment_years * 12 < _EMPLOYMENT_MIN_MONTHS:
        offer = {
            "type": "co_borrower_or_defer",
            "message": (
                "Employment tenure under 6 months is the standard "
                "thin-file trigger. Recommend either adding a qualifying "
                "co-borrower or deferring the decision until 6 months of "
                "employment history is established."
            ),
            "would_qualify": False,
        }
        offers.append(offer)
        if primary is None:
            primary = offer

    if not offers:
        return {
            "agent": "Negotiator",
            "applicable": True,
            "counter_offers": [],
            "primary_counter": None,
            "would_approve_under_counter": False,
            "message": (
                "Decline reasons do not map to a standard counter-offer. "
                "Recommend applicant consultation with a loan officer."
            ),
            "inputs_considered": {
                "loan_amount": loan,
                "annual_income": income,
                "credit_score": credit_score,
                "employment_years": employment_years,
            },
        }

    return {
        "agent": "Negotiator",
        "applicable": True,
        "counter_offers": offers,
        "primary_counter": primary,
        "would_approve_under_counter": bool(primary and primary.get("would_qualify")),
        "inputs_considered": {
            "loan_amount": loan,
            "annual_income": income,
            "credit_score": credit_score,
            "employment_years": employment_years,
            "current_lti_multiple": round(current_lti, 2),
            "current_dti_pct": round(current_dti * 100, 1),
        },
    }

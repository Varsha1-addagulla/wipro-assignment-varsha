"""
Consistency Checker — pure logic, no LLM.

Runs before all other agents as a pre-assessment gate.
Detects impossible or highly suspicious data combinations.
Returns a consistency_score (0-100) and a list of flags.
"""

# Each rule: (severity, deduction, check fn, flag message fn)
# severity: critical=50pts, high=30pts, medium=20pts, low=10pts
RULES = [
    (
        "critical", 50,
        lambda d: not (300 <= d["credit_score"] <= 850),
        lambda d: f"Credit score {d['credit_score']} is outside the valid FICO range (300–850) — data integrity issue.",
    ),
    (
        "critical", 50,
        lambda d: d["annual_income"] <= 0,
        lambda d: "Annual income is zero or negative — repayment capacity cannot be assessed.",
    ),
    (
        "critical", 40,
        lambda d: d["loan_amount"] <= 0,
        lambda d: f"Loan amount ${d['loan_amount']:,.0f} is zero or negative — invalid application.",
    ),
    (
        "critical", 35,
        lambda d: d["existing_debt"] < 0,
        lambda d: f"Existing debt ${d['existing_debt']:,.0f} is negative — data integrity issue.",
    ),
    (
        "critical", 35,
        lambda d: d["employment_years"] < 0,
        lambda d: f"Employment duration {d['employment_years']} years is negative — data integrity issue.",
    ),
    (
        "high", 30,
        lambda d: d["annual_income"] > 0 and d["loan_amount"] > 5 * d["annual_income"],
        lambda d: (
            f"Loan amount (${d['loan_amount']:,.0f}) exceeds 5× annual income "
            f"(${d['annual_income']:,.0f}) — repayment is highly unlikely."
        ),
    ),
    (
        "high", 30,
        lambda d: d["employment_years"] < 1 and d["loan_amount"] > 100_000,
        lambda d: (
            f"Loan of ${d['loan_amount']:,.0f} requested with less than 1 year of employment "
            f"({d['employment_years']} yrs) — income stability unproven for this loan size."
        ),
    ),
    (
        "medium", 20,
        lambda d: d["credit_score"] < 500 and d["annual_income"] > 200_000,
        lambda d: (
            f"Credit score of {d['credit_score']} paired with income of "
            f"${d['annual_income']:,.0f} is a statistically anomalous combination."
        ),
    ),
    (
        "medium", 20,
        lambda d: d["annual_income"] > 0 and d["existing_debt"] > 4 * d["annual_income"],
        lambda d: (
            f"Existing debt (${d['existing_debt']:,.0f}) exceeds 4× annual income "
            f"(${d['annual_income']:,.0f}) — extreme pre-existing debt burden."
        ),
    ),
    (
        "low", 10,
        lambda d: d["employment_years"] == 0 and d["loan_amount"] > 50_000,
        lambda d: (
            f"Zero employment history with a loan request of ${d['loan_amount']:,.0f} — "
            "insufficient income track record."
        ),
    ),
]

_SEVERITY_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}


def check_consistency(data: dict) -> dict:
    score = 100
    flags = []
    severities = []

    for severity, deduction, check_fn, flag_fn in RULES:
        try:
            if check_fn(data):
                flags.append(f"[{_SEVERITY_LABEL[severity]}] {flag_fn(data)}")
                severities.append(severity)
                score -= deduction
        except Exception:
            pass

    score = max(0, score)

    if score >= 80:
        status = "PASS"
        summary = (
            "No significant data inconsistencies detected. Application data appears internally consistent."
            if not flags
            else f"{len(flags)} minor flag(s) noted. Application data is largely consistent."
        )
    elif score >= 50:
        status = "WARNING"
        summary = (
            f"{len(flags)} consistency issue(s) detected. Human review recommended before proceeding."
        )
    else:
        status = "FAIL"
        summary = (
            f"{len(flags)} consistency issue(s) detected including critical violations. "
            "Data integrity cannot be confirmed."
        )

    return {
        "agent": "Consistency Checker",
        "consistency_score": score,
        "status": status,
        "flags": flags,
        "flag_count": len(flags),
        "is_consistent": status == "PASS",
        "summary": summary,
    }

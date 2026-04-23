from agents.base_agent import call_llm

SYSTEM = "Senior loan officer. Write concise formal assessment reports. Banking language."

AGENT_KEYS = ["credit_analyst", "income_verifier", "risk_assessor", "fraud_detector", "debt_analyzer"]


def _threshold_status(data: dict) -> str:
    monthly_income = data["annual_income"] / 12
    monthly_new = (data["loan_amount"] / 60) * 1.0417
    monthly_existing = data["existing_debt"] * 0.02
    dti = ((monthly_new + monthly_existing) / monthly_income * 100) if monthly_income > 0 else 100.0
    lti = data["loan_amount"] / data["annual_income"] if data["annual_income"] > 0 else 999.0

    def c(s): return "APPROVE" if s >= 720 else ("REVIEW" if s >= 620 else "REJECT")
    def d(v): return "APPROVE" if v < 36 else ("REVIEW" if v <= 43 else "REJECT")
    def e(y): return "APPROVE" if y >= 2 else ("REVIEW" if y >= 0.5 else "REJECT")
    def l(v): return "APPROVE" if v < 3 else ("REVIEW" if v <= 5 else "REJECT")

    return (
        f"Credit {data['credit_score']} ({c(data['credit_score'])}) | "
        f"DTI {dti:.1f}% ({d(dti)}) | "
        f"Employment {data['employment_years']}yrs ({e(data['employment_years'])}) | "
        f"LTI {lti:.2f}x ({l(lti)})"
    )


def write_report(data: dict, results: dict) -> dict:
    agent_lines = []
    for key in AGENT_KEYS:
        if key in results:
            r = results[key]
            agent_lines.append(
                f"{r.get('agent', key)}: {r.get('recommendation','N/A').upper()} "
                f"({r.get('confidence',0):.0f}%) — {r.get('analysis','')}"
            )

    critic = results.get("critic", {})
    consistency = results.get("consistency_checker", {})

    prompt = f"""Write a formal loan assessment report.

APPLICANT: {data['name']} | Loan: ${data['loan_amount']:,.0f} | Income: ${data['annual_income']:,.0f}
Credit: {data['credit_score']} | Employment: {data['employment_years']}yrs | Debt: ${data['existing_debt']:,.0f}

FANNIE MAE OUTCOMES: {_threshold_status(data)}

DATA VALIDATION: Score {consistency.get('consistency_score','N/A')}/100 — {consistency.get('summary','')}

AGENT RESULTS:
{chr(10).join(agent_lines)}

DECISION: {critic.get('decision','N/A')} | Avg confidence: {critic.get('average_confidence',0):.1f}%
Reason: {critic.get('reason','')}

Write five sections: EXECUTIVE SUMMARY, FINANCIAL PROFILE, AGENT FINDINGS, DECISION RATIONALE, CONDITIONS.
One paragraph each. Cite specific Fannie Mae threshold values throughout."""

    report_text = call_llm(SYSTEM, prompt, max_tokens=600)
    return {"agent": "Report Writer", "report": report_text}

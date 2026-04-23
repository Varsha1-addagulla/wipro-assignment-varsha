from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Debt sustainability specialist. Synthesize agent findings against Fannie Mae thresholds. JSON only."


def analyze_debt(data: dict, parallel_results: dict) -> dict:
    monthly_income = data["annual_income"] / 12
    monthly_existing = data["existing_debt"] * 0.02
    monthly_new = (data["loan_amount"] / 60) * 1.0417
    total_monthly_debt = monthly_existing + monthly_new
    disposable = monthly_income - total_monthly_debt
    dscr = monthly_income / total_monthly_debt if total_monthly_debt > 0 else 99.0
    dti = (total_monthly_debt / monthly_income * 100) if monthly_income > 0 else 100.0
    lti = data["loan_amount"] / data["annual_income"] if data["annual_income"] > 0 else 999.0

    def credit_band(s):
        return "APPROVE" if s >= 720 else ("REVIEW" if s >= 620 else "REJECT")
    def dti_band(d):
        return "APPROVE" if d < 36 else ("REVIEW" if d <= 43 else "REJECT")
    def emp_band(y):
        return "APPROVE" if y >= 2 else ("REVIEW" if y >= 0.5 else "REJECT")
    def lti_band(l):
        return "APPROVE" if l < 3 else ("REVIEW" if l <= 5 else "REJECT")

    agent_summary = "\n".join(
        f"  {r.get('agent','?')}: {r.get('recommendation','N/A').upper()} ({r.get('confidence',0):.0f}%)"
        for r in [parallel_results.get(k, {}) for k in ["credit_analyst","income_verifier","risk_assessor","fraud_detector"]]
        if r
    ) or "  None"

    prompt = f"""Applicant: {data['name']} | Income: ${monthly_income:,.0f}/mo | Debt service: ${total_monthly_debt:,.0f}/mo
Disposable: ${disposable:,.0f}/mo | DSCR: {dscr:.2f}x (>1.25 healthy) | DTI: {dti:.1f}%

Fannie Mae status: Credit {credit_band(data['credit_score'])} | DTI {dti_band(dti)} | Emp {emp_band(data['employment_years'])} | LTI {lti_band(lti)}

Prior agents:
{agent_summary}

Identify binding constraint. Confirm or challenge prior findings using DSCR and disposable income.

{{"analysis":"2-3 sentences on binding constraint and whether DSCR supports recommendation","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"]}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Debt Analyzer"
    result["confidence"] = float(result.get("confidence", 0))
    return result

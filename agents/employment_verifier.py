from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Employment verification specialist. Apply Fannie Mae employment thresholds. JSON only."

PRIORITY = "Priority 3"
PRIORITY_LEVEL = 3


def _classify_employment(years):
    if years >= 2.0:  return "approve", f"{years}yrs — APPROVE (2+ years)"
    if years >= 0.5:  return "review",  f"{years}yrs — REVIEW (6 months–2 years)"
    return "reject", f"{years}yrs — REJECT (<6 months)"


def verify_employment(data: dict) -> dict:
    emp_rec, emp_label = _classify_employment(data["employment_years"])

    prompt = f"""Applicant: {data['name']} | Employment: {emp_label}
Income: ${data['annual_income']:,.0f}/yr | Loan: ${data['loan_amount']:,.0f} | Credit: {data['credit_score']}

Thresholds: 2+ yrs approve | 6mo–2yr review | <6mo reject
Flag: <6mo employment with loan >$50k is high-risk combination.
State exact employment band triggered.

{{"analysis":"2-3 sentences citing exact duration and Fannie Mae band","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"],"threshold_triggered":"one sentence"}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Employment Verifier"
    result["priority"] = PRIORITY
    result["priority_level"] = PRIORITY_LEVEL
    result["confidence"] = float(result.get("confidence", 0))
    return result

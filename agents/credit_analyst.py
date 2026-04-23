from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Senior credit analyst. Evaluate loans against Fannie Mae thresholds. JSON only."

PRIORITY = "Priority 1"
PRIORITY_LEVEL = 1


def _classify_credit(score):
    if score >= 720: return "approve", f"{score} — APPROVE (720+)"
    if score >= 620: return "review",  f"{score} — REVIEW (620–719)"
    return "reject", f"{score} — REJECT (<620)"


def _classify_lti(lti):
    if lti < 3.0:  return "approve", f"{lti:.2f}x — APPROVE (<3x)"
    if lti <= 5.0: return "review",  f"{lti:.2f}x — REVIEW (3–5x)"
    return "reject", f"{lti:.2f}x — REJECT (>5x)"


def analyze_credit(data: dict) -> dict:
    lti = data["loan_amount"] / data["annual_income"] if data["annual_income"] > 0 else 999
    credit_rec, credit_label = _classify_credit(data["credit_score"])
    lti_rec, lti_label = _classify_lti(lti)

    prompt = f"""Applicant: {data['name']} | Loan: ${data['loan_amount']:,.0f} | Income: ${data['annual_income']:,.0f}
Credit: {data['credit_score']} | Employment: {data['employment_years']}yrs | Debt: ${data['existing_debt']:,.0f}

Pre-classified — Credit: {credit_label} | LTI: {lti_label}

Thresholds: Credit 720+ approve / 620-719 review / <620 reject
            LTI <3x approve / 3-5x review / >5x reject
Most restrictive outcome wins. State which threshold was triggered.

{{"analysis":"2-3 sentences citing exact threshold triggered","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"],"threshold_triggered":"one sentence"}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Credit Analyst"
    result["priority"] = PRIORITY
    result["priority_level"] = PRIORITY_LEVEL
    result["confidence"] = float(result.get("confidence", 0))
    return result

from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Risk assessment specialist. Score all four Fannie Mae underwriting dimensions. JSON only."


def _credit_band(s):
    if s >= 720: return f"{s} — APPROVE (720+)"
    if s >= 620: return f"{s} — REVIEW (620–719)"
    return f"{s} — REJECT (<620)"

def _dti_band(d):
    if d < 36:   return f"{d:.1f}% — APPROVE (<36%)"
    if d <= 43:  return f"{d:.1f}% — REVIEW (36–43%)"
    if d <= 50:  return f"{d:.1f}% — REJECT (>43%)"
    return f"{d:.1f}% — HARD REJECT (>50%)"

def _emp_band(y):
    if y >= 2.0: return f"{y}yrs — APPROVE (2+)"
    if y >= 0.5: return f"{y}yrs — REVIEW (6mo–2yr)"
    return f"{y}yrs — REJECT (<6mo)"

def _lti_band(l):
    if l < 3.0:  return f"{l:.2f}x — APPROVE (<3x)"
    if l <= 5.0: return f"{l:.2f}x — REVIEW (3–5x)"
    return f"{l:.2f}x — REJECT (>5x)"


def assess_risk(data: dict) -> dict:
    monthly_income = data["annual_income"] / 12
    monthly_new = (data["loan_amount"] / 60) * 1.0417
    monthly_existing = data["existing_debt"] * 0.02
    dti = ((monthly_new + monthly_existing) / monthly_income * 100) if monthly_income > 0 else 100.0
    lti = data["loan_amount"] / data["annual_income"] if data["annual_income"] > 0 else 999

    prompt = f"""Applicant: {data['name']} | Loan: ${data['loan_amount']:,.0f} | Income: ${data['annual_income']:,.0f}

Fannie Mae dimension scores:
  Credit:     {_credit_band(data['credit_score'])}
  DTI:        {_dti_band(dti)}
  Employment: {_emp_band(data['employment_years'])}
  LTI:        {_lti_band(lti)}

Rule: most restrictive dimension drives recommendation.
Identify the single binding constraint.

{{"analysis":"2-3 sentences naming each threshold and the binding constraint","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"]}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Risk Assessor"
    result["confidence"] = float(result.get("confidence", 0))
    return result

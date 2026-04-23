from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Income verification specialist. Assess DTI against Fannie Mae guidelines. JSON only."


def _classify_dti(dti):
    if dti < 36.0:  return "approve", f"{dti:.1f}% — APPROVE (<36%)"
    if dti <= 43.0: return "review",  f"{dti:.1f}% — REVIEW (36–43%)"
    if dti <= 50.0: return "reject",  f"{dti:.1f}% — REJECT (>43%)"
    return "reject", f"{dti:.1f}% — HARD REJECT (>50%)"


def verify_income(data: dict) -> dict:
    monthly_income = data["annual_income"] / 12
    monthly_new = (data["loan_amount"] / 60) * 1.0417
    monthly_existing = data["existing_debt"] * 0.02
    total_monthly_debt = monthly_new + monthly_existing
    dti = (total_monthly_debt / monthly_income * 100) if monthly_income > 0 else 100.0
    dti_rec, dti_label = _classify_dti(dti)

    prompt = f"""Applicant: {data['name']} | Income: ${data['annual_income']:,.0f}/yr (${monthly_income:,.0f}/mo)
Loan: ${data['loan_amount']:,.0f} | Est. new payment: ${monthly_new:,.0f}/mo | Existing debt service: ${monthly_existing:,.0f}/mo
DTI = ${total_monthly_debt:,.0f} / ${monthly_income:,.0f} = {dti_label}

Thresholds: <36% approve | 36-43% review | >43% reject | >50% hard reject
State exact DTI band triggered.

{{"analysis":"2-3 sentences citing exact DTI and Fannie Mae band","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"]}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Income Verifier"
    result["confidence"] = float(result.get("confidence", 0))
    return result

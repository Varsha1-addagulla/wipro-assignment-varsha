from agents.base_agent import call_llm, parse_json_response

SYSTEM = "Fraud detection specialist. Identify data inconsistencies and anomalies. JSON only."

PRIORITY = "Hard Stop"
PRIORITY_LEVEL = 0


def detect_fraud(data: dict) -> dict:
    flags = []
    if not (300 <= data["credit_score"] <= 850):
        flags.append(f"Credit score {data['credit_score']} outside FICO range (300–850)")
    if data["annual_income"] > 0 and data["loan_amount"] / data["annual_income"] > 10:
        flags.append(f"Loan is {data['loan_amount']/data['annual_income']:.1f}x income (>10x anomalous)")
    if data["employment_years"] < 0:
        flags.append("Negative employment years")
    if data["existing_debt"] < 0:
        flags.append("Negative existing debt")
    if data["annual_income"] < 0:
        flags.append("Negative annual income")

    flags_str = "\n".join(f"  - {f}" for f in flags) if flags else "  - None"

    prompt = f"""Applicant: {data['name']} | Loan: ${data['loan_amount']:,.0f} | Income: ${data['annual_income']:,.0f}
Credit: {data['credit_score']} | Employment: {data['employment_years']}yrs | Debt: ${data['existing_debt']:,.0f}

Automated flags:
{flags_str}

Assess fraud risk from internal consistency only (no external APIs in prototype).
High confidence = no fraud. Low confidence = fraud detected.

{{"analysis":"2-3 sentences on most significant fraud finding","confidence":<0-100>,"recommendation":"<approve|review|reject>","key_factors":["f1","f2","f3"],"threshold_triggered":"one sentence"}}"""

    text = call_llm(SYSTEM, prompt)
    result = parse_json_response(text)
    result["agent"] = "Fraud Detector"
    result["priority"] = PRIORITY
    result["priority_level"] = PRIORITY_LEVEL
    result["confidence"] = float(result.get("confidence", 0))
    return result

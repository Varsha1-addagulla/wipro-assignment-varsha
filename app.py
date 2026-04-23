from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

load_dotenv()

app = Flask(__name__)

from agents.consistency_checker import check_consistency
from agents.credit_analyst import analyze_credit
from agents.income_verifier import verify_income
from agents.risk_assessor import assess_risk
from agents.fraud_detector import detect_fraud
from agents.debt_analyzer import analyze_debt
from agents.critic_agent import make_decision
from agents.report_writer import write_report


def _safe_run(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:
        return {
            "agent": fn.__module__.split(".")[-1].replace("_", " ").title(),
            "analysis": f"Agent error: {exc}",
            "confidence": 0.0,
            "recommendation": "reject",
            "key_factors": ["Agent encountered an error"],
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/assess", methods=["POST"])
def assess():
    try:
        data = {
            "name": request.form.get("name", "").strip(),
            "loan_amount": float(request.form.get("loan_amount", 0)),
            "annual_income": float(request.form.get("annual_income", 0)),
            "credit_score": int(request.form.get("credit_score", 0)),
            "employment_years": float(request.form.get("employment_years", 0)),
            "existing_debt": float(request.form.get("existing_debt", 0)),
        }
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid form data: {exc}"}), 400

    results = {}

    # Agent 0: Consistency Checker (runs first — gates the rest)
    results["consistency_checker"] = check_consistency(data)

    # Agents 1–4 run in parallel
    parallel_agents = {
        "credit_analyst": analyze_credit,
        "income_verifier": verify_income,
        "risk_assessor": assess_risk,
        "fraud_detector": detect_fraud,
    }

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_key = {
            executor.submit(_safe_run, fn, data): key
            for key, fn in parallel_agents.items()
        }
        for future in as_completed(future_to_key):
            key = future_to_key[future]
            results[key] = future.result()

    # Agent 5: Debt Analyzer (needs parallel results)
    results["debt_analyzer"] = _safe_run(analyze_debt, data, results)

    # Agent 6: Critic Decision (pure logic — no LLM)
    results["critic"] = make_decision(results)

    # Agent 7: Report Writer
    results["report"] = _safe_run(write_report, data, results)

    return jsonify(results)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

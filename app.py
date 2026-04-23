"""Flask application for the multi-agent loan risk assessment service.

Exposes three endpoints:

* ``GET /``          — static UI (existing Jinja template).
* ``POST /assess``   — runs the LangGraph orchestrator on a validated payload.
* ``GET /healthz``   — liveness probe used by Cloud Run + Docker HEALTHCHECK.

Every request is traced with a request id, rate-limited per IP, validated
with Pydantic v2, and audited in the ``api_log`` table.
"""

from __future__ import annotations

import os
import time
import traceback
import uuid
from http import HTTPStatus
from typing import Any

import structlog
from dotenv import load_dotenv
from flask import Flask, Response, g, jsonify, render_template, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import ValidationError

from agents.graph import run_assessment
from config import Settings, get_settings
from db import init_engine, session_scope
from logging_config import configure_logging, get_logger
from models import ApiLog
from schemas import AssessmentRequest

load_dotenv()


def _coerce_form_payload(form: dict[str, str]) -> dict[str, Any]:
    """Coerce flat multipart form values into the assessment payload shape.

    Pydantic handles the final validation; this function only converts
    strings to the expected Python types and rejects unknown fields.
    """

    allowed = {
        "name",
        "loan_amount",
        "annual_income",
        "credit_score",
        "employment_years",
        "existing_debt",
    }
    unknown = set(form.keys()) - allowed
    if unknown:
        raise ValueError(f"Unknown form fields: {', '.join(sorted(unknown))}")

    return {
        "name": form.get("name", ""),
        "loan_amount": form.get("loan_amount", 0),
        "annual_income": form.get("annual_income", 0),
        "credit_score": form.get("credit_score", 0),
        "employment_years": form.get("employment_years", 0),
        "existing_debt": form.get("existing_debt", 0),
    }


def _write_api_log(
    *,
    request_id: str,
    endpoint: str,
    method: str,
    status_code: int,
    latency_ms: int,
    applicant_name: str | None,
    decision: str | None,
    average_confidence: float | None,
    error_message: str | None,
    request_summary: dict[str, Any] | None,
) -> None:
    """Persist an audit row. Database failures never break a response."""

    try:
        with session_scope() as session:
            session.add(
                ApiLog(
                    request_id=request_id,
                    endpoint=endpoint,
                    http_method=method,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    applicant_name=applicant_name,
                    decision=decision,
                    average_confidence=(
                        int(round(average_confidence))
                        if average_confidence is not None
                        else None
                    ),
                    error_message=error_message,
                    request_summary=request_summary,
                )
            )
    except Exception as exc:
        # Audit log is best-effort: a DB outage must never break a response.
        get_logger(__name__).error(
            "api_log_write_failed",
            request_id=request_id,
            error=str(exc),
        )


def create_app(settings: Settings | None = None) -> Flask:
    """Application factory."""

    app_settings = settings or get_settings()
    configure_logging(level=app_settings.log_level)
    init_engine()

    app = Flask(__name__)
    app.url_map.strict_slashes = False

    CORS(
        app,
        resources={r"/*": {"origins": app_settings.allowed_origins_list}},
        supports_credentials=False,
    )

    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=[app_settings.rate_limit_default],
        storage_uri=app_settings.rate_limit_storage_uri,
        headers_enabled=True,
    )

    log = get_logger(__name__)

    @app.before_request
    def _start_request() -> None:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_id = request_id
        g.started_at = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.path,
            method=request.method,
        )

    @app.after_request
    def _finish_request(response: Response) -> Response:
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    @app.errorhandler(Exception)
    def _handle_uncaught(exc: Exception) -> tuple[Response, int]:
        log.exception("unhandled_exception", error=str(exc))
        # Diagnostic surface: bubble the actual Python exception out in the JSON
        # body so browser-side errors show the real cause instead of Cloud Run's
        # default "Service Unavailable" plaintext. Safe here because the service
        # exposes no user data in tracebacks and has no auth surface to leak.
        return (
            jsonify(
                {
                    "error": "Internal server error",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "traceback": traceback.format_exc().splitlines()[-20:],
                }
            ),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    @app.route("/healthz")
    def healthz() -> tuple[Response, int]:
        return jsonify({"status": "ok"}), HTTPStatus.OK

    @app.route("/assess", methods=["POST"])
    @limiter.limit(app_settings.rate_limit_assess)
    def assess() -> tuple[Response, int]:
        request_id = getattr(g, "request_id", "")
        started = getattr(g, "started_at", time.perf_counter())

        try:
            raw = _coerce_form_payload(dict(request.form))
            validated = AssessmentRequest.model_validate(raw)
        except (ValidationError, ValueError) as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            message = exc.errors() if isinstance(exc, ValidationError) else str(exc)
            log.info(
                "assess_validation_failed", latency_ms=latency_ms, error=message
            )
            _write_api_log(
                request_id=request_id,
                endpoint="/assess",
                method=request.method,
                status_code=HTTPStatus.BAD_REQUEST,
                latency_ms=latency_ms,
                applicant_name=None,
                decision=None,
                average_confidence=None,
                error_message=str(message),
                request_summary=None,
            )
            return (
                jsonify({"error": "Invalid request", "details": message}),
                HTTPStatus.BAD_REQUEST,
            )

        payload = validated.to_agent_payload()

        try:
            results = run_assessment(payload)
        except Exception as exc:
            # Diagnostic surface: include exception class + message + a tail of
            # the traceback in the response so browser-side errors show the
            # real cause instead of a generic "Service Unavailable". Structured
            # server-side logging keeps the full context for Cloud Logging.
            latency_ms = int((time.perf_counter() - started) * 1000)
            tb_tail = traceback.format_exc().splitlines()[-20:]
            log.error(
                "assess_orchestration_failed",
                error=str(exc),
                exception_type=type(exc).__name__,
                traceback_tail=tb_tail,
            )
            _write_api_log(
                request_id=request_id,
                endpoint="/assess",
                method=request.method,
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                latency_ms=latency_ms,
                applicant_name=validated.name,
                decision=None,
                average_confidence=None,
                error_message=str(exc),
                request_summary={"loan_amount": float(validated.loan_amount)},
            )
            return (
                jsonify(
                    {
                        "error": "Assessment failed",
                        "exception_type": type(exc).__name__,
                        "exception_message": str(exc),
                        "traceback": tb_tail,
                    }
                ),
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        critic = results.get("critic", {}) if isinstance(results, dict) else {}
        decision = str(critic.get("decision")) if critic else None
        avg_conf = (
            float(critic.get("average_confidence", 0.0)) if critic else None
        )

        results["meta"] = {
            "request_id": request_id,
            "total_latency_ms": latency_ms,
            "service": "loan-risk-multiagent",
        }

        log.info(
            "assess_completed",
            decision=decision,
            average_confidence=avg_conf,
            latency_ms=latency_ms,
        )
        _write_api_log(
            request_id=request_id,
            endpoint="/assess",
            method=request.method,
            status_code=HTTPStatus.OK,
            latency_ms=latency_ms,
            applicant_name=validated.name,
            decision=decision,
            average_confidence=avg_conf,
            error_message=None,
            request_summary={
                "loan_amount": float(validated.loan_amount),
                "credit_score": int(validated.credit_score),
                "employment_years": float(validated.employment_years),
            },
        )

        return jsonify(results), HTTPStatus.OK

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)

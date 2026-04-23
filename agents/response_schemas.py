"""Output schemas for LLM agent responses.

Every LLM-backed agent (credit_analyst, income_verifier, risk_assessor,
fraud_detector, employment_verifier, debt_analyzer) must return an object
that matches :class:`AnalystResponse`. The report writer returns a free
text narrative so it uses :class:`ReportResponse`.

The :func:`coerce_analyst_response` helper defends the downstream critic
against malformed LLM output — it normalises ``recommendation`` casing,
clamps ``confidence`` into ``[0, 100]``, and supplies safe defaults for
missing fields instead of raising. This is a guardrail, not a silent
fallback: the :class:`AnalystResponse` model itself is strict and is used
by tests to pin the contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Recommendation = Literal["approve", "review", "reject"]

_VALID_RECS: frozenset[str] = frozenset({"approve", "review", "reject"})


class AnalystResponse(BaseModel):
    """Strict schema for a single LLM-backed analyst agent."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    agent: str = Field(min_length=1, max_length=64)
    analysis: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=100.0)
    recommendation: Recommendation
    key_factors: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("recommendation", mode="before")
    @classmethod
    def _normalise_recommendation(cls, value: Any) -> str:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in _VALID_RECS:
                return cleaned
        return "reject"

    @field_validator("key_factors", mode="before")
    @classmethod
    def _clean_factors(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(f)[:120] for f in value if f is not None][:10]


class ReportResponse(BaseModel):
    """Schema for the narrative report writer."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    agent: str = Field(min_length=1, max_length=64)
    report: str = Field(min_length=1, max_length=10_000)


def coerce_analyst_response(
    raw: dict[str, Any], *, agent_label: str
) -> dict[str, Any]:
    """Return a schema-clean analyst record.

    Best-effort coercion: clamps invalid numbers, replaces missing fields
    with safe defaults tagged with ``agent_label``. The resulting dict
    always satisfies :class:`AnalystResponse`, so downstream consumers
    (critic, report writer) can rely on the contract.
    """

    payload: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}

    payload.setdefault("agent", agent_label)
    payload.setdefault("analysis", "No analysis produced.")
    payload.setdefault("recommendation", "reject")
    payload.setdefault("key_factors", [])

    try:
        confidence = float(payload.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    payload["confidence"] = max(0.0, min(100.0, confidence))

    validated = AnalystResponse.model_validate(payload)
    return validated.model_dump()

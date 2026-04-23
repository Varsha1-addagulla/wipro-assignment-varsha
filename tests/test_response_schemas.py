"""Validation tests for :mod:`agents.response_schemas`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.response_schemas import AnalystResponse, coerce_analyst_response


def test_strict_schema_accepts_canonical_response() -> None:
    payload = {
        "agent": "Credit Analyst",
        "analysis": "Strong FICO — clear approve.",
        "confidence": 92.5,
        "recommendation": "approve",
        "key_factors": ["credit", "income"],
    }

    parsed = AnalystResponse.model_validate(payload)

    assert parsed.recommendation == "approve"
    assert parsed.confidence == 92.5


def test_strict_schema_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValidationError):
        AnalystResponse.model_validate(
            {
                "agent": "Credit Analyst",
                "analysis": "ok",
                "confidence": 150,
                "recommendation": "approve",
            }
        )


def test_coerce_clamps_and_normalises() -> None:
    raw = {
        "agent": "Credit Analyst",
        "analysis": "ok",
        "confidence": 200,
        "recommendation": "APPROVE",
        "key_factors": None,
    }

    cleaned = coerce_analyst_response(raw, agent_label="Credit Analyst")

    assert cleaned["confidence"] == 100.0
    assert cleaned["recommendation"] == "approve"
    assert cleaned["key_factors"] == []


def test_coerce_fills_missing_fields_with_safe_defaults() -> None:
    cleaned = coerce_analyst_response({}, agent_label="Risk Assessor")

    assert cleaned["agent"] == "Risk Assessor"
    assert cleaned["recommendation"] == "reject"
    assert cleaned["confidence"] == 0.0
    assert cleaned["analysis"]


def test_coerce_maps_unknown_recommendation_to_reject() -> None:
    cleaned = coerce_analyst_response(
        {"agent": "x", "analysis": "x", "confidence": 50, "recommendation": "maybe"},
        agent_label="x",
    )

    assert cleaned["recommendation"] == "reject"

"""Validation tests for :mod:`schemas`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import AssessmentRequest


def _base_payload() -> dict[str, object]:
    return {
        "name": "Jane Doe",
        "loan_amount": 250_000,
        "annual_income": 100_000,
        "credit_score": 720,
        "employment_years": 5,
        "existing_debt": 10_000,
    }


def test_accepts_valid_payload() -> None:
    req = AssessmentRequest.model_validate(_base_payload())

    assert req.name == "Jane Doe"
    assert req.credit_score == 720


def test_rejects_out_of_range_credit_score() -> None:
    payload = _base_payload()
    payload["credit_score"] = 900

    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate(payload)


def test_rejects_negative_loan_amount() -> None:
    payload = _base_payload()
    payload["loan_amount"] = -1

    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate(payload)


def test_rejects_unknown_fields() -> None:
    payload = _base_payload()
    payload["ssn"] = "123-45-6789"

    with pytest.raises(ValidationError):
        AssessmentRequest.model_validate(payload)


def test_sanitises_name() -> None:
    payload = _base_payload()
    payload["name"] = "<script>alert(1)</script> Jane"

    req = AssessmentRequest.model_validate(payload)

    assert "<" not in req.name
    assert "Jane" in req.name

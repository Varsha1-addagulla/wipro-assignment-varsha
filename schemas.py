"""Pydantic v2 schemas for the ``/assess`` endpoint.

Input validation is strict:

* unknown fields are rejected (``extra="forbid"``),
* numeric values are bounded to sane underwriting ranges,
* the ``name`` field is sanitised to reduce prompt-injection risk before it
  ever reaches an LLM prompt.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from security import sanitize_applicant_name


class AssessmentRequest(BaseModel):
    """Validated representation of a loan assessment form submission."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    loan_amount: float = Field(gt=0, le=10_000_000)
    annual_income: float = Field(gt=0, le=50_000_000)
    credit_score: int = Field(ge=300, le=850)
    employment_years: float = Field(ge=0, le=60)
    existing_debt: float = Field(ge=0, le=10_000_000)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = sanitize_applicant_name(value)
        if not cleaned:
            raise ValueError("name must contain printable characters")
        return cleaned

    def to_agent_payload(self) -> dict[str, object]:
        """Return the dict shape consumed by the agent graph.

        The keys here match what every agent module expects. Keeping the
        conversion in one place prevents schema drift.
        """

        return {
            "name": self.name,
            "loan_amount": float(self.loan_amount),
            "annual_income": float(self.annual_income),
            "credit_score": int(self.credit_score),
            "employment_years": float(self.employment_years),
            "existing_debt": float(self.existing_debt),
        }

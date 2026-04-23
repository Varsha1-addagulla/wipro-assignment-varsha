"""Security helpers — input sanitisation and prompt-safe wrapping.

These helpers run *before* user data reaches an LLM prompt so injection
attempts via the applicant ``name`` field cannot rewrite the agent's role
or instructions.
"""

from __future__ import annotations

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_DANGEROUS_CHARS = re.compile(r"[`<>{}\\]")
_COLLAPSE_WS = re.compile(r"\s+")


def sanitize_applicant_name(value: str) -> str:
    """Return a prompt-safe, display-safe applicant name.

    The sanitiser strips control characters, a small set of prompt-delimiter
    characters, and collapses internal whitespace. The result is bounded to
    120 characters so it can never dominate an LLM prompt.
    """

    if not isinstance(value, str):
        return ""
    cleaned = _CONTROL_CHARS.sub("", value)
    cleaned = _DANGEROUS_CHARS.sub("", cleaned)
    cleaned = _COLLAPSE_WS.sub(" ", cleaned).strip()
    return cleaned[:120]


def safe_prompt_value(value: object) -> str:
    """Stringify *value* for embedding in an LLM prompt.

    Numeric inputs are passed through unchanged (already formatted by the
    caller). Strings are sanitised the same way as the applicant name so
    future free-text fields automatically inherit the protection.
    """

    if isinstance(value, str):
        return sanitize_applicant_name(value)
    return str(value)

"""Shared Groq client + JSON parser used by every LLM agent.

The original helpers (``call_llm`` / ``parse_json_response``) keep their
signatures so none of the individual agent modules need to change. The
implementation has been hardened in three ways:

* Deterministic calls — ``temperature=0``.
* JSON mode + short, bounded retries via :mod:`tenacity` (exponential
  backoff) so transient Groq errors do not reject an entire assessment.
* Structured logging of every attempt with duration and token counts.

No secrets are logged. The Groq API key is loaded from the environment; on
Cloud Run it comes from Secret Manager.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Final

from groq import APIConnectionError, APIStatusError, Groq, RateLimitError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from logging_config import get_logger

_LOG = get_logger(__name__)

_DEFAULT_MODEL: Final[str] = os.environ.get(
    "GROQ_MODEL", "llama-3.3-70b-versatile"
)
_DEFAULT_TIMEOUT: Final[float] = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "30"))
_MAX_RETRY_ATTEMPTS: Final[int] = int(os.environ.get("GROQ_MAX_RETRIES", "2")) + 1


_RETRIABLE = (APIConnectionError, RateLimitError, APIStatusError)


def _build_client() -> Groq:
    return Groq(
        api_key=os.environ.get("GROQ_API_KEY"),
        timeout=_DEFAULT_TIMEOUT,
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(_MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
    retry=retry_if_exception_type(_RETRIABLE),
)
def _invoke_groq(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    json_mode: bool,
) -> str:
    client = _build_client()
    params: dict[str, Any] = {
        "model": _DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if json_mode:
        params["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**params)
    content = response.choices[0].message.content
    return content if content is not None else ""


def call_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 300,
    *,
    json_mode: bool = True,
) -> str:
    """Call the Groq chat completion API and return the raw text content.

    ``json_mode`` defaults to True because every agent prompt asks for JSON
    output; setting it ensures the model returns valid JSON. Callers that
    need freeform text (e.g. the report writer) should pass ``json_mode=False``.
    """

    started = time.perf_counter()
    try:
        text = _invoke_groq(system_prompt, user_prompt, max_tokens, json_mode)
        _LOG.debug(
            "groq_call_success",
            model=_DEFAULT_MODEL,
            json_mode=json_mode,
            latency_ms=int((time.perf_counter() - started) * 1000),
            response_chars=len(text),
        )
        return text
    except RetryError as exc:  # pragma: no cover - retry exhausted
        _LOG.error(
            "groq_call_retries_exhausted",
            model=_DEFAULT_MODEL,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc.last_attempt.exception() if exc.last_attempt else exc),
        )
        raise


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON returned by an LLM, tolerant of code fences / extra prose."""

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        try:
            result = json.loads(fenced.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    braces = re.search(r"\{[\s\S]*\}", text)
    if braces:
        try:
            result = json.loads(braces.group(0))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from response: {text[:300]}")

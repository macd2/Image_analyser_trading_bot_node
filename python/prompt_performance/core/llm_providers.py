"""
Unified LLM provider abstraction with JSON validation and self-repair.

- Uses intelligent_prompts to build messages for seed/improve/repair
- Validates/normalizes JSON with canonical_json
- Sends requests to providers via HTTP (requests), best-effort, graceful errors

Note: Actual network calls may require API keys; callers can mock send for tests.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple
import json
import os
import time
import requests

from .canonical_json import validate_and_normalize
from .intelligent_prompts import build_messages_for_provider

Provider = Literal["anthropic", "openai"]

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MSG_URL = "https://api.anthropic.com/v1/messages"


class LLMError(Exception):
    pass


def _send_openai(model: str, messages: List[Dict[str, Any]], timeout: float = 30.0, *, response_format_json: bool = True) -> str:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY_1")
    if not key:
        raise LLMError("OPENAI_API_KEY not set")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if response_format_json:
        payload["response_format"] = {"type": "json_object"}
    r = requests.post(OPENAI_CHAT_URL, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }, data=json.dumps(payload), timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"OpenAI error {r.status_code}: {r.text[:200]}")
    body = r.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except Exception as e:
        raise LLMError(f"OpenAI response parse error: {e}")
    return content


def _send_anthropic(model: str, system: str, messages: List[Dict[str, Any]], timeout: float = 30.0) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError("ANTHROPIC_API_KEY not set")
    payload = {
        "model": model,
        "system": system,
        "max_tokens": 1500,
        "temperature": 0.2,
        "messages": messages,
    }
    r = requests.post(ANTHROPIC_MSG_URL, headers={
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }, data=json.dumps(payload), timeout=timeout)
    if r.status_code != 200:
        raise LLMError(f"Anthropic error {r.status_code}: {r.text[:200]}")
    body = r.json()
    try:
        # content is a list of blocks, take first text block
        blocks = body.get("content", [])
        pieces = []
        for b in blocks:
            if b.get("type") == "text":
                pieces.append(b.get("text", ""))
        content = "\n".join(pieces).strip()
    except Exception as e:
        raise LLMError(f"Anthropic response parse error: {e}")
    return content


def call_model(
    provider: Provider,
    model: str,
    kind: Literal["seed", "improve"],
    payload: Dict[str, Any],
    *,
    timeout: float = 30.0,
    max_repair_attempts: int = 1,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> Tuple[Optional[Dict[str, Any]], List[str], str]:
    """
    Call provider for seed/improve and return (normalized_json, errors, raw_text).
    If validation fails, attempts self-repair up to max_repair_attempts times.
    Network errors are retried with exponential backoff.
    """
    import time

    built = build_messages_for_provider(provider, kind, payload)
    raw_text = ""

    # Retry logic for network errors
    last_error = None
    for attempt in range(max_retries):
        try:
            if provider == "openai":
                # For improve, we want plain text (no forced JSON). For seed/repair, request JSON.
                raw_text = _send_openai(model, built["messages"], timeout, response_format_json=(kind != "improve"))
            else:
                raw_text = _send_anthropic(model, built["system"], built["messages"], timeout)
            break  # Success, exit retry loop
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                time.sleep(wait_time)
            else:
                return None, [f"network: {e}"], raw_text

    # Primary validation
    try:
        data = json.loads(raw_text)
    except Exception:
        data = {}
    normalized, errors = validate_and_normalize(data if isinstance(data, dict) else {})
    if not errors:
        return normalized, [], raw_text

    # Self-repair attempts
    for _ in range(max_repair_attempts):
        repair_payload = {"errors": errors}
        built = build_messages_for_provider(provider, "repair", repair_payload)

        # Retry logic for repair attempts
        for attempt in range(max_retries):
            try:
                if provider == "openai":
                    raw_text = _send_openai(model, built["messages"], timeout)
                else:
                    raw_text = _send_anthropic(model, built["system"], built["messages"], timeout)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                else:
                    return None, [f"network: {e}"], raw_text

        try:
            data = json.loads(raw_text)
        except Exception:
            data = {}
        normalized, errors = validate_and_normalize(data if isinstance(data, dict) else {})
        if not errors:
            return normalized, [], raw_text

    return normalized, errors, raw_text


__all__ = ["call_model", "LLMError"]


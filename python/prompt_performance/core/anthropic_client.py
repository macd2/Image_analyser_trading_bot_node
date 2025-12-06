import json
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

try:
    # Prefer centralized secrets manager if available in project
    from trading_bot.core.secrets_manager import SecretsManager  # type: ignore
except Exception:
    SecretsManager = None  # type: ignore

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


@dataclass
class AnthropicResponse:
    improved_prompt: str
    findings: str
    improvements: str
    observations: str
    issues: str
    raw_json: Dict[str, Any]


class AnthropicClient:
    """Lightweight client for Anthropic Messages API with robust error handling.

    - Reads API key from env ANTHROPIC_API_KEY (via SecretsManager if available)
    - Retries 429 and transient network errors with exponential backoff + jitter
    - Validates and normalizes model JSON response into a fixed schema
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        timeout: float = 25.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        if api_key:
            self.api_key = api_key
        else:
            self.api_key = self._load_api_key()

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required but not set")

    def _load_api_key(self) -> str:
        # Try central SecretsManager first (preferred by project)
        if SecretsManager:
            try:
                return SecretsManager.get_secret("ANTHROPIC_API_KEY", required=True)
            except Exception as e:
                logger.debug(f"SecretsManager could not load ANTHROPIC_API_KEY: {e}")
        # Fallback to plain environment variable
        val = os.getenv("ANTHROPIC_API_KEY", "")
        if not val:
            logger.error("ANTHROPIC_API_KEY not found in environment")
        return val

    @staticmethod
    def _build_system_prompt() -> str:
        return (
            "You are an expert trading prompt engineer. Given the ORIGINAL PROMPT and its "
            "BACKTEST CONTEXT (performance), generate targeted improvements.\n"
            "Respond ONLY with a single valid JSON object with keys: "
            "improved_prompt, findings, improvements, observations, issues.\n"
            "- improved_prompt: a COMPLETE, ready-to-use revised prompt in raw Markdown.\n"
            "  Requirements: include ALL sections and headings fully expanded; do NOT use placeholders like '...','[omitted]','[same as original]', or references like 'rest of steps same as original'.\n"
            "  Exclude any section titled 'OUTPUT FORMAT' or 'OUTPUT REQUIREMENTS' (we will append the original one separately).\n"
            "- findings: return as raw Markdown (bulleted list).\n"
            "- improvements: return as raw Markdown (bulleted list).\n"
            "- observations: return as raw Markdown (bulleted list).\n"
            "- issues: return as raw Markdown (bulleted list).\n"
            "Rules: Output only JSON, no extra commentary. Ensure content completeness; if needed, be concise but never omit sections."
        )

    @staticmethod
    def _compose_user_message(original_prompt_md: str, performance_context_md: str, extra_context: Optional[str] = None) -> str:
        msg = (
            "# ORIGINAL PROMPT (Markdown)\n" + original_prompt_md.strip() + "\n\n" +
            "# BACKTEST CONTEXT (Summary)\n" + performance_context_md.strip()
        )
        if extra_context and extra_context.strip():
            msg += "\n\n# ADDITIONAL CONTEXT\n" + extra_context.strip()
        return msg

    @staticmethod
    def _default_payload(model: str, system: str, user_content: str) -> Dict[str, Any]:
        return {
            "model": model,
            "system": system,
            "messages": [
                {"role": "user", "content": user_content}
            ],
            "max_tokens": 6000,
            "temperature": 0.2,
            # response_format removed for compatibility with Anthropic 2023-06-01; enforce JSON via instructions
        }

    def _post_with_retry(self, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        last_status = 0
        last_body: Dict[str, Any] = {}
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    ANTHROPIC_API_URL,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.timeout,
                )
                last_status = resp.status_code
                # Attempt JSON parse even for non-2xx to get error type
                try:
                    last_body = resp.json()
                except Exception:
                    last_body = {"raw": resp.text}

                if resp.status_code == 200:
                    return resp.status_code, last_body

                # Handle well-known errors
                if resp.status_code == 401 or resp.status_code == 403:
                    raise PermissionError("Authentication/authorization failed for Anthropic API")

                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    # backoff and retry
                    sleep_s = min(2.0 * attempt, 6.0) + random.uniform(0.0, 0.5)
                    logger.warning(f"Anthropic API transient error {resp.status_code}; retrying in {sleep_s:.1f}s (attempt {attempt}/{self.max_retries})")
                    time.sleep(sleep_s)
                    continue

                # Other non-retriable HTTP errors
                break

            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt >= self.max_retries:
                    raise TimeoutError(f"Anthropic API request failed after retries: {e}")
                sleep_s = min(2.0 * attempt, 6.0) + random.uniform(0.0, 0.5)
                logger.warning(f"Network error contacting Anthropic ({e}); retrying in {sleep_s:.1f}s (attempt {attempt}/{self.max_retries})")
                time.sleep(sleep_s)
            except PermissionError:
                raise
            except Exception as e:
                # Unexpected error; do not retry unless last status suggests transient
                logger.error(f"Unexpected error calling Anthropic: {e}")
                break

        return last_status, last_body

    @staticmethod
    def _extract_text_content(api_json: Dict[str, Any]) -> str:
        """Anthropic messages API returns a content array; pick first text block."""
        try:
            content = api_json.get("content")
            if isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("type") == "text":
                    return str(first.get("text") or "").strip()
            # Fallback: Some SDKs may already return the JSON-string as top-level field
            if isinstance(api_json.get("output_text"), str):
                return api_json["output_text"].strip()
        except Exception:
            pass
        # As a last resort, try entire body dump
        return json.dumps(api_json)

    @staticmethod
    def _safe_parse_model_json(text: str) -> Dict[str, Any]:
        """Parse model text to JSON, tolerating leading/trailing text. Return dict."""
        # Try direct JSON parse first
        try:
            return json.loads(text)
        except Exception:
            pass
        # Attempt to extract first JSON object substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = text[start : end + 1]
            try:
                return json.loads(snippet)
            except Exception:
                pass
        # Fallback
        return {}

    @staticmethod
    @staticmethod
    def _to_markdown(value: Any) -> str:
        """Normalize value into readable Markdown text.
        - lists -> bullet list
        - dict -> key: value bullets
        - primitives -> string
        Also tolerates stringified lists/dicts (JSON or Python-literal style).
        """
        try:
            # If it's a string that looks like a JSON/Python list or dict, parse it
            if isinstance(value, str):
                s = value.strip()
                # If wrapped in quotes like "[ ... ]" or '\n[ ... ]\n', unwrap once
                if s and s[0] in ('"', "'") and len(s) > 1 and s[1] in "[{":
                    q = s[0]
                    if s.endswith(q):
                        s = s[1:-1].strip()
                if s and s[0] in "[{":
                    try:
                        parsed = json.loads(s)
                        value = parsed
                    except Exception:
                        try:
                            import ast
                            value = ast.literal_eval(s)
                        except Exception:
                            pass
            if isinstance(value, list):
                lines = []
                for item in value:
                    if isinstance(item, (str, int, float)):
                        s = str(item)
                    elif isinstance(item, dict):
                        s = "; ".join(f"{k}: {v}" for k, v in item.items())
                    else:
                        s = json.dumps(item, ensure_ascii=False)
                    lines.append(f"- {s}")
                return "\n".join(lines).strip()
            if isinstance(value, dict):
                return "\n".join(f"- {k}: {v}" for k, v in value.items()).strip()
            return str(value or "").strip()
        except Exception:
            return str(value or "").strip()

    @staticmethod
    def _normalize_response(data: Dict[str, Any]) -> AnthropicResponse:
        # Ensure all expected keys exist and are strings or rendered markdown
        improved_val = data.get("improved_prompt")
        if isinstance(improved_val, list):
            # Rare, but if the model returns list of sections, join with blank lines
            improved_prompt = "\n\n".join(AnthropicClient._to_markdown(x) for x in improved_val)
        else:
            improved_prompt = AnthropicClient._to_markdown(improved_val)
        findings = AnthropicClient._to_markdown(data.get("findings"))
        improvements = AnthropicClient._to_markdown(data.get("improvements"))
        observations = AnthropicClient._to_markdown(data.get("observations"))
        issues = AnthropicClient._to_markdown(data.get("issues"))
        return AnthropicResponse(
            improved_prompt=improved_prompt,
            findings=findings,
            improvements=improvements,
            observations=observations,
            issues=issues,
            raw_json=data or {},
        )

    def generate_recommendations(
        self,
        *,
        original_prompt_md: str,
        performance_context_md: str,
        extra_context: Optional[str] = None,
    ) -> AnthropicResponse:
        """Call Anthropic to get structured prompt improvement recommendations."""
        system = self._build_system_prompt()
        user = self._compose_user_message(original_prompt_md, performance_context_md, extra_context)
        payload = self._default_payload(self.model, system, user)

        status, body = self._post_with_retry(payload)
        if status != 200:
            # Surface typed error info but do not leak secret
            err_type = (body or {}).get("error", {}).get("type") if isinstance(body, dict) else None
            err_msg = (body or {}).get("error", {}).get("message") if isinstance(body, dict) else None
            raise RuntimeError(f"Anthropic API error {status}: {err_type or ''} {err_msg or ''}".strip())

        text = self._extract_text_content(body)
        data = self._safe_parse_model_json(text)
        if not data:
            logger.warning("Model returned non-JSON or empty content; using safe fallbacks")
        return self._normalize_response(data)


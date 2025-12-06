"""
Central prompt templates and provider-shaped message builders
for the Intelligent Prompt Builder.

This module centralizes all prompt wording used to:
- Seed an initial strategy from one or more images
- Improve a candidate prompt using backtest metrics
- Repair malformed JSON responses (self-repair loop)

Provider message building supports Anthropic and OpenAI with image inputs.
Keep this file lightweight and Pylance-friendly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from .canonical_json import CANONICAL_SCHEMA_SUMMARY

Provider = Literal["anthropic", "openai"]
Kind = Literal["seed", "improve", "repair"]

PROMPT_VERSION = "v0.1"


# ---------- Core text templates ----------

def get_seed_system_prompt() -> str:
    return (
        "You are a trading prompt engineer. Analyze chart images to propose a structured "
        "strategy recommendation that our backtester can execute. Favor clarity and "
        "risk-first logic."
    )


def get_seed_user_instructions(payload: Dict[str, Any]) -> str:
    symbol = payload.get("symbol") or ""
    timeframe = payload.get("timeframe") or ""
    analyzer_prompt = payload.get("analyzer_prompt") or ""

    if analyzer_prompt:
        # Iteration 1+: use the improved analyzer prompt from previous iteration
        task_text = (
            f"Task: Analyze the provided chart image using this analyzer prompt and return a trade decision.\n\n"
            f"Analyzer prompt:\n{analyzer_prompt}\n\n"
            f"Context: symbol={symbol} timeframe={timeframe}\n"
        )
    else:
        # Iteration 0: seed from scratch
        task_text = (
            f"Task: From the provided chart image, propose a trade decision and structured plan.\n"
            f"Context: symbol={symbol} timeframe={timeframe}\n"
            "This is for the crypto market, and your prompt should be applicable to multiple symbols and timeframes.\n"
        )

    return (
        f"{task_text}"
        f"Output JSON (canonical, concise):\n"
        f"{CANONICAL_SCHEMA_SUMMARY}\n\n"
        "Rules:\n"
        "- Return strictly JSON, no markdown code fences or prose.\n"
        "- Use decimals for percentages (e.g., 0.01 = 1%).\n"
        "- If using rule-based prices (breakout/retest/etc.), specify rule text and optional offset_pct.\n"
        "- Provide at least one take profit. Multiple TPs are allowed.\n"
        "- Include risk and confidence components.\n"
        "- Keep rationale brief.\n"
        "- IMPORTANT: Include a 'prompt_used' field containing the exact concise analyzer prompt text you used to analyze this chart. Do NOT include any 'OUTPUT REQUIREMENTS' section; it is injected locally in our system.\n"
    )


def get_improve_system_prompt() -> str:
    return (
        "You are a trading prompt engineer. Based on measured backtest results, return a STRICT canonical JSON "
        "trade plan that our backtester can execute. Also include the improved analyzer prompt in a 'prompt_used' "
        "field. Do not include markdown or code fences."
    )


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """Compact metrics formatting for the improve prompt."""
    keys = [
        "pnl_pct", "sharpe", "win_rate", "max_dd", "trade_count",
        "rr_avg", "rr_median", "std_pnl", "consistency",
    ]
    parts: List[str] = []
    for k in keys:
        if k in metrics and metrics[k] is not None:
            parts.append(f"{k}={metrics[k]}")
    return ", ".join(parts) if parts else "(no metrics)"


def get_improve_user_instructions(payload: Dict[str, Any]) -> str:
    metric_hint = payload.get("primary_metric") or "pnl_pct"
    candidate = payload.get("candidate_prompt_text") or ""
    metrics = payload.get("metrics_summary") or {}

    return (
        f"Task: Improve the prompt based on backtest results.\n"
        "Context: Crypto market; should generalize across symbols/timeframes.\n"
        f"Current analyzer prompt:\n{candidate}\n\n"
        f"Backtest metrics: {_format_metrics(metrics)}\n\n"
        f"Goal: Improve {metric_hint} and reduce max drawdown without overfitting.\n\n"
        f"Output (STRICTLY JSON ONLY, no fences/no prose):\n"
        f"{CANONICAL_SCHEMA_SUMMARY}\n\n"
        "Rules:\n"
        "- Return STRICT JSON only.\n"
        "- The 'action', 'entry', 'stop_loss', 'take_profits' fields should be placeholder/example values (we won't use them).\n"
        "- You MUST include a 'prompt_used' field that contains the IMPROVED prompt text.\n"
        "- Focus on improving the prompt logic based on the backtest metrics.\n"
        "- Keep the improved prompt concise and generalizable.\n"
        "- Add instructions or actionable rules to the prompt that helps a trader to get better results.\n"
        "- Keep in mind the improoved prompt should be applicable to multiple symbols and timeframes but still not be to generica.\n"
        "- Youre imrpovments must conatin actionable and clear intructions for my trader\n"
    )


def get_json_repair_instructions(payload: Dict[str, Any]) -> str:
    """Explain how to fix JSON only, not the underlying decision logic."""
    errors: List[str] = payload.get("errors", [])
    return (
        "Your previous response was not valid according to the canonical schema.\n"
        "Fix ONLY the JSON formatting/fields; do NOT change your decision or logic.\n"
        "Guidelines:\n"
        "- Return strictly JSON (no prose, no code fences).\n"
        "- Use decimals for percentages.\n"
        "- Ensure required keys exist and are correctly typed.\n"
        "- For take_profits, include at least one target; size_pct may be omitted (will be distributed).\n"
        "- For risk, include risk_pct or position_size_pct.\n"
        "- For entry/stop_loss/take_profit, provide either price or rule.\n\n"
        f"Validation errors: {errors}\n"
        f"Canonical JSON envelope:\n{CANONICAL_SCHEMA_SUMMARY}\n"
    )


# ---------- Provider message building ----------

_def_image_payload = {
    "media_type_default": "image/png",
}


def _image_part_for_openai(image: Dict[str, Any]) -> Dict[str, Any]:
    url = image.get("url")
    media_type = image.get("media_type") or _def_image_payload["media_type_default"]
    if not url:
        # Expect base64
        b64 = image.get("base64") or ""
        url = f"data:{media_type};base64,{b64}"
    return {"type": "image_url", "image_url": {"url": url}}


def _image_part_for_anthropic(image: Dict[str, Any]) -> Dict[str, Any]:
    url = image.get("url")
    media_type = image.get("media_type") or _def_image_payload["media_type_default"]
    if url:
        return {"type": "image", "source": {"type": "url", "url": url}}
    # else base64
    b64 = image.get("base64") or ""
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def _openai_messages_from_text_and_images(system_text: str, user_text: str, images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    user_content.extend(_image_part_for_openai(img) for img in images)
    return [
        {"role": "system", "content": system_text},
        {"role": "user", "content": user_content},
    ]


def _anthropic_messages_from_text_and_images(system_text: str, user_text: str, images: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    content.extend(_image_part_for_anthropic(img) for img in images)
    # Anthropic messages API typically wants: system: str, messages=[{"role":"user","content":[...] }]
    return system_text, [{"role": "user", "content": content}]


def build_messages_for_provider(provider: Provider, kind: Kind, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return provider-shaped message payloads.

    payload keys:
      - image(s): for seed -> payload["image"] (single dict) or payload["images"] list
      - original_prompt_text, candidate_prompt_text, metrics_summary, symbols, timeframes
      - errors: for repair
    """
    images: List[Dict[str, Any]] = []
    if kind == "seed":
        if payload.get("images"):
            images = list(payload["images"])  # type: ignore[assignment]
        elif payload.get("image"):
            images = [payload["image"]]  # type: ignore[list-item]

        sys_text = get_seed_system_prompt()
        usr_text = get_seed_user_instructions(payload)

    elif kind == "improve":
        sys_text = get_improve_system_prompt()
        usr_text = get_improve_user_instructions(payload)

    else:  # repair
        sys_text = "You are a careful JSON formatter."
        usr_text = get_json_repair_instructions(payload)

    if provider == "openai":
        messages = _openai_messages_from_text_and_images(sys_text, usr_text, images)
        return {"messages": messages, "version": PROMPT_VERSION, "kind": kind}

    if provider == "anthropic":
        system_text, messages = _anthropic_messages_from_text_and_images(sys_text, usr_text, images)
        return {"system": system_text, "messages": messages, "version": PROMPT_VERSION, "kind": kind}

    raise ValueError(f"Unsupported provider: {provider}")


__all__ = [
    "PROMPT_VERSION",
    "get_seed_system_prompt",
    "get_seed_user_instructions",
    "get_improve_system_prompt",
    "get_improve_user_instructions",
    "get_json_repair_instructions",
    "build_messages_for_provider",
]


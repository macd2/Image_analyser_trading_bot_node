"""
Model discovery service for OpenAI and Anthropic.

- Queries providers for available models (best-effort, optional)
- Filters to vision-capable chat models when possible
- Normalizes to a common structure and supports caching in-memory

Network calls are optional and will fail gracefully when API keys are missing.
We avoid installing extra deps: use requests.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
import time
import requests

# Minimal fallback allowlists (vision-capable families change; keep conservative)
OPENAI_FALLBACK = [
    "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o4-mini"
]
ANTHROPIC_FALLBACK = [
    "claude-3.5-sonnet", "claude-3.5-haiku",
    # Common Anthropic naming with dashes
    "claude-3-5-sonnet", "claude-3-5-haiku",
]

_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_CACHE_TTL = 15 * 60.0  # 15 minutes


def _cache_get(key: str) -> Optional[List[Dict[str, Any]]]:
    t = _CACHE.get(key)
    if not t: return None
    ts, data = t
    if time.time() - ts < _CACHE_TTL:
        return data
    return None


def _cache_set(key: str, data: List[Dict[str, Any]]):
    _CACHE[key] = (time.time(), data)


def _supports_image_openai(model_id: str) -> bool:
    # Heuristic: known families likely vision-capable
    return any(model_id.startswith(fam) for fam in OPENAI_FALLBACK)


def _supports_image_anthropic(info: Dict[str, Any]) -> bool:
    # Anthropic /v1/models returns input_modalities (or modalities) in some deployments
    mods = info.get("input_modalities") or info.get("modalities") or []
    if isinstance(mods, list) and any(isinstance(m, str) and m.lower() == "image" for m in mods):
        return True
    # Fallback heuristics based on model id naming
    mid = str(info.get("id") or info.get("name") or "").lower()
    mid_norm = mid.replace("_", "-").replace(".", "-")
    # Most claude-3 family variants support images; be permissive here to avoid empty dropdowns
    if mid_norm.startswith(("claude-3-", "claude-3", "claude-4-", "claude-4")):
        return True
    # Check against conservative fallback list (accept both dot and dash variants)
    return any(mid_norm.startswith(str(fam).replace(".", "-").lower()) for fam in ANTHROPIC_FALLBACK)


def discover_openai_models(use_cache: bool = True) -> List[Dict[str, Any]]:
    if use_cache:
        cached = _cache_get("openai")
        if cached is not None:
            return cached
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY_1")
    url = "https://api.openai.com/v1/models"
    out: List[Dict[str, Any]] = []
    try:
        if not key:
            raise RuntimeError("missing OPENAI_API_KEY")
        r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=10)
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI list error {r.status_code}")
        body = r.json()
        data = body.get("data", []) if isinstance(body, dict) else []
        for m in data:
            mid = m.get("id")
            if not mid: continue
            out.append({
                "provider": "openai",
                "id": mid,
                "supports_image": _supports_image_openai(mid),
                "raw": m,
            })
    except Exception:
        # Fallback
        out = [{"provider": "openai", "id": mid, "supports_image": True} for mid in OPENAI_FALLBACK]
    _cache_set("openai", out)
    return out


def discover_anthropic_models(use_cache: bool = True) -> List[Dict[str, Any]]:
    if use_cache:
        cached = _cache_get("anthropic")
        if cached is not None:
            return cached
    key = os.environ.get("ANTHROPIC_API_KEY")
    url = "https://api.anthropic.com/v1/models"
    out: List[Dict[str, Any]] = []
    try:
        if not key:
            raise RuntimeError("missing ANTHROPIC_API_KEY")
        r = requests.get(url, headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }, timeout=10)
        if r.status_code != 200:
            raise RuntimeError(f"Anthropic list error {r.status_code}")
        body = r.json()
        data = body.get("data", []) if isinstance(body, dict) else []
        for m in data:
            mid = m.get("id") or m.get("name")
            if not mid: continue
            out.append({
                "provider": "anthropic",
                "id": mid,
                "supports_image": _supports_image_anthropic(m),
                "raw": m,
            })
    except Exception:
        out = [{"provider": "anthropic", "id": mid, "supports_image": True} for mid in ANTHROPIC_FALLBACK]
    _cache_set("anthropic", out)
    return out


def discover_all_models(vision_only: bool = True, use_cache: bool = True) -> List[Dict[str, Any]]:
    """Return normalized list of available models across providers."""
    openai_models = discover_openai_models(use_cache=use_cache)
    anthropic_models = discover_anthropic_models(use_cache=use_cache)
    models = openai_models + anthropic_models
    if vision_only:
        models = [m for m in models if m.get("supports_image")]
    return models


__all__ = [
    "discover_openai_models",
    "discover_anthropic_models",
    "discover_all_models",
]


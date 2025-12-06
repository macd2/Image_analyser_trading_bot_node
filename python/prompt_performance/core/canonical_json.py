"""
Canonical JSON envelope for Intelligent Prompt Builder

- Minimal but broad schema to keep models unconstrained while ensuring comparability
- Pure-Python validator/normalizer (no external deps) to satisfy Pylance and keep lightweight

This module is intentionally independent from provider clients and UI.
It exposes:
  - CANONICAL_SCHEMA_SUMMARY: short human-readable schema guidance for prompts
  - validate_and_normalize(data): returns (normalized, errors) without raising
  - normalize_only(data): returns normalized or raises ValueError with detailed message

Conventions:
- Percentages are decimals (0.01 = 1%). Strings like "1%" are converted to 0.01.
- Prices are floats. If entry/SL/TP are provided as plain numbers, they are wrapped.
- take_profits supports list[float] or list[object]; size_pct is optional. If all
  size_pct are missing, we distribute equally. If provided and sum>1, we renormalize
  with a warning.
- risk requires at least one of risk_pct or position_size_pct.
- confidence may include setup, rr, environment, overall. We do not round here;
  rounding to 3 decimals remains the responsibility of the data layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional, Union, cast

ALLOWED_ACTIONS = {"long", "short", "hold"}

CANONICAL_SCHEMA_SUMMARY = """
{
  "action": "long",
  "entry": { "price": 123.45 },
  "stop_loss": { "price": 120.00 },
  "take_profits": [
    { "price": 125.00, "size_pct": 0.5 },
    { "price": 128.00, "size_pct": 0.5 }
  ],
  "risk": {
    "risk_pct": 0.01,
    "max_bars_in_trade": 48
  },
  "confidence": {
    "setup": 0.7,
    "rr": 0.6,
    "environment": 0.65,
    "overall": 0.65
  },
  "rationale": "Short reason for the trade.",

  "timeframe": "1h",
  "entry_conditions": "Entry logic in brief.",
  "invalidation_conditions": "When this idea is invalid.",

  "prompt_used": "the prompt you woudl use to analyze similar charts next time"
}
"""


def _to_float(x: Any, key_path: str, errors: List[str]) -> Optional[float]:
    """Best-effort float parse for prices/ratios.

    Accepts numeric or strings like "1.23", "1%", "0.5%". Returns None and logs error on failure.
    """
    if x is None:
        errors.append(f"{key_path}: missing value")
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().lower()
        try:
            if s.endswith("%"):
                num = float(s[:-1].strip())
                return num / 100.0
            # plain float string
            return float(s)
        except Exception:
            errors.append(f"{key_path}: invalid numeric value '{x}'")
            return None
    errors.append(f"{key_path}: expected number or percent-string, got {type(x).__name__}")
    return None


def _to_decimal_pct(x: Any, key_path: str, errors: List[str]) -> Optional[float]:
    """Normalize percentages to decimals in [0, 1].

    Accepts numeric (interprets >1 as percent, e.g., 5 -> 0.05) or strings ("5%", "0.05").
    Clamps to [0, 1] and records warning if clamped.
    """
    if isinstance(x, (int, float)):
        v = float(x)
        v = v / 100.0 if v > 1.0 else v
    elif isinstance(x, str):
        v = _to_float(x, key_path, errors)
        if v is None:
            return None
        # if user wrote "5" as string, interpret as 5% like numeric branch
        v = v / 100.0 if v > 1.0 else v
    else:
        errors.append(f"{key_path}: expected percent (number or string)")
        return None

    if v < 0.0:
        errors.append(f"{key_path}: negative percent not allowed; clamped to 0")
        v = 0.0
    if v > 1.0:
        errors.append(f"{key_path}: percent > 1.0 not allowed; clamped to 1.0")
        v = 1.0
    return v


def _normalize_price_or_rule(obj: Any, key_path: str, errors: List[str]) -> Optional[Dict[str, Any]]:
    """Normalize entry/stop_loss/take_profit target to a unified object.

    Accepted forms:
    - number => {"type":"price","price": value}
    - {"price": number} => add type: price
    - {"rule": str, ...} => keep type if provided, default type: "rule"
    - {"type": "limit"|"market"|"breakout"|"retest"|"price"|"rule", ...}
    """
    if isinstance(obj, (int, float, str)):
        # try number first; if string that parses to number, treat as price
        v = _to_float(obj, key_path, errors)
        if v is None:
            # could be a textual rule; fall back to rule-type
            return {"type": "rule", "rule": str(obj)}
        return {"type": "price", "price": v}

    if not isinstance(obj, dict):
        errors.append(f"{key_path}: expected number or object, got {type(obj).__name__}")
        return None

    out: Dict[str, Any] = dict(obj)  # shallow copy
    tp = str(out.get("type") or "").strip().lower()

    if "price" in out:
        price = _to_float(out.get("price"), f"{key_path}.price", errors)
        if price is not None:
            out["price"] = price
        out.setdefault("type", "price")
        return out

    if "rule" in out:
        out.setdefault("type", "rule")
        return out

    # If only type present (e.g., limit/market) without price/rule, leave as-is for later resolution
    if tp:
        out["type"] = tp
        return out

    errors.append(f"{key_path}: must include price or rule")
    return None


def _normalize_take_profits(tps: Any, key_path: str, errors: List[str]) -> List[Dict[str, Any]]:
    """Normalize take_profits into a list of objects and fix size_pct distribution."""
    result: List[Dict[str, Any]] = []

    if isinstance(tps, list):
        for i, item in enumerate(tps):
            tp_obj = _normalize_price_or_rule(item, f"{key_path}[{i}]", errors)
            if tp_obj is None:
                continue
            # size_pct optional
            if "size_pct" in tp_obj:
                sp = _to_decimal_pct(tp_obj.get("size_pct"), f"{key_path}[{i}].size_pct", errors)
                if sp is not None:
                    tp_obj["size_pct"] = sp
                else:
                    tp_obj.pop("size_pct", None)
            result.append(tp_obj)
    else:
        # allow single number/object
        tp_obj = _normalize_price_or_rule(tps, key_path, errors)
        if tp_obj is not None:
            result.append(tp_obj)

    # Assign equal sizes if all missing
    if result and all("size_pct" not in tp for tp in result):
        eq = 1.0 / len(result)
        for tp in result:
            tp["size_pct"] = eq
    else:
        # If provided but sum > 1, renormalize proportionally
        total = sum(tp.get("size_pct", 0.0) for tp in result)
        if total > 1.0 + 1e-9 and total > 0:
            for tp in result:
                tp["size_pct"] = tp.get("size_pct", 0.0) / total
            errors.append("take_profits: size_pct sum > 1.0; renormalized")

    return result


def validate_and_normalize(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Validate and normalize a candidate JSON envelope.

    Returns (normalized, errors). If errors is non-empty, normalized may be partial.
    Callers can feed errors back to the LLM for self-repair.
    """
    errors: List[str] = []
    norm: Dict[str, Any] = {}

    if not isinstance(data, dict):
        return None, ["root: expected object"]

    # action
    action = str(data.get("action", "")).strip().lower()
    if action not in ALLOWED_ACTIONS:
        errors.append("action: required and must be one of ['long','short','hold']")
    else:
        norm["action"] = action

    # entry
    entry = _normalize_price_or_rule(data.get("entry"), "entry", errors)
    if entry is None:
        errors.append("entry: required")
    else:
        norm["entry"] = entry

    # stop_loss
    sl = _normalize_price_or_rule(data.get("stop_loss"), "stop_loss", errors)
    if sl is None:
        errors.append("stop_loss: required")
    else:
        norm["stop_loss"] = sl

    # take_profits
    if "take_profits" not in data:
        errors.append("take_profits: required (list)")
        tps: List[Dict[str, Any]] = []
    else:
        tps = _normalize_take_profits(data.get("take_profits"), "take_profits", errors)
        if not tps:
            errors.append("take_profits: must contain at least one target")
    norm["take_profits"] = tps

    # risk
    risk_in = cast(Dict[str, Any], data.get("risk") or {})
    if not isinstance(risk_in, dict):
        errors.append("risk: must be object with risk_pct or position_size_pct")
        risk_in = {}
    rp = risk_in.get("risk_pct")
    ps = risk_in.get("position_size_pct")
    norm_risk: Dict[str, Any] = {}
    if rp is not None:
        rp_v = _to_decimal_pct(rp, "risk.risk_pct", errors)
        if rp_v is not None:
            norm_risk["risk_pct"] = rp_v
    if ps is not None:
        ps_v = _to_decimal_pct(ps, "risk.position_size_pct", errors)
        if ps_v is not None:
            norm_risk["position_size_pct"] = ps_v
    # passthrough optional fields
    if "max_bars_in_trade" in risk_in:
        mb = risk_in.get("max_bars_in_trade")
        if isinstance(mb, (int, float)):
            norm_risk["max_bars_in_trade"] = int(mb)
        else:
            errors.append("risk.max_bars_in_trade: must be integer number of bars")
    if not norm_risk.get("risk_pct") and not norm_risk.get("position_size_pct"):
        errors.append("risk: must include risk_pct or position_size_pct")
    norm["risk"] = norm_risk

    # confidence
    conf_in = cast(Dict[str, Any], data.get("confidence") or {})
    if not isinstance(conf_in, dict):
        errors.append("confidence: must be object with components")
        conf_in = {}
    norm_conf: Dict[str, Any] = {}
    for k in ("setup", "rr", "environment", "overall"):
        if k in conf_in:
            v = _to_float(conf_in.get(k), f"confidence.{k}", errors)
            if v is not None:
                # clamp to [0, 1] if it looks like a score
                if 0.0 <= v <= 1.0:
                    norm_conf[k] = float(v)
                else:
                    # allow raw numbers; keep as-is
                    norm_conf[k] = float(v)
        else:
            # Not strictly required for all components; leave optional
            pass
    if not norm_conf:
        errors.append("confidence: expected at least one component (setup, rr, environment, overall)")
    norm["confidence"] = norm_conf

    # rationale
    rationale = data.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        norm["rationale"] = rationale.strip()
    else:
        errors.append("rationale: required non-empty string")

    # optional pass-throughs with light checks
    for opt_key in (
        "timeframe",
        "rr_expected",
        "trailing_stop",
        "entry_conditions",
        "invalidation_conditions",
        "order",
        "position",
        "metadata",
        "prompt_used",
    ):
        if opt_key in data:
            norm[opt_key] = data[opt_key]

    return (norm if not errors else norm), errors


def normalize_only(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and raise on errors with a readable message."""
    norm, errs = validate_and_normalize(data)
    if errs:
        raise ValueError("; ".join(errs))
    assert norm is not None
    return norm


__all__ = [
    "ALLOWED_ACTIONS",
    "CANONICAL_SCHEMA_SUMMARY",
    "validate_and_normalize",
    "normalize_only",
]


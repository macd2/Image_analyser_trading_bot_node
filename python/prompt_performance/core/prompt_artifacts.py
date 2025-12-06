"""
Prompt artifact store: save and list promoted winner prompts.
Stores JSON file in core/prompt_artifacts.json with simple schema.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACTS_PATH = Path(__file__).parent / "prompt_artifacts.json"


def _load_all(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    p = path or ARTIFACTS_PATH
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _save_all(items: List[Dict[str, Any]], path: Optional[Path] = None) -> None:
    p = path or ARTIFACTS_PATH
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_artifacts(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    return _load_all(path)


def save_artifact(*, name: str, prompt_text: str, signature: str, metadata: Optional[Dict[str, Any]] = None, path: Optional[Path] = None) -> Dict[str, Any]:
    items = _load_all(path)
    # Enforce unique name and unique signature
    for it in items:
        if it.get("name") == name:
            # overwrite text and metadata for same name
            it["prompt_text"] = prompt_text
            it["signature"] = signature
            it["metadata"] = metadata or {}
            _save_all(items, path)
            return it
    for it in items:
        if it.get("signature") == signature:
            # signature exists under a different name: no-op
            return it
    new_item = {
        "name": name,
        "prompt_text": prompt_text,
        "signature": signature,
        "metadata": metadata or {},
    }
    items.append(new_item)
    _save_all(items, path)
    return new_item


__all__ = ["list_artifacts", "save_artifact", "ARTIFACTS_PATH"]


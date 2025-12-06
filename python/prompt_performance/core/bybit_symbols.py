from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests

SYMBOLS_JSON = Path(__file__).with_name("bybit_symbols.json")
BYBIT_BASE_URL = "https://api.bybit.com"
INSTRUMENTS_PATH = "/v5/market/instruments-info"


@dataclass
class SymbolList:
    category: str
    fetched_at: float
    symbols: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {"category": self.category, "fetched_at": self.fetched_at, "symbols": self.symbols}

    @staticmethod
    def from_dict(d: Dict[str, object]) -> "SymbolList":
        return SymbolList(category=str(d.get("category", "linear")), fetched_at=float(d.get("fetched_at", 0)), symbols=list(d.get("symbols", [])))


def _fetch_page(category: str, cursor: Optional[str] = None, limit: int = 1000) -> Dict[str, object]:
    params: Dict[str, object] = {"category": category, "limit": limit}
    if cursor:
        params["cursor"] = cursor
    url = BYBIT_BASE_URL + INSTRUMENTS_PATH
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def fetch_bybit_symbols(category: str = "linear") -> List[str]:
    # Page through all instruments for the category and extract symbols that can be used for kline
    symbols: List[str] = []
    cursor: Optional[str] = None
    while True:
        data = _fetch_page(category=category, cursor=cursor)
        if not isinstance(data, dict) or data.get("retCode") != 0:
            break
        result = data.get("result", {}) or {}
        items = result.get("list", []) or []
        for item in items:
            sym = item.get("symbol") if isinstance(item, dict) else None
            status = item.get("status") if isinstance(item, dict) else None
            if isinstance(sym, str) and sym and (status in (None, "Trading", "Listed")):
                symbols.append(sym)
        cursor = result.get("nextPageCursor") or None
        if not cursor:
            break
    # De-duplicate and sort
    symbols = sorted(set(symbols))
    return symbols


def refresh_bybit_symbols(category: str = "linear") -> List[str]:
    symbols = fetch_bybit_symbols(category=category)
    payload = SymbolList(category=category, fetched_at=time.time(), symbols=symbols).to_dict()
    try:
        SYMBOLS_JSON.write_text(json.dumps(payload, indent=2))
    except Exception:
        # Best-effort: ignore cache write errors
        pass
    return symbols


def get_bybit_symbols_cached(category: str = "linear", max_age_seconds: int = 7 * 24 * 3600) -> List[str]:
    # Try cache first
    try:
        if SYMBOLS_JSON.exists():
            data = json.loads(SYMBOLS_JSON.read_text())
            sl = SymbolList.from_dict(data)
            if sl.category == category and (time.time() - sl.fetched_at) < max_age_seconds and sl.symbols:
                return sl.symbols
    except Exception:
        pass
    # Refresh if cache missing/expired
    return refresh_bybit_symbols(category=category)


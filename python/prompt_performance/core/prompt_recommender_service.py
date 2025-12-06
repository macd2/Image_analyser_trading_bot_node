import hashlib
import json
import logging
import sqlite3
import time
import re

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

from .anthropic_client import AnthropicClient, AnthropicResponse

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "backtests.db"
CACHE_PATH = Path(__file__).parent / "prompt_recommendations_cache.json"


@dataclass
class PromptPerformance:
    prompt_name: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    loss_rate: float
    avg_pnl_percent: float
    avg_confidence: float
    long_trades: int
    short_trades: int
    taken_signals_pct: float
    summary: str
    backtest_data_hash: str


def _load_cache() -> Dict[str, Any]:
    try:
        if CACHE_PATH.exists():
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read cache file: {e}")
    return {}


def _save_cache(data: Dict[str, Any]) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to write cache file: {e}")


def _compute_hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()


def get_original_prompt_text(prompt_name: str) -> Optional[str]:
    """Resolve the actual prompt text for a given prompt_name without requiring charts dir.

    Strategy:
    1) Try PROMPT_REGISTRY (short names) from backtest_with_images
    2) Try dynamic function in trading_bot.core.prompts.analyzer_prompt by exact name
    3) If not found and name doesn't start with prefix, try 'get_analyzer_prompt_' + prompt_name
    """
    func = None
    try:
        # Import analyzer_prompt directly and reload to ensure latest functions are visible
        import importlib
        from trading_bot.core.prompts import analyzer_prompt as ap  # type: ignore
        try:
            ap = importlib.reload(ap)
        except Exception:
            pass
        # 1) Known short-name aliases (replicated locally to avoid importing backtest_with_images)
        short_map = {
            'code_nova': getattr(ap, 'code_nova_improoved_based_on_analyzis', None),
            'hybrid': getattr(ap, 'get_analyzer_prompt_hybrid_ultimate', None),
            'v28_short_fix': getattr(ap, 'get_analyzer_prompt_improved_v28_short_fix', None),
            'grok_fineTune': getattr(ap, 'get_analyzer_prompt_optimized_v26_grok_fineTune', None),
            'trade_playbook_v1': getattr(ap, 'get_analyzer_prompt_trade_playbook_v1', None),
        }
        if prompt_name in short_map and short_map[prompt_name] is not None:
            func = short_map[prompt_name]
        if func is None:
            # 2) Exact function name
            func = getattr(ap, prompt_name, None)
        # 3) Prefixed convention (only if name isn't already a 'get_analyzer_prompt*')
        if func is None and not prompt_name.startswith("get_analyzer_prompt"):
            cand = f"get_analyzer_prompt_{prompt_name}"
            func = getattr(ap, cand, None)
    except Exception as e:
        logger.debug(f"Dynamic prompt import failed for {prompt_name}: {e}")

    if func is None:
        # Fallback: load analyzer_prompt directly from file path to avoid sys.path/package issues
        try:
            import importlib.util
            from pathlib import Path as _P
            repo_root = _P(__file__).resolve().parent.parent.parent
            ap_path = repo_root / "trading_bot" / "core" / "prompts" / "analyzer_prompt.py"
            spec = importlib.util.spec_from_file_location("_ap_dynamic", str(ap_path))
            if spec and spec.loader:
                _ap = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(_ap)  # type: ignore[attr-defined]
                # Try exact name first
                func = getattr(_ap, prompt_name, None)
                # Then prefixed convention if needed
                if func is None and not prompt_name.startswith("get_analyzer_prompt"):
                    cand = f"get_analyzer_prompt_{prompt_name}"
                    func = getattr(_ap, cand, None)
        except Exception as e:
            logger.debug(f"File-based analyzer_prompt import failed for {prompt_name}: {e}")

    if func is None:
        logger.error(f"Prompt function not found for '{prompt_name}'")
        return None

    # Call prompt function with minimal context; tolerate signature differences
    try:
        try:
            res = func({"symbol": "BTCUSDT", "timeframe": "1h"})
        except TypeError:
            res = func()
    except Exception as e:
        logger.error(f"Prompt function call failed for {prompt_name}: {e}")
        return None

    # Normalize to text
    try:
        if isinstance(res, dict):
            txt = res.get("prompt") or res.get("text") or ""
            return str(txt).strip()
        return str(res or "").strip()
    except Exception:
        return None


def _connect_db() -> sqlite3.Connection:
    return sqlite3.connect(str(DB_PATH))


def get_prompt_performance(prompt_name: str) -> Optional[PromptPerformance]:
    """Aggregate key metrics for a single prompt from backtests.db."""
    if not DB_PATH.exists():
        return None

    with _connect_db() as conn:
        c = conn.cursor()
        # Trades: wins/losses, avg realized pnl %, avg confidence, direction split
        c.execute(
            """
            SELECT outcome, realized_pnl_percent, COALESCE(confidence, 0.0), LOWER(direction)
            FROM trades
            WHERE prompt_name = ?
            """,
            (prompt_name,),
        )
        rows = c.fetchall()

        wins = sum(1 for r in rows if (r[0] or "").lower() == "win")
        losses = sum(1 for r in rows if (r[0] or "").lower() == "loss")
        total_trades = wins + losses
        # Calculate avg_pnl - filter for win/loss outcomes with non-None pnl values
        pnl_values = [float(r[1]) for r in rows if r[1] is not None and (r[0] or "").lower() in ("win", "loss")]
        avg_pnl = (sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0

        # Calculate avg_conf - filter for win/loss outcomes with non-None confidence values
        conf_values = [float(r[2]) for r in rows if r[2] is not None and (r[0] or "").lower() in ("win", "loss")]
        avg_conf = (sum(conf_values) / len(conf_values)) if conf_values else 0.0
        long_trades = sum(1 for r in rows if (r[3] or "") in ("long", "buy"))
        short_trades = sum(1 for r in rows if (r[3] or "") in ("short", "sell"))

        # Analyses: taken signals % (buy/sell vs total decisions)
        c.execute(
            """
            SELECT LOWER(COALESCE(recommendation, '')) FROM analyses WHERE prompt_name = ?
            """,
            (prompt_name,),
        )
        recs = [r[0] for r in c.fetchall()]
        total_decisions = len(recs)
        taken_decisions = sum(1 for v in recs if v in ("buy", "sell"))
        taken_pct = (taken_decisions / total_decisions * 100.0) if total_decisions > 0 else 0.0

        win_rate = (wins / total_trades) if total_trades > 0 else 0.0
        loss_rate = (losses / total_trades) if total_trades > 0 else 0.0

        perf_dict = {
            "prompt_name": prompt_name,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "loss_rate": loss_rate,
            "avg_pnl_percent": avg_pnl,
            "avg_confidence": avg_conf,
            "long_trades": long_trades,
            "short_trades": short_trades,
            "taken_signals_pct": taken_pct,
        }
        summary = (
            f"{total_trades} trades • Win rate {win_rate:.1%} • Avg PnL {avg_pnl:.2f}% • "
            f"Confidence {avg_conf:.2f} • Long/Short {long_trades}/{short_trades} • Taken {taken_pct:.1f}%"
        )
        perf_hash = _compute_hash(perf_dict)

        return PromptPerformance(
            prompt_name=prompt_name,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            loss_rate=loss_rate,
            avg_pnl_percent=avg_pnl,
            avg_confidence=avg_conf,
            long_trades=long_trades,
            short_trades=short_trades,
            taken_signals_pct=taken_pct,
            summary=summary,
            backtest_data_hash=perf_hash,
        )


def get_real_trade_performance(prompt_name: str) -> Optional[PromptPerformance]:
    """Get performance metrics from real trades in data/trading.db.

    Args:
        prompt_name: The prompt function name to filter by

    Returns:
        PromptPerformance object or None if no data found
    """
    # Consolidated database path: prototype/data/trading.db
    real_db_path = Path(__file__).parent.parent.parent / "data" / "trading.db"
    if not real_db_path.exists():
        logger.warning(f"Real trades database not found at {real_db_path}")
        return None

    try:
        conn = sqlite3.connect(str(real_db_path))
        cursor = conn.cursor()

        # Query trades joined with analysis_results to get prompt_id
        query = """
            SELECT
                t.id,
                t.symbol,
                t.side,
                t.pnl,
                t.entry_price,
                t.avg_exit_price,
                t.status,
                t.confidence,
                a.prompt_id
            FROM trades t
            INNER JOIN analysis_results a ON t.recommendation_id = a.id
            WHERE a.prompt_id = ? AND t.status = 'closed'
        """

        cursor.execute(query, (prompt_name,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            logger.info(f"No real trades found for prompt '{prompt_name}'")
            return None

        # Calculate metrics
        total_trades = len(rows)
        wins = sum(1 for r in rows if r[3] and float(r[3]) > 0)
        losses = sum(1 for r in rows if r[3] and float(r[3]) < 0)

        # Calculate PnL metrics
        pnl_values = [float(r[3]) for r in rows if r[3] is not None]
        total_pnl = sum(pnl_values) if pnl_values else 0.0
        avg_pnl = total_pnl / len(pnl_values) if pnl_values else 0.0

        # Calculate avg PnL percentage
        pnl_pct_values = []
        for r in rows:
            if r[3] and r[4]:  # pnl and entry_price
                pnl_pct = (float(r[3]) / float(r[4])) * 100 if float(r[4]) != 0 else 0
                pnl_pct_values.append(pnl_pct)
        avg_pnl_pct = sum(pnl_pct_values) / len(pnl_pct_values) if pnl_pct_values else 0.0

        # Calculate confidence
        conf_values = [float(r[7]) for r in rows if r[7] is not None]
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        # Count long vs short
        long_trades = sum(1 for r in rows if r[2] and r[2].lower() in ('buy', 'long'))
        short_trades = sum(1 for r in rows if r[2] and r[2].lower() in ('sell', 'short'))

        # Create summary
        summary = (
            f"Real trading performance for {prompt_name}:\n"
            f"- Total closed trades: {total_trades}\n"
            f"- Wins: {wins}, Losses: {losses}\n"
            f"- Total PnL: ${total_pnl:.2f}\n"
            f"- Avg PnL per trade: ${avg_pnl:.2f}\n"
            f"- Long/Short: {long_trades}/{short_trades}"
        )

        return PromptPerformance(
            prompt_name=prompt_name,
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=wins / total_trades if total_trades > 0 else 0.0,
            loss_rate=losses / total_trades if total_trades > 0 else 0.0,
            avg_pnl_percent=avg_pnl_pct,
            avg_confidence=avg_conf,
            long_trades=long_trades,
            short_trades=short_trades,
            taken_signals_pct=100.0,  # All real trades were taken
            summary=summary,
            backtest_data_hash="real_trades",
        )

    except Exception as e:
        logger.error(f"Error fetching real trade performance: {e}")
        return None


def _format_performance_md(pp: PromptPerformance, data_source: str = "backtest") -> str:
    """Format performance data as markdown.

    Args:
        pp: PromptPerformance object
        data_source: One of "backtest", "real_trades", or "both"
    """
    if data_source == "backtest":
        header = "## Backtest Performance Summary\n"
    elif data_source == "real_trades":
        header = "## Real Trading Performance Summary\n"
    else:
        header = "## Performance Summary\n"

    return (
        header +
        f"- Total trades: {pp.total_trades}\n"
        f"- Win rate: {pp.win_rate:.1%} | Loss rate: {pp.loss_rate:.1%}\n"
        f"- Realized P&L (avg %): {pp.avg_pnl_percent:.2f}%\n"
        f"- Avg confidence: {pp.avg_confidence:.2f}\n"
        f"- Long vs Short: {pp.long_trades}/{pp.short_trades}\n"
        f"- Taken trades %: {pp.taken_signals_pct:.1f}%\n"
        f"- Data source: {pp.backtest_data_hash}\n"
    )


def _split_output_section(md: str) -> Tuple[str, str]:
    """Return (md_without_output_section, output_section_md).

    Detects a section starting with a heading like '## OUTPUT FORMAT', '### OUTPUT FORMAT (JSON)',
    or '## OUTPUT REQUIREMENTS' (case-insensitive). The section spans until the next heading
    of same or higher level, or end of document.
    """
    try:
        pattern = re.compile(r"(?im)^\s{0,3}(#{1,6})\s*(OUTPUT\s+(FORMAT|REQUIREMENTS)[^\n]*)\s*$")
        m = pattern.search(md)
        if not m:
            return md, ""
        start = m.start()
        heading_hashes = m.group(1)
        level = len(heading_hashes)
        # Next heading of same or higher level (allow up to 3 leading spaces)
        next_heading = re.compile(rf"(?im)^\s{{0,3}}#{{1,{level}}}\s+")
        n = next_heading.search(md, m.end())
        end = n.start() if n else len(md)
        section = md[start:end].rstrip()
        before = md[:start].rstrip()
        after = md[end:].lstrip()
        merged = (before + ("\n\n" if before and after else "") + after).strip()
        return merged, section
    except Exception:
        # On any parsing error, fail open
        return md, ""



def _looks_incomplete(md: str) -> bool:
    """Heuristic to detect placeholder/incomplete content from the model.
    Flags phrases like 'same as original', 'rest of steps same', '[rest ...]', or heavy ellipses.
    """
    try:
        pattern = re.compile(r"(?i)(same\s+as\s+original|rest\s+of\s+.*same|\[rest[^\]]*\]|\bomitted\b|\u2026|^\s*\.{3,}\s*$)")
        return bool(pattern.search(md or ""))
    except Exception:
        return False


def _remove_output_section(md: str) -> str:
    return _split_output_section(md)[0]


def _extract_output_section(md: str) -> str:
    return _split_output_section(md)[1]


def generate_prompt_recommendations(
    prompt_name: str,
    extra_context: Optional[str] = None,
    data_source: str = "backtest"
) -> Tuple[AnthropicResponse, str, PromptPerformance]:
    """Orchestrate getting original prompt, performance, caching, and API call.

    Args:
        prompt_name: Name of the prompt to improve
        extra_context: Optional additional context or instructions for the AI
        data_source: One of "backtest", "real_trades", or "both"

    Returns: (response, original_prompt_md, performance)
    """
    original = get_original_prompt_text(prompt_name)
    if not original:
        raise RuntimeError(f"Original prompt text not found for '{prompt_name}'")
    original_output_section = _extract_output_section(original)

    # Strip CURRENT MARKET DATA section before sending to Anthropic (runtime-only placeholder)
    try:
        cmd_pattern = re.compile(r"(?im)^\s{0,3}(#{1,6})\s*CURRENT\s+MARKET\s+DATA\s*$")
        m = cmd_pattern.search(original)
        if m:
            start = m.start()
            level = len(m.group(1))
            next_heading = re.compile(rf"(?im)^\s{{0,3}}#{{1,{level}}}\s+")
            n = next_heading.search(original, m.end())
            end = n.start() if n else len(original)
            before = original[:start].rstrip()
            after = original[end:].lstrip()
            original_for_model = (before + ("\n\n" if before and after else "") + after).strip()
        else:
            original_for_model = original
    except Exception:
        original_for_model = original

    # Get performance data based on data_source
    perf_md_parts = []
    perf = None

    if data_source in ("backtest", "both"):
        perf = get_prompt_performance(prompt_name)
        if perf:
            perf_md_parts.append(_format_performance_md(perf, "backtest"))

    if data_source in ("real_trades", "both"):
        real_perf = get_real_trade_performance(prompt_name)
        if real_perf:
            perf_md_parts.append(_format_performance_md(real_perf, "real_trades"))
            if not perf:  # Use real_perf as primary if no backtest data
                perf = real_perf

    if not perf:
        raise RuntimeError("No performance data found (neither backtest nor real trades)")

    perf_md = "\n\n".join(perf_md_parts)

    # Cache key: prompt_name + backtest_data_hash + extra_context + data_source
    cache_key = _compute_hash({
        "prompt": prompt_name,
        "hash": perf.backtest_data_hash,
        "extra_context": extra_context or "",
        "data_source": data_source
    })
    cache = _load_cache()
    if cache_key in cache:
        try:
            cached = cache[cache_key]
            data = cached.get("data") or {}
            # Normalize cached data to ensure lists render as markdown
            ar = AnthropicClient._normalize_response(data)  # type: ignore[attr-defined]

            # Post-process with original output section same as fresh calls
            improved_no_output = _remove_output_section(ar.improved_prompt or "")
            final_improved = improved_no_output.strip()
            if original_output_section.strip():
                if final_improved:
                    final_improved += "\n\n" + original_output_section.strip()
                else:
                    final_improved = original_output_section.strip()
            ar.improved_prompt = final_improved
            try:
                data_out = dict(ar.raw_json) if isinstance(ar.raw_json, dict) else {}
                data_out["improved_prompt"] = final_improved
            except Exception:
                data_out = {"improved_prompt": final_improved}
            ar.raw_json = data_out
            # If cached result looks incomplete (placeholders), bypass cache and fetch fresh
            if not _looks_incomplete(final_improved):
                return ar, original, perf
            # else fall through to make a fresh API call below
        except Exception:
            # ignore malformed cache
            pass

    # Use longer timeout (60s) for complex analysis requests with large prompts and backtest data
    client = AnthropicClient(timeout=60.0)
    ar = client.generate_recommendations(original_prompt_md=original_for_model, performance_context_md=perf_md, extra_context=extra_context)

    # Post-process: ensure improved prompt excludes any output format section,
    # and then append the original prompt's OUTPUT FORMAT/REQUIREMENTS section.
    improved_no_output = _remove_output_section(ar.improved_prompt or "")
    final_improved = improved_no_output.strip()
    if original_output_section.strip():
        if final_improved:
            final_improved += "\n\n" + original_output_section.strip()
        else:
            final_improved = original_output_section.strip()

    # Update the response and raw_json so cache+UI see the merged version
    ar.improved_prompt = final_improved
    try:
        data_out = dict(ar.raw_json) if isinstance(ar.raw_json, dict) else {}
        data_out["improved_prompt"] = final_improved
    except Exception:
        data_out = {"improved_prompt": final_improved}
    ar.raw_json = data_out

    # store cache
    cache[cache_key] = {
        "ts": int(time.time()),  # type: ignore[name-defined]
        "prompt_name": prompt_name,
        "backtest_hash": perf.backtest_data_hash,
        "data": ar.raw_json,
    }
    _save_cache(cache)

    return ar, original, perf


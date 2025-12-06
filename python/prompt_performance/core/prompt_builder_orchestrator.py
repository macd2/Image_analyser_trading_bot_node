"""
Intelligent Prompt Builder Orchestrator

Seed -> Backtest -> Improve -> Rank -> Early-stop -> Holdout (skeleton)

This orchestrator wires together:
- model discovery (for UI selection)
- prompt templates (seed/improve)
- LLM provider (with JSON repair)
- dataset sampler (anti-overfitting)
- backtest adapter (evaluate prompt text on sampled images)

Network/API calls are not executed here; the LLM step is pluggable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast
from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone

from .dataset_sampler import DatasetSampler, SamplerConfig
from .llm_providers import call_model, Provider
from .intelligent_prompts import PROMPT_VERSION

# Reuse analyzer + simulator like in backtest_with_images
from trading_bot.core.analyzer import ChartAnalyzer
from prompt_performance.core.trade_simulator import TradeSimulator
from prompt_performance.core.candle_fetcher import CandleFetcher
from trading_bot.config.settings_v2 import Config
from .backtest_store import BacktestStore


@dataclass
class Candidate:
    provider: str
    model: str
    prompt_text: str
    signature: str  # hash of prompt_text
    iteration: int


@dataclass
class EvalResult:
    candidate_sig: str
    metrics: Dict[str, Any]


class BacktestAdapter:
    """Evaluate either a prompt_text on images OR a single normalized signal on its image.

    This keeps backward compatibility while enabling the iterative builder loop.
    """

    def __init__(self) -> None:
        # Load config from project root (same as other components). Fallback to default path if not found.
        root_cfg = Path(__file__).parent.parent.parent / "config.yaml"
        self.config = Config.from_yaml(str(root_cfg) if root_cfg.exists() else "config.yaml")
        self.analyzer = ChartAnalyzer(None, self.config)  # Analyzer knows how to handle custom_prompt_data
        self.simulator = TradeSimulator()
        self.candles = CandleFetcher(self.config)

    @staticmethod
    def _compute_sharpe(returns_dec: List[float]) -> float:
        """Compute simple Sharpe based on per-trade decimal returns (no annualization)."""
        n = len(returns_dec)
        if n < 2:
            return 0.0
        mean = sum(returns_dec) / n
        var = sum((r - mean) ** 2 for r in returns_dec) / (n - 1)
        if var <= 0:
            return 0.0
        std = var ** 0.5
        return float(mean / std) if std > 0 else 0.0

    @staticmethod
    def _compute_max_drawdown(returns_dec: List[float]) -> float:
        """Compute max drawdown from equity curve built by compounding decimal returns.
        Returns a positive fraction (e.g., 0.2 for 20%)."""
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns_dec:
            equity *= (1.0 + float(r))
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak if peak > 0 else 0.0
            if drawdown > max_dd:
                max_dd = drawdown
        return float(max_dd)

    def _prompt_data(self, prompt_text: str, name: str) -> Dict[str, Any]:
        return {
            "prompt": prompt_text,
            "version": {"version": PROMPT_VERSION, "name": name},
        }

    def evaluate(self, images: List[Any], prompt_text: str, *, name: str) -> Dict[str, Any]:
        trades: List[Dict[str, Any]] = []
        for info in images:
            pd = self._prompt_data(prompt_text, name)
            res = self.analyzer.analyze_chart_with_assistant(
                image_path=str(info.filepath),
                target_timeframe=info.timeframe,
                custom_prompt_data=pd,
                skip_market_data=True,
            )
            if res.get("error") or res.get("skipped"):
                continue
            # Inject image timestamp metadata to align simulation start
            try:
                res["image_timestamp_ms"] = getattr(info, "timestamp_ms", None)
                ts = getattr(info, "timestamp", None)
                res["timestamp"] = ts.isoformat() if ts is not None else None
            except Exception:
                pass
            # TradeSimulator expects structured JSON already inside result
            # simulate_trade_from_analysis may not exist in older builds; fall back if needed
            sim = None
            try:
                sim = getattr(self.simulator, "simulate_trade_from_analysis")(  # type: ignore[attr-defined]
                    analysis_result=res,
                    symbol=info.symbol,
                    timeframe=info.timeframe,
                    candles_fetcher=self.candles,
                )
            except AttributeError:
                # Fallback path: build minimal record and use CandleFetcher + simulate_trade
                candles = []
                try:
                    ts_ms = getattr(info, "timestamp_ms", None)
                    if ts_ms is not None and hasattr(self.candles, "get_candles_for_simulation"):
                        candles = self.candles.get_candles_for_simulation(info.symbol, info.timeframe, ts_ms)
                    else:
                        candles = self.candles.get_candles(info.symbol, info.timeframe)  # type: ignore[attr-defined]
                except Exception:
                    candles = []

                # If no candles available, try to fetch and cache them from API
                if not candles and ts_ms is not None:
                    # Try to fetch and cache missing candles starting from image timestamp
                    self.candles.fetch_and_cache_candles(
                        symbol=info.symbol,
                        timeframe=info.timeframe,
                        earliest_timestamp=ts_ms
                    )
                    # Retry after fetch
                    if hasattr(self.candles, "get_candles_for_simulation"):
                        candles = self.candles.get_candles_for_simulation(info.symbol, info.timeframe, ts_ms)
                    else:
                        candles = self.candles.get_candles(info.symbol, info.timeframe)  # type: ignore[attr-defined]
                ts_rec = getattr(info, "timestamp", None)
                rec = {
                    "recommendation": (res.get("recommendation") or res.get("direction") or "").lower(),
                    "entry_price": res.get("entry_price"),
                    "stop_loss": res.get("stop_loss"),
                    "take_profit": res.get("take_profit"),
                    "timestamp": ts_rec.isoformat() if ts_rec is not None else res.get("timestamp"),
                }
                try:
                    sim = self.simulator.simulate_trade(rec, candles)
                except Exception:
                    sim = None
            if sim:
                trades.append(sim)
        # Aggregate metrics
        total = len(trades)
        wins = sum(1 for t in trades if (str(t.get("outcome", "")).lower() == "win" or bool(t.get("is_profitable"))))
        win_rate = (wins / total) if total else 0.0
        # Use realized_pnl_percent if available; treat missing as 0
        returns_pct = [float(t.get("realized_pnl_percent") or 0.0) for t in trades]
        returns_dec = [r / 100.0 for r in returns_pct]
        pnl_pct = float(sum(returns_pct))
        sharpe = self._compute_sharpe(returns_dec)
        max_dd = self._compute_max_drawdown(returns_dec)
        return {
            "trade_count": total,
            "win_rate": win_rate,
            "pnl_pct": pnl_pct,
            "sharpe": sharpe,
            "max_dd": max_dd,
        }

    def evaluate_single_signal(self, symbol: str, timeframe: str, signal: Dict[str, Any], start_timestamp_ms: Optional[int] = None, *, return_details: bool = False) -> Dict[str, Any]:
        """Simulate one trade from a normalized signal starting at the image timestamp for that timeframe/symbol.
        Returns 0-trade metrics if prices are rule-based or unavailable.
        If return_details=True, also includes 'simulation_details' with full trade info.
        """
        # Map action to direction if needed
        direction = (signal.get("action") or signal.get("direction") or "").lower()
        # Prefer price values; if rules, we cannot evaluate numerically -> skip
        entry = signal.get("entry") or {}
        sl = signal.get("stop_loss") or {}
        tps = signal.get("take_profits") or []
        try:
            entry_val = entry.get("price") if isinstance(entry, dict) else entry
            entry_price = float(entry_val) if entry_val is not None else None
        except Exception:
            entry_price = None
        try:
            sl_val = sl.get("price") if isinstance(sl, dict) else sl
            stop_price = float(sl_val) if sl_val is not None else None
        except Exception:
            stop_price = None
        tp_price = None
        # Pick first take profit price if available
        if isinstance(tps, list) and tps:
            tp0 = tps[0]
            try:
                tp_val = tp0.get("price") if isinstance(tp0, dict) else tp0
                tp_price = float(tp_val) if tp_val is not None else None
            except Exception:
                tp_price = None
        if not (entry_price and stop_price and tp_price and direction in ("long", "short")):
            result = {"trade_count": 0, "win_rate": 0.0, "pnl_pct": 0.0, "sharpe": 0.0, "max_dd": 0.0}
            if return_details:
                result["simulation_details"] = None
            return result
        # Fetch candles from image timestamp forward and simulate
        try:
            if start_timestamp_ms is not None and hasattr(self.candles, "get_candles_for_simulation"):
                candles = self.candles.get_candles_for_simulation(symbol, timeframe, start_timestamp_ms)
            else:
                candles = self.candles.get_candles(symbol, timeframe)  # type: ignore[attr-defined]
        except Exception:
            candles = []

        # If no candles available, try to fetch and cache them from API
        if not candles and start_timestamp_ms is not None:
            # Try to fetch and cache missing candles starting from image timestamp
            self.candles.fetch_and_cache_candles(
                symbol=symbol,
                timeframe=timeframe,
                earliest_timestamp=start_timestamp_ms
            )
            # Retry after fetch
            if hasattr(self.candles, "get_candles_for_simulation"):
                candles = self.candles.get_candles_for_simulation(symbol, timeframe, start_timestamp_ms)
            else:
                candles = self.candles.get_candles(symbol, timeframe)  # type: ignore[attr-defined]

        # If still no candles, return 0-trade metrics (no fallback/synthesis)
        if not candles:
            result = {"trade_count": 0, "win_rate": 0.0, "pnl_pct": 0.0, "sharpe": 0.0, "max_dd": 0.0}
            if return_details:
                result["simulation_details"] = None
            return result
        # Map direction to recommendation format expected by TradeSimulator
        # TradeSimulator expects 'buy'/'sell', not 'long'/'short'
        if direction == "long":
            recommendation = "buy"
        elif direction == "short":
            recommendation = "sell"
        else:
            recommendation = "hold"

        rec = {
            "recommendation": recommendation,
            "entry_price": entry_price,
            "stop_loss": stop_price,
            "take_profit": tp_price,
            "timestamp": start_timestamp_ms,
        }
        try:
            sim = self.simulator.simulate_trade(rec, candles)
        except Exception:
            sim = None
        if not sim:
            result = {"trade_count": 0, "win_rate": 0.0, "pnl_pct": 0.0, "sharpe": 0.0, "max_dd": 0.0}
            if return_details:
                result["simulation_details"] = None
            return result
        # Compute metrics for a single trade
        total = 1
        win = 1 if (str(sim.get("outcome", "")).lower() == "win" or bool(sim.get("is_profitable"))) else 0
        win_rate = float(win)
        pnl_pct = float(sim.get("realized_pnl_percent") or 0.0)
        returns_dec = [pnl_pct / 100.0]
        sharpe = self._compute_sharpe(returns_dec)
        max_dd = self._compute_max_drawdown(returns_dec)
        result = {"trade_count": total, "win_rate": win_rate, "pnl_pct": pnl_pct, "sharpe": sharpe, "max_dd": max_dd}
        if return_details:
            result["simulation_details"] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp_ms": start_timestamp_ms,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": stop_price,
                "take_profit": tp_price,
                "outcome": sim.get("outcome"),
                "exit_price": sim.get("exit_price"),
                "realized_pnl_percent": sim.get("realized_pnl_percent"),
                "duration_candles": sim.get("duration_candles"),
                "achieved_rr": sim.get("achieved_rr"),
            }
        return result


def _sig(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class PromptOptimizer:
    def __init__(
        self,
        charts_dir: Path,
        symbols: List[str],
        timeframes: List[str],
        min_offset: int = 100,
        *,
        primary_metric: str = "pnl_pct",
        patience: int = 0,
        backtest_images_per_iteration: int = 5,
        store: Optional[BacktestStore] = None,
        dry_run: bool = False
    ) -> None:
        self.sampler = DatasetSampler(SamplerConfig(symbols=symbols, timeframes=timeframes, charts_dir=charts_dir, min_offset=min_offset))
        self.bt = BacktestAdapter()
        self.primary_metric = primary_metric
        self.patience = max(0, int(patience))
        self.backtest_images_per_iteration = max(1, int(backtest_images_per_iteration))
        self.store = store or BacktestStore()
        self.dry_run = bool(dry_run)

    @staticmethod
    def _append_output_requirements_tail(prompt_text: str) -> str:
        """Append the OUTPUT REQUIREMENTS block from analyzer_prompt.get_analyzer_prompt
        to ensure structured JSON output, unless the text already contains an output
        section. Keeps prompt lightweight and generic.
        """
        try:
            if any(h in prompt_text for h in ("## OUTPUT REQUIREMENTS", "### OUTPUT FORMAT", "### OUTPUT (JSON)")):
                return prompt_text
            # Import here to avoid heavy import at module load
            from trading_bot.core.prompts.analyzer_prompt import get_analyzer_prompt as _ap_fn  # type: ignore
            # Build once with dummy market_data to get full text, then slice tail
            md = {"symbol": "SYMBOL", "timeframe": "1h", "last_price": "N/A", "price_change_24h_percent": "N/A",
                  "high_24h": "N/A", "low_24h": "N/A", "funding_rate": "N/A", "long_short_ratio": "N/A"}
            ap = _ap_fn(md)
            base = str((ap or {}).get("prompt") or "")
            idx = base.find("## OUTPUT REQUIREMENTS")
            if idx == -1:
                return prompt_text  # fallback: do not modify if header not found
            tail = base[idx:].strip()
            return (prompt_text.rstrip() + "\n\n" + tail + "\n").strip()
        except Exception:
            return prompt_text

    @staticmethod
    def _get_analyzer_prompt_head() -> str:
        """Return the analyzer prompt header (without the OUTPUT REQUIREMENTS tail).
        Falls back to a generic, reusable crypto prompt if analyzer prompt is unavailable.
        """
        try:
            from trading_bot.core.prompts.analyzer_prompt import get_analyzer_prompt as _ap_fn  # type: ignore
            md = {"symbol": "SYMBOL", "timeframe": "1h", "last_price": "N/A", "price_change_24h_percent": "N/A",
                  "high_24h": "N/A", "low_24h": "N/A", "funding_rate": "N/A", "long_short_ratio": "N/A"}
            ap = _ap_fn(md)
            base = str((ap or {}).get("prompt") or "")
            idx = base.find("## OUTPUT REQUIREMENTS")
            return base[:idx].rstrip() if idx != -1 else base.strip()
        except Exception:
            # Provider-agnostic baseline analyzer-style header
            return (
                "Analyze the crypto candlestick chart. Identify trend regime, key levels, and a concrete trade plan "
                "with entry, stop loss, and 1–3 take profits. Be concise and robust across symbols and timeframes."
            )

    @staticmethod
    def _sanitize_prompt_head(prompt_text: str, symbol: str, timeframe: str) -> str:
        """Make prompt head generic by removing symbol/timeframe specifics from the first lines.
        Conservative: only strips exact symbol and timeframe tokens if present.
        """
        try:
            head = prompt_text
            # Remove exact occurrences like "AAVEUSDT" and "1h" within the first line/sentence
            for tok in [symbol, timeframe]:
                if tok and tok in head:
                    head = head.replace(tok, "").replace("  ", " ").strip()
            # Common connectors
            head = head.replace("Analyze the  candlestick", "Analyze the candlestick")
            # Avoid double spaces
            while "  " in head:
                head = head.replace("  ", " ")
            return head
        except Exception:
            return prompt_text

    def seed_candidates(self, provider_models: List[Tuple[str, str]], seed_image_payload: Dict[str, Any]) -> List[Candidate]:
        out: List[Candidate] = []
        for provider, model in provider_models:
            # Build seed messages and call provider
            _, _, raw = call_model(cast(Provider, provider), model, "seed", seed_image_payload)
            # For seed, we just need a JSON to be parsable; embed short strategy in prompt_text
            # Construct a minimal prompt from normalized content (if available)
            prompt_text = raw or ""
            sig = _sig(prompt_text)
            out.append(Candidate(provider=provider, model=model, prompt_text=prompt_text, signature=sig, iteration=0))
        return out

    def improve_candidate(self, cand: Candidate, payload: Dict[str, Any]) -> Candidate:
        _, _, raw = call_model(cast(Provider, cand.provider), cand.model, "improve", payload)
        text = raw or cand.prompt_text
        return Candidate(provider=cand.provider, model=cand.model, prompt_text=text, signature=_sig(text), iteration=cand.iteration + 1)

    def _sample_backtest_images(self, iteration_index: int) -> List[Any]:
        """Sample images for backtesting, respecting data selection config."""
        # Get all available images from the sampler
        all_imgs = self.sampler._list_images()
        buckets = self.sampler._group_by_key(all_imgs)

        sample: List[Any] = []
        images_per_bucket = max(1, self.backtest_images_per_iteration // len(buckets)) if buckets else 1

        for key, arr in buckets.items():
            # Apply offset per key (same as sampler logic)
            eligible = [i for idx, i in enumerate(arr) if idx >= self.sampler.cfg.min_offset]
            # Exclude previously used images
            eligible = [i for i in eligible if i.filepath.name not in self.sampler._used]
            if not eligible:
                continue

            # Sample up to images_per_bucket without marking as used
            # Use a high offset to avoid overlap with signal generation images
            n = min(images_per_bucket, len(eligible))
            # Take from the middle of eligible pool to avoid newest/oldest
            start_idx = min(10, len(eligible) // 4) if len(eligible) > 20 else 0
            choices = eligible[start_idx:start_idx + n]
            sample.extend(choices)

        # Limit to configured number and return
        return sample[:self.backtest_images_per_iteration]

    def _aggregate_backtest_metrics(self, backtest_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate metrics across all backtest images."""
        if not backtest_results:
            return {"trade_count": 0, "win_rate": 0.0, "pnl_pct": 0.0, "sharpe": 0.0, "max_dd": 0.0}

        total_trades = sum(r["metrics"].get("trade_count", 0) for r in backtest_results)
        total_wins = sum(r["metrics"].get("trade_count", 0) * r["metrics"].get("win_rate", 0.0) for r in backtest_results)
        win_rate = (total_wins / total_trades) if total_trades > 0 else 0.0

        total_pnl = sum(r["metrics"].get("pnl_pct", 0.0) for r in backtest_results)

        # Aggregate sharpe and max_dd (simple average)
        avg_sharpe = sum(r["metrics"].get("sharpe", 0.0) for r in backtest_results) / len(backtest_results)
        avg_max_dd = sum(r["metrics"].get("max_dd", 0.0) for r in backtest_results) / len(backtest_results)

        return {
            "trade_count": total_trades,
            "win_rate": win_rate,
            "pnl_pct": total_pnl,
            "sharpe": avg_sharpe,
            "max_dd": avg_max_dd,
        }

    def _create_metrics_summary(self, backtest_results: List[Dict[str, Any]], aggregated: Dict[str, Any]) -> str:
        """Create a concise summary of backtest results for the model."""
        lines = ["Backtest Results:"]

        # Per symbol/timeframe breakdown
        for r in backtest_results:
            m = r["metrics"]
            lines.append(
                f"{r['symbol']}, {r['timeframe']}: "
                f"PnL={m.get('pnl_pct', 0.0):.2f}%, "
                f"WR={m.get('win_rate', 0.0)*100:.1f}%, "
                f"Trades={m.get('trade_count', 0)}"
            )

        # Overall summary
        lines.append("")
        lines.append(
            f"Overall: WinRate={aggregated['win_rate']*100:.1f}%, "
            f"MaxDD={aggregated['max_dd']*100:.1f}%, "
            f"PnL={aggregated['pnl_pct']:.2f}%, "
            f"Sharpe={aggregated['sharpe']:.2f}"
        )

        return "\n".join(lines)

    def _select_top(self, evals: List[EvalResult]) -> Optional[str]:
        if not evals:
            return None
        # Rank by primary metric, then win_rate, then trade_count, then pnl_pct as tie-breaker
        pm = self.primary_metric
        def score(ev: EvalResult) -> Tuple[float, float, float, float]:
            m = ev.metrics
            # Primary metric direction: for max_dd lower is better; others higher is better
            primary_val = float(m.get(pm, 0.0))
            if pm in ("max_dd",):
                primary_val = -primary_val
            return (
                primary_val,
                float(m.get("win_rate", 0.0)),
                float(m.get("trade_count", 0.0)),
                float(m.get("pnl_pct", 0.0)),
            )
        evals_sorted = sorted(evals, key=score, reverse=True)
        return evals_sorted[0].candidate_sig if evals_sorted else None

    def run_iteration(self, iteration_index: int, candidates: List[Candidate]) -> Tuple[List[EvalResult], List[Candidate]]:
        images = self.sampler.next_iteration(iteration_index)
        evals: List[EvalResult] = []
        for c in candidates:
            name = f"cand_{c.signature}" + ("-dry-run" if self.dry_run else "")
            metrics = self.bt.evaluate(images, c.prompt_text, name=name)
            evals.append(EvalResult(candidate_sig=c.signature, metrics=metrics))
        best_sig = self._select_top(evals)
        best = [c for c in candidates if c.signature == best_sig]
        return evals, best or candidates[:1]

    def optimize(self, provider_models: List[Tuple[str, str]], max_iters: int = 3, progress: Optional[Any] = None) -> Dict[str, Any]:
        # Create optimizer run in DB (skip when dry_run)
        cfg_obj = {
            "symbols": self.sampler.cfg.symbols,
            "timeframes": self.sampler.cfg.timeframes,
            "min_offset": self.sampler.cfg.min_offset,
            "growth": self.sampler.cfg.growth,
            "provider_models": provider_models,
            "primary_metric": self.primary_metric,
            "max_iters": max_iters,
            "patience": self.patience,
            "backtest_images_per_iteration": self.backtest_images_per_iteration,
        }
        run_id: Optional[int] = None
        if not self.dry_run and self.store:
            run_id = self.store.opt_create_run(
                started_at=datetime.now(timezone.utc).isoformat(),
                primary_metric=self.primary_metric,
                config_json=json.dumps(cfg_obj),
            )

        # Per-provider state
        states = [
            {"provider": p, "model": m, "prompt_text": "", "signature": "", "last_metrics": {}}
            for (p, m) in provider_models
        ]
        history: List[Dict[str, Any]] = []
        best_global = {"score": float("-inf"), "prompt": "", "sig": ""}
        no_improve = 0

        for it in range(max_iters):
            iter_id: Optional[int] = None
            if not self.dry_run and self.store and run_id is not None:
                iter_id = self.store.opt_start_iteration(run_id, idx=it, started_at=datetime.now(timezone.utc).isoformat())

            # 1) Select one image for signal generation (first image from iteration)
            imgs = self.sampler.next_iteration(it)
            if not imgs:
                break
            img = imgs[0]

            # 1b) Sample additional images for backtesting (respecting data selection config)
            backtest_imgs = self._sample_backtest_images(it)

            if progress:
                try:
                    progress({"event": "iteration_start", "iteration": it, "image": Path(str(img.filepath)).name, "backtest_images": len(backtest_imgs)})
                except Exception:
                    pass

            # 2) For each provider/model: get signal from image, backtest, then improve prompt
            evals: List[EvalResult] = []
            per_cand_records: List[Dict[str, Any]] = []
            for st in states:
                # 2a) Get signal JSON from image (always send image + current prompt)
                prev_prompt = st["prompt_text"]
                # Encode image as base64 for API
                import base64
                abs_image_path = Path(img.filepath).resolve()
                with open(abs_image_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")

                if it == 0:
                    # First iteration: seed with image only
                    kind = "seed"
                    payload = {
                        "symbol": img.symbol,
                        "timeframe": img.timeframe,
                        "image": {"base64": image_b64, "media_type": "image/png"},
                    }
                else:
                    # Subsequent iterations: send image + improved prompt from previous iteration
                    # Use "seed" kind but include the improved prompt in payload
                    kind = "seed"
                    payload = {
                        "symbol": img.symbol,
                        "timeframe": img.timeframe,
                        "image": {"base64": image_b64, "media_type": "image/png"},
                        "analyzer_prompt": prev_prompt or "",
                    }

                norm, errs, raw = call_model(st["provider"], st["model"], kind, payload)

                # Store raw response and errors for debugging
                model_raw_response = raw
                model_errors = errs

                # Handle rate limit / quota errors: abort run and do not proceed
                if errs:
                    err_text = "; ".join(map(str, errs)).lower()
                    if ("429" in err_text) or ("quota" in err_text) or ("rate limit" in err_text):
                        if progress:
                            try:
                                progress({
                                    "event": "rate_limited",
                                    "iteration": it,
                                    "provider": st["provider"],
                                    "model": st["model"],
                                    "error": errs[0] if errs else "rate_limited",
                                })
                            except Exception:
                                pass
                        # Close iteration/run if created, then return early
                        if iter_id is not None and not self.dry_run and self.store and run_id is not None:
                            try:
                                self.store.opt_complete_iteration(iter_id, finished_at=datetime.now(timezone.utc).isoformat())
                            except Exception:
                                pass
                        if not self.dry_run and self.store and run_id is not None:
                            try:
                                self.store.opt_complete_run(run_id, finished_at=datetime.now(timezone.utc).isoformat())
                            except Exception:
                                pass
                        return {
                            "success": False,
                            "error": "rate_limited",
                            "message": errs[0] if errs else "rate limited",
                            "iterations": len(history),
                            "history": history,
                            "winner": "",
                            "run_id": run_id,
                            "primary_metric": self.primary_metric,
                        }
                    else:
                        # Non-rate-limit errors: log but continue
                        if progress:
                            try:
                                progress({
                                    "event": "model_error",
                                    "iteration": it,
                                    "provider": st["provider"],
                                    "model": st["model"],
                                    "errors": errs,
                                    "raw_response_length": len(raw),
                                })
                            except Exception:
                                pass

                signal = norm or {}

                # Extract the analyzer prompt head from model's JSON (no tail needed)
                prompt_used = signal.get("prompt_used") or ""
                invalid_prompt_used = (not isinstance(prompt_used, str)) or (not prompt_used.strip()) or prompt_used.strip().startswith(("{", "["))
                if invalid_prompt_used:
                    if progress:
                        try:
                            progress({
                                "event": "diagnostic",
                                "iteration": it,
                                "provider": st["provider"],
                                "model": st["model"],
                                "reason": f"missing_or_invalid_prompt_used_from_{kind}",
                            })
                        except Exception:
                            pass
                    prompt_used = ""
                else:
                    prompt_used = self._sanitize_prompt_head(prompt_used, img.symbol, img.timeframe)

                if progress:
                    try:
                        progress({
                            "event": "signal_generated",
                            "iteration": it,
                            "provider": st["provider"],
                            "model": st["model"],
                            "keys": list(signal.keys()),
                            "source": kind,
                        })
                    except Exception:
                        pass

                # 2b) Evaluate the prompt on backtest images by generating a NEW signal for EACH image
                # This tests the PROMPT's ability to generate good signals across different market conditions
                backtest_results = []
                backtest_details = []  # Store detailed trade info for each image
                for bt_img in backtest_imgs:
                    try:
                        # Generate a NEW signal for THIS specific backtest image using the SAME prompt
                        # Encode backtest image as base64
                        import base64
                        abs_bt_image_path = Path(bt_img.filepath).resolve()
                        with open(abs_bt_image_path, "rb") as f:
                            bt_image_b64 = base64.b64encode(f.read()).decode("utf-8")

                        # Call model with the prompt to generate a signal specific to this image
                        bt_payload = {
                            "symbol": bt_img.symbol,
                            "timeframe": bt_img.timeframe,
                            "image": {"base64": bt_image_b64, "media_type": "image/png"},
                            "analyzer_prompt": prompt_used or "",  # Use the same prompt
                        }
                        bt_signal, bt_errs, bt_raw = call_model(st["provider"], st["model"], "seed", bt_payload)

                        # If signal generation failed, skip this backtest image
                        if not bt_signal or bt_errs:
                            continue

                        # Evaluate this NEW signal on this specific image
                        start_ms = getattr(bt_img, 'timestamp_ms', None)
                        bt_metrics = self.bt.evaluate_single_signal(
                            symbol=bt_img.symbol,
                            timeframe=bt_img.timeframe,
                            signal=bt_signal,  # Use the NEW signal generated for THIS image
                            start_timestamp_ms=start_ms,
                            return_details=True
                        )
                        backtest_results.append({
                            "symbol": bt_img.symbol,
                            "timeframe": bt_img.timeframe,
                            "metrics": bt_metrics,
                        })
                        # Extract and store simulation details
                        sim_details = bt_metrics.get("simulation_details")
                        if sim_details:
                            backtest_details.append({
                                "image_filename": bt_img.filepath.name if hasattr(bt_img.filepath, 'name') else str(bt_img.filepath),
                                **sim_details
                            })
                    except Exception:
                        pass

                # Aggregate metrics across all backtest images
                metrics = self._aggregate_backtest_metrics(backtest_results)
                metrics_summary = self._create_metrics_summary(backtest_results, metrics)

                if progress:
                    try:
                        progress({"event": "metrics", "iteration": it, "provider": st["provider"], "model": st["model"], "metrics": metrics, "images_evaluated": len(backtest_imgs)})
                    except Exception:
                        pass

                # 3) Persist candidate for this iteration
                sig_eval = _sig(prompt_used)
                if not self.dry_run and self.store and run_id is not None:
                    try:
                        self.store.opt_add_candidate(
                            run_id,
                            provider=st["provider"],
                            model=st["model"],
                            signature=sig_eval,
                            iteration=it,
                            prompt_text=prompt_used,
                        )
                    except Exception:
                        pass

                evals.append(EvalResult(candidate_sig=sig_eval, metrics=metrics))
                _fname2 = Path(str(img.filepath)).name
                per_cand_records.append({
                    "provider": st["provider"],
                    "model": st["model"],
                    "signature": sig_eval,
                    "prompt_used": prompt_used,
                    "metrics": metrics,
                    "image_filename": _fname2,
                })


                # 2c) Now improve the prompt based on backtest metrics summary
                # Skip improve on last iteration (no point improving if we won't test it)
                improved_prompt = ""
                if prompt_used and it < max_iters - 1:
                    improve_payload = {
                        "candidate_prompt_text": prompt_used,
                        "metrics_summary": metrics_summary,  # Use detailed summary instead of just aggregated metrics
                        "symbols": self.sampler.cfg.symbols,
                        "timeframes": self.sampler.cfg.timeframes,
                        "primary_metric": self.primary_metric,
                    }
                    improve_norm, _, _ = call_model(cast(Provider, st["provider"]), st["model"], "improve", improve_payload)
                    if improve_norm and isinstance(improve_norm, dict):
                        improved_prompt = improve_norm.get("prompt_used") or ""
                        if improved_prompt and isinstance(improved_prompt, str) and improved_prompt.strip():
                            improved_prompt = self._sanitize_prompt_head(improved_prompt, img.symbol, img.timeframe)
                        else:
                            improved_prompt = ""

                # Persist eval including both prompts, errors, raw response, and backtest details
                if not self.dry_run and self.store and run_id is not None:
                    try:
                        metrics_payload = {
                            "metrics": metrics,
                            "signal": signal,
                            "prompt_used": prompt_used,
                            "improved_prompt": improved_prompt,
                            "model_errors": model_errors,
                            "model_raw_response": model_raw_response[:5000] if model_raw_response else "",  # Limit size
                            "backtest_details": backtest_details,  # Add detailed trade results
                            "ts": datetime.now(timezone.utc).isoformat(),
                        }
                        _fname = Path(str(img.filepath)).name
                        self.store.opt_add_eval(
                            run_id,
                            iteration=it,
                            candidate_sig=sig_eval,
                            metrics_json=json.dumps(metrics_payload),
                            image_filename=_fname,
                            assistant_model=st["model"],
                        )
                    except Exception:
                        pass

                # Stash improved prompt for next iteration (or keep current if improve failed)
                st["prompt_text"] = improved_prompt if improved_prompt else prompt_used
                st["signature"] = _sig(st["prompt_text"])
                st["last_metrics"] = metrics
                per_cand_records[-1]["prompt_text"] = st["prompt_text"]
                per_cand_records[-1]["improved_prompt"] = improved_prompt

            if iter_id is not None and not self.dry_run and self.store and run_id is not None:
                self.store.opt_complete_iteration(iter_id, finished_at=datetime.now(timezone.utc).isoformat())
            if progress:
                try:
                    progress({"event": "iteration_persisted", "iteration": it})
                except Exception:
                    pass

            # 4) Rank prompts for this iteration and track convergence
            pm = self.primary_metric
            def score(ev: EvalResult) -> Tuple[float, float, float, float]:
                m = ev.metrics
                primary_val = float(m.get(pm, 0.0))
                if pm in ("max_dd",):
                    primary_val = -primary_val
                return (
                    primary_val,
                    float(m.get("win_rate", 0.0)),
                    float(m.get("trade_count", 0.0)),
                    float(m.get("pnl_pct", 0.0)),
                )
            if evals:
                best_ev = sorted(evals, key=score, reverse=True)[0]
                best_val = score(best_ev)[0]
                if best_val > best_global["score"]:
                    best_global["score"] = best_val
                    # Prefer the evaluated prompt text for the winning signature
                    best_rec = next((r for r in per_cand_records if r.get("signature") == best_ev.candidate_sig), None)
                    if best_rec:
                        best_global["prompt"] = best_rec.get("prompt_used") or best_global["prompt"]
                        best_global["sig"] = best_ev.candidate_sig
                    else:
                        # Fallback: try to resolve via current states (may reflect improved-next prompts)
                        best_state = next((s for s in states if s["signature"] == best_ev.candidate_sig), None)
                        if best_state:
                            best_global["prompt"] = best_state["prompt_text"]
                            best_global["sig"] = best_state["signature"]
                    no_improve = 0
                else:
                    no_improve += 1
            else:
                best_val = float("-inf")
                no_improve += 1
            if progress:
                try:
                    progress({"event": "iteration_ranked", "iteration": it, "best_val": best_val})
                except Exception:
                    pass

            history.append({
                "iteration": it,
                "image_filename": Path(str(img.filepath)).name,
                "candidates": per_cand_records,
                "best_val": best_val,
            })

            if it == max_iters - 1:
                break
            if self.patience and no_improve >= self.patience:
                break

        if not self.dry_run and self.store and run_id is not None:
            self.store.opt_complete_run(run_id, finished_at=datetime.now(timezone.utc).isoformat())
        return {
            "success": True,
            "iterations": len(history),
            "history": history,
            "winner": best_global["prompt"],
            "run_id": run_id,
            "primary_metric": self.primary_metric,
        }


__all__ = ["PromptOptimizer", "Candidate", "EvalResult"]


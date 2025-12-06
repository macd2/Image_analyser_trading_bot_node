"""
Tournament System for Finding Best Prompt
Implements elimination-style tournament to efficiently compare prompts
"""

import os
import json
import random
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path

# Import existing backtest components
from prompt_performance.backtest_with_images import (
    ImageBacktester, ImageSelector, PROMPT_REGISTRY
)
from prompt_performance.core.backtest_store import BacktestStore


@dataclass
class TournamentConfig:
    """Configuration for a tournament run"""
    model: str = "gpt-4o"
    elimination_pct: int = 50          # Eliminate bottom X% each phase
    images_phase_1: int = 10           # Images per prompt in phase 1
    images_phase_2: int = 25           # Images per prompt in phase 2
    images_phase_3: int = 50           # Images per prompt in phase 3
    image_offset: int = 100            # Skip N most recent images
    selection_strategy: str = "random"  # random or sequential
    ranking_strategy: str = "wilson"   # wilson, win_rate, pnl
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)
    random_symbols: bool = False       # If True, symbols were randomized
    random_timeframes: bool = False    # If True, timeframes were randomized
    max_workers: int = 5               # Max parallel API calls (respect rate limits)
    min_trades_for_survival: int = 1   # Minimum trades required to survive a phase (0 = disabled)
    hold_penalty: float = -0.1         # PnL penalty per HOLD (opportunity cost) - set to 0 to disable


@dataclass
class PromptScore:
    """Track prompt performance"""
    prompt_name: str
    wins: int = 0
    losses: int = 0
    holds: int = 0
    total_pnl: float = 0.0
    hold_penalty_applied: float = 0.0  # Cumulative hold penalty

    @property
    def trades(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100) if self.trades > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        """Average PnL per trade (without hold penalty)"""
        return (self.total_pnl / self.trades) if self.trades > 0 else 0.0

    @property
    def effective_pnl(self) -> float:
        """Total PnL including hold penalty - used for ranking"""
        return self.total_pnl + self.hold_penalty_applied

    @property
    def wilson_lower(self) -> float:
        """Wilson score lower bound - conservative win rate estimate (95% CI)"""
        n = self.trades
        if n <= 0:
            return 0.0
        p = self.wins / n
        z = 1.96  # 95% confidence
        z2 = z * z
        denom = 1.0 + z2 / n
        center = p + z2 / (2.0 * n)
        margin = z * ((p * (1.0 - p) + z2 / (4.0 * n)) / n) ** 0.5
        lb = (center - margin) / denom
        return max(0.0, min(1.0, lb)) * 100  # Return as percentage

    @property
    def confidence(self) -> float:
        """Sample size confidence (1.0 at 30 trades)"""
        return min(1.0, self.trades / 30.0)

    @property
    def rank_score(self) -> float:
        """Combined rank score factoring in hold penalty.

        If no trades: rank = hold_penalty (negative = bad)
        If trades exist: (wilson × 0.6 + avg_pnl × 0.4) × confidence + hold_penalty_pct
        """
        if self.trades == 0:
            # No trades = just the hold penalty (will be negative)
            return self.hold_penalty_applied / 100.0

        base = (self.wilson_lower / 100 * 0.6) + (self.avg_pnl / 100 * 0.4)
        # Add hold penalty as percentage impact
        hold_impact = self.hold_penalty_applied / 100.0 * 0.2  # 20% weight on hold penalty
        return base * self.confidence + hold_impact


class PromptTournament:
    """
    Tournament-style elimination to find best prompt efficiently
    """
    
    def __init__(
        self,
        config: TournamentConfig,
        charts_dir: str,
        db_path: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.config = config
        self.charts_dir = charts_dir
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'bot.db')
        self.progress_callback = progress_callback
        self._lock = threading.Lock()
        
        # Initialize backtester for running analyses
        self.backtester = ImageBacktester(
            charts_dir=charts_dir,
            db_path=db_path,
            progress_callback=self._internal_progress
        )
        self.image_selector = ImageSelector(charts_dir)
        self.store = BacktestStore()

        # Tournament state
        self.tournament_id: Optional[str] = None
        self.current_phase: int = 0
        self.active_prompts: List[str] = []
        self.scores: Dict[str, PromptScore] = {}
        self.total_api_calls: int = 0

        # Reproducibility tracking
        self._random_seed: int = int(datetime.now().timestamp() * 1000) % (2**31)
        random.seed(self._random_seed)
        self._phase_details: Dict[str, Dict] = {}  # Track all details per phase
        self._start_time: Optional[datetime] = None

        # Capture actual assistant info (for when using OpenAI Assistants API)
        self._assistant_id: Optional[str] = None
        self._assistant_model: Optional[str] = None
        self._resolve_assistant_info()

    def _resolve_assistant_info(self) -> None:
        """Resolve actual assistant ID and model from the backtester's config.

        This captures what model is actually used (from OpenAI Assistant API config),
        not just the requested model in tournament config.
        Future: When switching to direct API calls, this will use config.model directly.
        """
        try:
            config = self.backtester.prompt_analyzer.config
            if hasattr(config, 'openai') and hasattr(config.openai, 'assistant'):
                self._assistant_id = config.openai.assistant.assistants.get('analyzer', '')
                if self._assistant_id:
                    # Retrieve actual model from OpenAI
                    try:
                        client = self.backtester.prompt_analyzer.analyzer.client
                        asst_obj = client.beta.assistants.retrieve(self._assistant_id)
                        self._assistant_model = getattr(asst_obj, 'model', None)
                    except Exception as e:
                        self._emit('info', {'message': f'Could not retrieve assistant model: {e}'})
        except Exception as e:
            self._emit('info', {'message': f'Could not resolve assistant info: {e}'})

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit progress event"""
        if self.progress_callback:
            try:
                with self._lock:
                    self.progress_callback({'type': event_type, **data})
            except Exception:
                pass
                
    def _internal_progress(self, data: Dict[str, Any]) -> None:
        """Handle progress from backtester"""
        if data.get('type') == 'image_complete':
            self.total_api_calls += 1
            self._emit('analysis', {
                'prompt': data.get('prompt_name'),
                'symbol': data.get('symbol'),
                'recommendation': data.get('recommendation'),
                'api_calls': self.total_api_calls
            })
    
    def get_all_prompts(self) -> List[str]:
        """Get all available prompts from registry"""
        return [name for name in PROMPT_REGISTRY.keys() if name != 'get_market_data']
    
    def select_images(self, num_images: int) -> List[str]:
        """Select images for a phase (same images for all prompts = fair comparison)"""
        # ImageSelector.select_images doesn't have strategy param - we handle it here
        all_images = self.image_selector.select_images(
            symbols=self.config.symbols,
            num_images=num_images * 2,  # Get extra to handle offset
            timeframes=self.config.timeframes or None,
            offset=self.config.image_offset
        )

        # Apply random strategy if configured
        if self.config.selection_strategy == 'random':
            random.shuffle(all_images)

        return all_images[:num_images]
    
    def run_phase(self, phase_num: int, images_per_prompt: int) -> Dict[str, PromptScore]:
        """Run a single phase of the tournament"""
        self.current_phase = phase_num
        phase_scores: Dict[str, PromptScore] = {}

        self._emit('phase_start', {
            'phase': phase_num,
            'prompts': len(self.active_prompts),
            'images': images_per_prompt
        })

        # Select same images for all prompts (fair comparison)
        images = self.select_images(images_per_prompt)

        # Fail early if no images found
        if not images:
            error_msg = f"No images found for symbols={self.config.symbols}, timeframes={self.config.timeframes}. Check that backup folder has matching images."
            self._emit('error', {'message': error_msg})
            raise ValueError(error_msg)

        # Extract metadata from images for reproducibility tracking
        image_details = []
        for img_path in images:
            img_name = os.path.basename(str(img_path))
            # Parse: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.png
            parts = img_name.replace('.png', '').split('_')
            if len(parts) >= 4:
                symbol = parts[0]
                timeframe = parts[1]
                timestamp = f"{parts[2]}_{parts[3]}"
                image_details.append({
                    'path': str(img_path),
                    'filename': img_name,
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'timestamp': timestamp
                })
            else:
                image_details.append({'path': str(img_path), 'filename': img_name})

        # Initialize phase tracking with full details for replay
        phase_key = f'phase_{phase_num}'
        self._phase_details[phase_key] = {
            'prompts_tested': list(self.active_prompts),
            'images_count': len(images),
            'images': image_details,
            'symbols_used': list(set(d.get('symbol', 'unknown') for d in image_details)),
            'timeframes_used': list(set(d.get('timeframe', 'unknown') for d in image_details)),
            'analyses': [],  # Will store each analysis result
            'trades': [],    # Will store each trade simulation
            'eliminated': [],  # Prompts eliminated this phase
        }

        total_tasks = len(self.active_prompts) * len(images)
        self._emit('info', {'message': f'Phase {phase_num}: Testing {len(self.active_prompts)} prompts on {len(images)} images ({total_tasks} analyses, {self.config.max_workers} workers)'})

        # Log images being used
        for i, img in enumerate(images):
            self._emit('info', {'message': f'  Image {i+1}: {img.filepath.name}'})

        # Initialize scores for all prompts
        for prompt_name in self.active_prompts:
            phase_scores[prompt_name] = PromptScore(prompt_name=prompt_name)

        # Thread-safe counters and storage
        lock = threading.Lock()
        completed = [0]  # Use list for mutable reference in closure

        def process_task(prompt_name: str, image_info) -> Dict[str, Any]:
            """Process a single (prompt, image) pair - runs in parallel"""
            analysis_record = {
                'prompt': prompt_name,
                'image': image_info.filepath.name,
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
                'timestamp': image_info.timestamp.isoformat() if image_info.timestamp else None,
                'result': None,
                'trade': None,
                'error': None
            }

            try:
                result = self.backtester.prompt_analyzer.analyze_image(image_info, prompt_name)

                if result:
                    rec = (result.get('recommendation') or 'HOLD').upper()

                    # Core fields (always present for backward compatibility)
                    analysis_record['result'] = {
                        'recommendation': rec,
                        'direction': result.get('direction'),
                        'entry_price': result.get('entry_price'),
                        'stop_loss': result.get('stop_loss'),
                        'take_profit': result.get('take_profit'),
                        'confidence': result.get('confidence'),
                        'reasoning': result.get('reasoning', '')[:500] if result.get('reasoning') else None,
                        # Extended metadata from model (new fields, optional)
                        'metadata': {
                            'summary': result.get('summary'),
                            'key_levels': result.get('key_levels'),
                            'risk_factors': result.get('risk_factors'),
                            'market_condition': result.get('market_condition'),
                            'market_direction': result.get('market_direction'),
                            'evidence': result.get('evidence'),
                            'entry_explanation': result.get('entry_explanation'),
                            'take_profit_explanation': result.get('take_profit_explanation'),
                            'stop_loss_explanation': result.get('stop_loss_explanation'),
                            'risk_reward_ratio': result.get('risk_reward_ratio'),
                            'rationale': result.get('rationale'),
                        }
                    }

                    if rec != 'HOLD':
                        trade_result = self._simulate_trade(image_info, result)
                        if trade_result:
                            analysis_record['trade'] = {
                                'prompt': prompt_name,
                                'image': image_info.filepath.name,
                                'symbol': image_info.symbol,
                                'direction': result.get('direction', rec),
                                'entry_price': result.get('entry_price'),
                                'stop_loss': result.get('stop_loss'),
                                'take_profit': result.get('take_profit'),
                                'outcome': trade_result.get('outcome', '').upper(),
                                'pnl': round(trade_result.get('realized_pnl_percent', 0) or 0, 3),
                                'exit_price': trade_result.get('exit_price'),
                                'exit_reason': trade_result.get('exit_reason'),
                                'confidence': result.get('confidence'),
                                # Extended metadata for trades (copy from analysis for easy access)
                                'metadata': {
                                    'summary': result.get('summary'),
                                    'key_levels': result.get('key_levels'),
                                    'risk_factors': result.get('risk_factors'),
                                    'market_condition': result.get('market_condition'),
                                    'market_direction': result.get('market_direction'),
                                    'evidence': result.get('evidence'),
                                    'entry_explanation': result.get('entry_explanation'),
                                    'take_profit_explanation': result.get('take_profit_explanation'),
                                    'stop_loss_explanation': result.get('stop_loss_explanation'),
                                    'risk_reward_ratio': result.get('risk_reward_ratio'),
                                    'rationale': result.get('rationale'),
                                }
                            }
            except Exception as e:
                analysis_record['error'] = str(e)

            return analysis_record

        # Build task list: all (prompt, image) combinations
        tasks = [(p, img) for p in self.active_prompts for img in images]

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            future_to_task = {executor.submit(process_task, p, img): (p, img) for p, img in tasks}

            for future in as_completed(future_to_task):
                prompt_name, image_info = future_to_task[future]
                try:
                    record = future.result()

                    with lock:
                        # Update API call counter
                        self.total_api_calls += 1
                        completed[0] += 1

                        # Store analysis record
                        self._phase_details[phase_key]['analyses'].append(record)

                        # Update score
                        score = phase_scores[prompt_name]
                        if record.get('error'):
                            self._emit('error', {'message': f"Error: {prompt_name} on {image_info.filepath.name}: {record['error']}"})
                        elif record.get('result'):
                            rec = record['result'].get('recommendation', 'HOLD')
                            if rec == 'HOLD':
                                score.holds += 1
                                # Apply hold penalty (opportunity cost)
                                score.hold_penalty_applied += self.config.hold_penalty
                            elif record.get('trade'):
                                trade = record['trade']
                                outcome = trade.get('outcome', '')
                                pnl = trade.get('pnl', 0)
                                if outcome == 'WIN':
                                    score.wins += 1
                                elif outcome == 'LOSS':
                                    score.losses += 1
                                score.total_pnl += pnl
                                self._phase_details[phase_key]['trades'].append(trade)
                                self._emit('trade', {
                                    'prompt': prompt_name,
                                    'image': image_info.filepath.name,
                                    'direction': trade.get('direction'),
                                    'outcome': outcome,
                                    'pnl': pnl
                                })

                        # Progress update every 10%
                        if completed[0] % max(1, total_tasks // 10) == 0:
                            pct = int(completed[0] / total_tasks * 100)
                            self._emit('info', {'message': f'  Progress: {completed[0]}/{total_tasks} ({pct}%)'})

                except Exception as e:
                    self._emit('error', {'message': f'Future error for {prompt_name}: {e}'})

        # Emit prompt_complete for each prompt
        for prompt_name in self.active_prompts:
            score = phase_scores[prompt_name]
            self._emit('prompt_complete', {
                'phase': phase_num,
                'prompt': prompt_name,
                'win_rate': score.win_rate,
                'avg_pnl': score.avg_pnl,
                'trades': score.trades
            })

        return phase_scores

    def _simulate_trade(self, image_info, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Simulate a trade using the trade simulator to get outcome and PnL."""
        try:
            entry_price = analysis.get('entry_price', 0)
            stop_loss = analysis.get('stop_loss', 0)
            take_profit = analysis.get('take_profit', 0)
            recommendation = (analysis.get('recommendation') or 'hold').lower()

            # Skip if no valid prices or hold recommendation
            if recommendation == 'hold':
                return None
            if not entry_price or entry_price <= 0:
                return None
            if not stop_loss or stop_loss <= 0:
                return None
            if not take_profit or take_profit <= 0:
                return None

            # Convert timestamp to ms if needed
            ts = image_info.timestamp
            if hasattr(ts, 'timestamp'):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                ts_ms = int(ts)

            # First try to get from cache
            candles = self.backtester.candle_fetcher.get_candles_for_simulation(
                symbol=image_info.symbol,
                timeframe=image_info.timeframe,
                start_timestamp=ts_ms,
                limit=100
            )

            # If no candles, fetch from API
            if not candles:
                self.backtester.candle_fetcher.fetch_and_cache_candles(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    earliest_timestamp=ts_ms
                )
                candles = self.backtester.candle_fetcher.get_candles_for_simulation(
                    symbol=image_info.symbol,
                    timeframe=image_info.timeframe,
                    start_timestamp=ts_ms,
                    limit=100
                )

            if not candles:
                self._emit('error', {'message': f'No candles for {image_info.symbol} at {image_info.timestamp}'})
                return None

            # Verify first candle is within 24h of image timestamp (data validity check)
            first_candle_ts = candles[0].get('start_time', 0)
            max_gap_ms = 24 * 60 * 60 * 1000  # 24 hours
            if abs(first_candle_ts - ts_ms) > max_gap_ms:
                self._emit('error', {'message': f'Candle data gap: image at {image_info.timestamp}, first candle {(first_candle_ts - ts_ms) / 3600000:.1f}h away'})
                return None

            # Build record for simulator
            record = {
                'recommendation': recommendation,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'timestamp': image_info.timestamp.isoformat() if hasattr(image_info.timestamp, 'isoformat') else str(image_info.timestamp),
                'symbol': image_info.symbol,
                'timeframe': image_info.timeframe,
            }

            # Use trade simulator
            trade_result = self.backtester.trade_simulator.simulate_trade(record, candles)
            return trade_result
        except Exception as e:
            self._emit('error', {'message': f'Trade simulation error: {e}'})
            return None

    def _get_rank_key(self, score: PromptScore):
        """Get ranking key based on configured strategy"""
        strategy = self.config.ranking_strategy
        if strategy == 'wilson':
            # Wilson lower bound (sample-size aware) with PnL and confidence
            return (score.rank_score, score.wilson_lower, score.avg_pnl, score.trades)
        elif strategy == 'pnl':
            # Average PnL focused
            return (score.avg_pnl, score.win_rate, score.trades)
        else:  # 'win_rate' default
            return (score.win_rate, score.avg_pnl, score.trades)

    def eliminate_prompts(self, phase_scores: Dict[str, PromptScore], phase_num: int) -> List[str]:
        """Eliminate bottom X% of prompts based on configured ranking strategy.

        Also enforces min_trades_for_survival - prompts with fewer trades are auto-eliminated.
        """
        ranked = sorted(
            phase_scores.values(),
            key=self._get_rank_key,
            reverse=True
        )

        # Calculate how many to keep based on elimination percentage
        keep_count = max(2, int(len(ranked) * (100 - self.config.elimination_pct) / 100))

        # Apply minimum trades requirement
        min_trades = self.config.min_trades_for_survival
        if min_trades > 0:
            # Separate into those meeting min trades and those not
            meets_min = [s for s in ranked if s.trades >= min_trades]
            below_min = [s for s in ranked if s.trades < min_trades]

            if below_min:
                self._emit('info', {
                    'message': f'  Auto-eliminating {len(below_min)} prompts with <{min_trades} trades: ' +
                               ', '.join(s.prompt_name.replace("get_analyzer_prompt_", "") for s in below_min[:5]) +
                               ('...' if len(below_min) > 5 else '')
                })

            # Survivors come from those meeting minimum, then by ranking
            if len(meets_min) >= keep_count:
                # Enough prompts meet minimum - take top keep_count from them
                survivors = [s.prompt_name for s in meets_min[:keep_count]]
            else:
                # Not enough meet minimum - take all that do, then fill from below_min by rank
                survivors = [s.prompt_name for s in meets_min]
                remaining = keep_count - len(survivors)
                if remaining > 0 and below_min:
                    survivors.extend([s.prompt_name for s in below_min[:remaining]])
        else:
            survivors = [s.prompt_name for s in ranked[:keep_count]]

        eliminated = [s.prompt_name for s in ranked if s.prompt_name not in survivors]

        # Store rankings and eliminated prompts in phase details
        phase_key = f'phase_{phase_num}'
        if phase_key in self._phase_details:
            self._phase_details[phase_key]['eliminated'] = eliminated
            self._phase_details[phase_key]['survivors'] = survivors
            self._phase_details[phase_key]['rankings'] = [{
                'prompt': s.prompt_name,
                'win_rate': s.win_rate,
                'avg_pnl': s.avg_pnl,
                'effective_pnl': s.effective_pnl,
                'hold_penalty': s.hold_penalty_applied,
                'wins': s.wins,
                'losses': s.losses,
                'holds': s.holds,
                'trades': s.trades,
                'wilson_lower': s.wilson_lower,
                'rank_score': s.rank_score,
                'survived': s.prompt_name in survivors
            } for s in ranked]

        self._emit('elimination', {
            'phase': self.current_phase,
            'survivors': survivors,
            'eliminated': eliminated,
            'rankings': [{
                'prompt': s.prompt_name,
                'win_rate': s.win_rate,
                'avg_pnl': s.avg_pnl,
                'hold_penalty': s.hold_penalty_applied,
                'wilson_lower': s.wilson_lower,
                'rank_score': s.rank_score,
                'trades': s.trades
            } for s in ranked]
        })

        return survivors

    def run_tournament(self, prompt_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Run full tournament to find best prompt

        Returns:
            {
                'winner': prompt_name,
                'win_rate': float,
                'avg_pnl': float,
                'rankings': [...],
                'phases': [...],
                'total_api_calls': int
            }
        """
        self._start_time = datetime.now()

        # Initialize prompts - validate each one exists
        requested_prompts = prompt_names or self.get_all_prompts()
        valid_prompts = []
        invalid_prompts = []

        for p in requested_prompts:
            try:
                self.backtester.prompt_analyzer.get_prompt_function(p)
                valid_prompts.append(p)
            except ValueError:
                invalid_prompts.append(p)
                self._emit('error', {'message': f'Skipping invalid prompt: {p} (not found in analyzer_prompt.py)'})

        if invalid_prompts:
            self._emit('info', {'message': f'Skipped {len(invalid_prompts)} invalid prompts: {invalid_prompts}'})

        self.active_prompts = valid_prompts
        if len(self.active_prompts) < 2:
            raise ValueError(f"Need at least 2 valid prompts for tournament. Found: {len(valid_prompts)} valid, {len(invalid_prompts)} invalid")

        # Generate tournament ID and save to store
        self.tournament_id = f"t_{self._start_time.strftime('%Y%m%d_%H%M%S')}_{self._random_seed}"
        config_dict = {
            'model': self.config.model,  # Requested model (for future direct API calls)
            'elimination_pct': self.config.elimination_pct,
            'images_phase_1': self.config.images_phase_1,
            'images_phase_2': self.config.images_phase_2,
            'images_phase_3': self.config.images_phase_3,
            'image_offset': self.config.image_offset,
            'selection_strategy': self.config.selection_strategy,
            'ranking_strategy': self.config.ranking_strategy,
            'symbols': self.config.symbols,
            'timeframes': self.config.timeframes,
            'random_symbols': self.config.random_symbols,
            'random_timeframes': self.config.random_timeframes,
            'prompts': self.active_prompts,
            # Actual model used (from OpenAI Assistant API)
            'assistant_id': self._assistant_id,
            'assistant_model': self._assistant_model,
        }
        self.store.tournament_create(
            tournament_id=self.tournament_id,
            started_at=self._start_time.isoformat(),
            config=config_dict,
            random_seed=self._random_seed
        )

        self._emit('start', {
            'prompts': self.active_prompts,
            'tournament_id': self.tournament_id,
            'config': {
                'elimination_pct': self.config.elimination_pct,
                'phases': [self.config.images_phase_1, self.config.images_phase_2, self.config.images_phase_3]
            }
        })

        all_phase_results = []
        phase_configs = [
            (1, self.config.images_phase_1),
            (2, self.config.images_phase_2),
            (3, self.config.images_phase_3),
        ]

        # Run phases until we have a winner or run out of phases
        for phase_num, images_per_prompt in phase_configs:
            if len(self.active_prompts) <= 1:
                break

            # Run this phase
            phase_scores = self.run_phase(phase_num, images_per_prompt)
            all_phase_results.append({
                'phase': phase_num,
                'scores': {k: {'win_rate': v.win_rate, 'avg_pnl': v.avg_pnl, 'trades': v.trades}
                          for k, v in phase_scores.items()}
            })

            # Accumulate scores
            for name, score in phase_scores.items():
                if name not in self.scores:
                    self.scores[name] = PromptScore(prompt_name=name)
                self.scores[name].wins += score.wins
                self.scores[name].losses += score.losses
                self.scores[name].holds += score.holds
                self.scores[name].total_pnl += score.total_pnl

            # Eliminate bottom performers (unless final phase or few remaining)
            if len(self.active_prompts) > 2:
                self.active_prompts = self.eliminate_prompts(phase_scores, phase_num)

        # Determine final winner using configured ranking strategy
        final_rankings = sorted(
            [self.scores[p] for p in self.active_prompts if p in self.scores],
            key=self._get_rank_key,
            reverse=True
        )

        winner = final_rankings[0] if final_rankings else None
        duration = (datetime.now() - self._start_time).total_seconds()

        result = {
            'tournament_id': self.tournament_id,
            'winner': winner.prompt_name if winner else None,
            'win_rate': winner.win_rate if winner else 0,
            'avg_pnl': winner.avg_pnl if winner else 0,
            'wilson_lower': winner.wilson_lower if winner else 0,
            'rank_score': winner.rank_score if winner else 0,
            'ranking_strategy': self.config.ranking_strategy,
            'rankings': [
                {'rank': i+1, 'prompt': s.prompt_name, 'win_rate': s.win_rate,
                 'avg_pnl': s.avg_pnl, 'trades': s.trades, 'wilson_lower': s.wilson_lower,
                 'rank_score': s.rank_score}
                for i, s in enumerate(final_rankings)
            ],
            'phases': all_phase_results,
            'total_api_calls': self.total_api_calls,
            'duration_sec': duration,
            # Reproducibility: random seed used
            'random_seed': self._random_seed,
            # Store all config
            'config': {
                'model': self.config.model,  # Requested model (for future direct API calls)
                'elimination_pct': self.config.elimination_pct,
                'images_phase_1': self.config.images_phase_1,
                'images_phase_2': self.config.images_phase_2,
                'images_phase_3': self.config.images_phase_3,
                'image_offset': self.config.image_offset,
                'selection_strategy': self.config.selection_strategy,
                'ranking_strategy': self.config.ranking_strategy,
                'symbols': self.config.symbols,
                'timeframes': self.config.timeframes,
                'random_symbols': self.config.random_symbols,
                'random_timeframes': self.config.random_timeframes,
                'min_trades_for_survival': self.config.min_trades_for_survival,
                'hold_penalty': self.config.hold_penalty,
                # Actual model used (from OpenAI Assistant API)
                'assistant_id': self._assistant_id,
                'assistant_model': self._assistant_model,
            },
            # Full phase details: images, symbols, timeframes used per phase
            'phase_details': self._phase_details
        }

        # Save to store
        self.store.tournament_complete(
            tournament_id=self.tournament_id,
            finished_at=datetime.now().isoformat(),
            status='completed',
            phase_details=self._phase_details,
            result=result
        )

        self._emit('complete', result)
        return result


# CLI for testing
if __name__ == '__main__':
    import sys

    config = TournamentConfig(
        symbols=['BTCUSDT', 'ETHUSDT'],
        elimination_pct=50,
        images_phase_1=5,
        images_phase_2=10,
        images_phase_3=20
    )

    def progress(data):
        print(f"[{data.get('type')}] {json.dumps(data, default=str)}")

    tournament = PromptTournament(
        config=config,
        charts_dir='data/charts/.backup',
        progress_callback=progress
    )

    result = tournament.run_tournament()
    print(f"\n🏆 Winner: {result['winner']} (Win Rate: {result['win_rate']:.1f}%)")


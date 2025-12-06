import logging
import csv
from typing import List, Dict, Any, DefaultDict, Optional
from collections import defaultdict
from pathlib import Path
try:
    from .database_utils import CandleStoreDatabase
except ImportError:
    # Fallback for dynamic imports
    import sys
    from pathlib import Path
    core_dir = Path(__file__).parent
    sys.path.insert(0, str(core_dir))
    from database_utils import CandleStoreDatabase

logger = logging.getLogger(__name__)

class MetricsAggregator:
    """Aggregates trade simulation results and generates reports."""

    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            # Default to a path relative to this module's location
            module_dir = Path(__file__).parent.parent
            output_dir = str(module_dir)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def aggregate_by_prompt_version(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_version."""
        prompt_groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            prompt_version = result.get('prompt_version', 'unknown')
            prompt_groups[prompt_version].append(result)

        aggregated = []
        for prompt_version, results in prompt_groups.items():
            metrics = self._calculate_metrics(results)
            aggregated.append({
                'prompt_version': prompt_version,
                **metrics
            })

        return aggregated

    def aggregate_by_prompt_and_symbol_timeframe(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_version, symbol, and timeframe."""
        group_key = lambda r: (r.get('prompt_version', 'unknown'), r['symbol'], r['timeframe'])
        groups: DefaultDict[tuple, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            key = group_key(result)
            groups[key].append(result)

        aggregated = []
        for (prompt_version, symbol, timeframe), results in groups.items():
            metrics = self._calculate_metrics(results)
            aggregated.append({
                'prompt_version': prompt_version,
                'symbol': symbol,
                'timeframe': timeframe,
                **metrics
            })

        return aggregated

    def aggregate_by_prompt_hash(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_hash."""
        prompt_groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            prompt_hash = result.get('prompt_hash', 'unknown')
            prompt_groups[prompt_hash].append(result)

        aggregated = []
        for prompt_hash, results in prompt_groups.items():
            metrics = self._calculate_metrics(results)
            aggregated.append({
                'prompt_hash': prompt_hash,
                **metrics
            })

        return aggregated

    def aggregate_by_prompt_hash_and_symbol_timeframe(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_hash, symbol, and timeframe."""
        group_key = lambda r: (r.get('prompt_hash', 'unknown'), r['symbol'], r['timeframe'])
        groups: DefaultDict[tuple, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            key = group_key(result)
            groups[key].append(result)

        aggregated = []
        for (prompt_hash, symbol, timeframe), results in groups.items():
            metrics = self._calculate_metrics(results)
            aggregated.append({
                'prompt_hash': prompt_hash,
                'symbol': symbol,
                'timeframe': timeframe,
                **metrics
            })

        return aggregated

    def aggregate_by_prompt_hash_symbol_timeframe(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_hash, symbol, and timeframe combinations."""
        group_key = lambda r: (r.get('prompt_hash', 'unknown'), r.get('symbol', 'unknown'), r.get('timeframe', 'unknown'))
        groups: DefaultDict[tuple, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            key = group_key(result)
            groups[key].append(result)

        aggregated = []
        for (prompt_hash, symbol, timeframe), results in groups.items():
            metrics = self._calculate_metrics(results)

            aggregated.append({
                'prompt_hash': prompt_hash,
                'symbol': symbol,
                'timeframe': timeframe,
                'combination': f"{prompt_hash[:5]}_{symbol}_{timeframe}",
                **metrics
            })

        # Sort by win rate descending
        aggregated.sort(key=lambda x: x['win_rate'], reverse=True)

        return aggregated

    def get_top_performing_combinations(self, trade_results: List[Dict[str, Any]], top_n: int = 20) -> List[Dict[str, Any]]:
        """Get top performing prompt_hash + symbol + timeframe combinations."""
        combinations = self.aggregate_by_prompt_hash_symbol_timeframe(trade_results)

        logger.info(f"Found {len(combinations)} total combinations before filtering")

        # Debug: Log sample combinations
        if combinations:
            logger.info(f"Sample combination: {combinations[0]}")

        # Filter combinations with minimum trade count for statistical significance
        significant_combinations = [
            combo for combo in combinations
            if combo['total_trades'] >= 5  # Minimum 5 trades for significance
        ]

        logger.info(f"Found {len(significant_combinations)} significant combinations (>=5 trades)")

        return significant_combinations[:top_n]

    def _calculate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate performance metrics for a group of trade results."""
        if not results:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_rr': 0.0,
                'profit_factor': 0.0,
                'expectancy': 0.0
            }

        total_trades = len(results)
        wins = [r for r in results if r['outcome'] == 'win']
        losses = [r for r in results if r['outcome'] == 'loss']

        # Win rate (exclude expired)
        win_rate = len(wins) / (len(wins) + len(losses)) if (len(wins) + len(losses)) > 0 else 0.0

        # Average RR for winning trades
        avg_rr = sum(r['achieved_rr'] for r in wins) / len(wins) if wins else 0.0

        # Profit factor
        total_win_pips = sum(abs(r['take_profit'] - r['entry_price']) * r['achieved_rr'] for r in wins)
        total_loss_pips = sum(abs(r['entry_price'] - r['stop_loss']) for r in losses)
        profit_factor = total_win_pips / total_loss_pips if total_loss_pips > 0 else float('inf')

        # Expectancy
        avg_win = total_win_pips / len(wins) if wins else 0.0
        avg_loss = total_loss_pips / len(losses) if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        return {
            'total_trades': total_trades,
            'win_rate': round(win_rate, 4),
            'avg_rr': round(avg_rr, 4),
            'profit_factor': round(profit_factor, 4) if profit_factor != float('inf') else profit_factor,
            'expectancy': round(expectancy, 4)
        }

    def write_summary_csv(self, aggregated_results: List[Dict[str, Any]], filename: str = "summary.csv"):
        """Write aggregated summary to CSV."""
        filepath = self.output_dir / filename

        if not aggregated_results:
            logger.warning("No results to write to summary CSV")
            return

        fieldnames = ['prompt_version', 'symbol', 'timeframe', 'total_trades', 'win_rate', 'avg_rr', 'profit_factor', 'expectancy']

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(aggregated_results)

        logger.info(f"Summary CSV written to {filepath}")

    def write_summary_csv_for_prompt_hash(self, aggregated_results: List[Dict[str, Any]], filename: str = "summary_prompt_hash.csv"):
        """Write aggregated summary to CSV for prompt hash analysis."""
        filepath = self.output_dir / filename

        if not aggregated_results:
            logger.warning("No results to write to prompt hash summary CSV")
            return

        fieldnames = ['prompt_hash', 'symbol', 'timeframe', 'total_trades', 'win_rate', 'avg_rr', 'profit_factor', 'expectancy']

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(aggregated_results)

        logger.info(f"Prompt hash summary CSV written to {filepath}")

    def write_trade_logs_csv(self, trade_results: List[Dict[str, Any]], filename: str = "trade_logs.csv"):
        """Write detailed trade logs to CSV."""
        filepath = self.output_dir / filename

        if not trade_results:
            logger.warning("No trade results to write to logs CSV")
            return

        fieldnames = [
            'prompt_version', 'symbol', 'timeframe', 'timestamp', 'direction',
            'entry_price', 'stop_loss', 'take_profit', 'outcome', 'duration_candles',
            'achieved_rr', 'confidence'
        ]

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in trade_results:
                # Format timestamp if it's a string
                timestamp = result.get('timestamp')
                if isinstance(timestamp, (int, float)):
                    # Convert ms timestamp to ISO string
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(timestamp / 1000).isoformat()
                elif not isinstance(timestamp, str):
                    timestamp = str(timestamp)

                row = {
                    'prompt_version': result.get('prompt_version', 'unknown'),
                    'symbol': result['symbol'],
                    'timeframe': result['timeframe'],
                    'timestamp': timestamp,
                    'direction': result['direction'],
                    'entry_price': result['entry_price'],
                    'stop_loss': result['stop_loss'],
                    'take_profit': result['take_profit'],
                    'outcome': result['outcome'],
                    'duration_candles': result['duration_candles'],
                    'achieved_rr': round(result['achieved_rr'], 4),
                    'confidence': result.get('confidence', 0.0)
                }
                writer.writerow(row)

        logger.info(f"Trade logs CSV written to {filepath}")

    def write_trade_logs_csv_for_prompt_hash(self, trade_results: List[Dict[str, Any]], filename: str = "trade_logs_prompt_hash.csv"):
        """Write detailed trade logs to CSV for prompt hash analysis."""
        filepath = self.output_dir / filename

        if not trade_results:
            logger.warning("No trade results to write to prompt hash logs CSV")
            return

        fieldnames = [
            'prompt_hash', 'symbol', 'timeframe', 'timestamp', 'direction',
            'entry_price', 'stop_loss', 'take_profit', 'outcome', 'duration_candles',
            'achieved_rr', 'confidence'
        ]

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in trade_results:
                # Format timestamp if it's a string
                timestamp = result.get('timestamp')
                if isinstance(timestamp, (int, float)):
                    # Convert ms timestamp to ISO string
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(timestamp / 1000).isoformat()
                elif not isinstance(timestamp, str):
                    timestamp = str(timestamp)

                row = {
                    'prompt_hash': result.get('prompt_hash', 'unknown'),
                    'symbol': result['symbol'],
                    'timeframe': result['timeframe'],
                    'timestamp': timestamp,
                    'direction': result['direction'],
                    'entry_price': result['entry_price'],
                    'stop_loss': result['stop_loss'],
                    'take_profit': result['take_profit'],
                    'outcome': result['outcome'],
                    'duration_candles': result['duration_candles'],
                    'achieved_rr': round(result['achieved_rr'], 4),
                    'confidence': result.get('confidence', 0.0)
                }
                writer.writerow(row)

        logger.info(f"Prompt hash trade logs CSV written to {filepath}")

    def write_metadata_enhanced_csv(self, aggregated_results: List[Dict[str, Any]], filename: str = "summary_with_metadata.csv"):
        """Write aggregated summary with metadata to CSV."""
        filepath = self.output_dir / filename

        if not aggregated_results:
            logger.warning("No results to write to metadata-enhanced CSV")
            return

        fieldnames = [
            'prompt_hash', 'normalized_prompt', 'timeframe', 'symbol',
            'total_trades', 'win_rate', 'avg_rr', 'profit_factor', 'expectancy'
        ]

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in aggregated_results:
                metadata = result.get('metadata', {})
                row = {
                    'prompt_hash': result.get('prompt_hash', 'unknown'),
                    'normalized_prompt': metadata.get('normalized_prompt', ''),
                    'timeframe': metadata.get('timeframe', ''),
                    'symbol': metadata.get('symbol', ''),
                    'total_trades': result.get('total_trades', 0),
                    'win_rate': result.get('win_rate', 0.0),
                    'avg_rr': result.get('avg_rr', 0.0),
                    'profit_factor': result.get('profit_factor', 0.0),
                    'expectancy': result.get('expectancy', 0.0)
                }
                writer.writerow(row)

        logger.info(f"Metadata-enhanced CSV written to {filepath}")

    def write_combination_analysis_csv(self, combinations: List[Dict[str, Any]], filename: str = "combination_analysis.csv"):
        """Write combination analysis to CSV."""
        filepath = self.output_dir / filename

        if not combinations:
            logger.warning("No combinations to write to CSV")
            return

        fieldnames = [
            'combination', 'prompt_hash', 'symbol', 'timeframe',
            'total_trades', 'win_rate', 'avg_rr', 'profit_factor', 'expectancy'
        ]

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(combinations)

        logger.info(f"Combination analysis CSV written to {filepath}")

    def generate_report(self, trade_results: List[Dict[str, Any]]):
        """Generate both summary and detailed reports."""
        # Aggregate by prompt and symbol/timeframe
        summary_results = self.aggregate_by_prompt_and_symbol_timeframe(trade_results)

        # Write CSVs
        self.write_summary_csv(summary_results)
        self.write_trade_logs_csv(trade_results)

        logger.info("Report generation completed")

    def generate_report_for_prompt_hash(self, trade_results: List[Dict[str, Any]]):
        """Generate both summary and detailed reports for prompt hash analysis."""
        # Aggregate by prompt hash and symbol/timeframe
        summary_results = self.aggregate_by_prompt_hash_and_symbol_timeframe(trade_results)

        # Write CSVs
        self.write_summary_csv_for_prompt_hash(summary_results)
        self.write_trade_logs_csv_for_prompt_hash(trade_results)

        logger.info("Prompt hash report generation completed")

    def get_prompt_hash_metadata(self, prompt_hash: str) -> Dict[str, Any]:
        """Get metadata for a prompt hash from the database."""
        db = CandleStoreDatabase()

        # Get the normalized prompt text
        prompt_text = db.get_prompt_text_by_hash(prompt_hash)

        # Get the metadata (timeframe, symbol)
        metadata = db.get_prompt_metadata(prompt_hash)

        result = {
            'prompt_hash': prompt_hash,
            'normalized_prompt': prompt_text or '',
            'has_metadata': metadata is not None
        }

        if metadata:
            result.update(metadata)

        return result

    def aggregate_by_prompt_hash_with_metadata(self, trade_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aggregate metrics by prompt_hash and include metadata for analysis."""
        prompt_groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)

        for result in trade_results:
            prompt_hash = result.get('prompt_hash', 'unknown')
            prompt_groups[prompt_hash].append(result)

        aggregated = []
        for prompt_hash, results in prompt_groups.items():
            metrics = self._calculate_metrics(results)

            # Get metadata for this prompt hash
            metadata = self.get_prompt_hash_metadata(prompt_hash)

            aggregated.append({
                'prompt_hash': prompt_hash,
                'metadata': metadata,
                **metrics
            })

        return aggregated
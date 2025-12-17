"""
Trade Replay Engine - Replay trades with identical inputs to verify reproducibility

This module provides functionality to:
1. Load reproducibility data from database
2. Re-run analysis with identical inputs
3. Compare original vs replayed results
4. Calculate similarity scores
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Engine for replaying trades with reproducibility data"""

    def __init__(self):
        """Initialize replay engine"""
        self.original_result = None
        self.replayed_result = None
        self.comparison = None

    def replay_analysis(
        self,
        strategy_instance: Any,
        reproducibility_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Replay analysis with identical inputs from reproducibility data

        Args:
            strategy_instance: Strategy instance to use for replay
            reproducibility_data: Reproducibility data from database

        Returns:
            Dict with replayed analysis result
        """
        try:
            recommendation = reproducibility_data.get("recommendation", {})
            market_data = recommendation.get("market_data_snapshot", {})
            strategy_config = recommendation.get("strategy_config_snapshot", {})

            # Call strategy analyze with same inputs
            replayed_result = strategy_instance.analyze(
                market_data=market_data,
                strategy_config=strategy_config,
            )

            self.replayed_result = replayed_result
            return replayed_result

        except Exception as e:
            logger.error(f"Failed to replay analysis: {e}")
            raise

    def compare_results(
        self,
        original: Dict[str, Any],
        replayed: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare original recommendation with replayed result

        Args:
            original: Original recommendation from database
            replayed: Replayed analysis result

        Returns:
            Dict with comparison results and similarity score
        """
        comparison = {
            "original": original,
            "replayed": replayed,
            "differences": [],
            "similarity_score": 0.0,
            "is_reproducible": False,
        }

        # Key fields to compare
        key_fields = [
            "recommendation",
            "confidence",
            "entry_price",
            "stop_loss",
            "take_profit",
        ]

        matching_fields = 0
        total_fields = len(key_fields)

        for field in key_fields:
            orig_val = original.get(field)
            replay_val = replayed.get(field)

            if orig_val == replay_val:
                matching_fields += 1
            else:
                comparison["differences"].append({
                    "field": field,
                    "original": orig_val,
                    "replayed": replay_val,
                    "match": False,
                })

        # Calculate similarity score (0-100%)
        similarity_score = (matching_fields / total_fields) * 100 if total_fields > 0 else 0
        comparison["similarity_score"] = round(similarity_score, 2)

        # Consider reproducible if all key fields match
        comparison["is_reproducible"] = matching_fields == total_fields

        self.comparison = comparison
        return comparison

    def get_comparison_summary(self) -> Dict[str, Any]:
        """
        Get summary of comparison results

        Returns:
            Dict with summary information
        """
        if not self.comparison:
            return {"error": "No comparison data available"}

        return {
            "is_reproducible": self.comparison["is_reproducible"],
            "similarity_score": self.comparison["similarity_score"],
            "differences_count": len(self.comparison["differences"]),
            "differences": self.comparison["differences"],
        }

    def export_replay_report(self, output_path: Optional[str] = None) -> str:
        """
        Export replay report as JSON

        Args:
            output_path: Optional path to save report

        Returns:
            JSON string of report
        """
        if not self.comparison:
            return json.dumps({"error": "No comparison data available"})

        report = {
            "replay_summary": self.get_comparison_summary(),
            "original_result": self.original_result,
            "replayed_result": self.replayed_result,
            "full_comparison": self.comparison,
        }

        report_json = json.dumps(report, indent=2, default=str)

        if output_path:
            Path(output_path).write_text(report_json)
            logger.info(f"Replay report saved to {output_path}")

        return report_json


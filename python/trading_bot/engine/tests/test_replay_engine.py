"""
Tests for Trade Replay Engine
"""

import sys
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from trading_bot.engine.replay_engine import ReplayEngine


class TestReplayEngine:
    """Test suite for ReplayEngine"""

    @pytest.fixture
    def replay_engine(self):
        """Create replay engine instance"""
        return ReplayEngine()

    @pytest.fixture
    def mock_strategy(self):
        """Create mock strategy instance"""
        strategy = Mock()
        strategy.analyze = Mock(return_value={
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        })
        return strategy

    @pytest.fixture
    def reproducibility_data(self):
        """Create sample reproducibility data"""
        return {
            "recommendation": {
                "symbol": "BTCUSDT",
                "recommendation": "LONG",
                "confidence": 0.85,
                "entry_price": 100.0,
                "stop_loss": 99.0,
                "take_profit": 102.0,
                "market_data_snapshot": {
                    "symbol": "BTCUSDT",
                    "last_price": 100.5,
                    "volume_24h": 1000000,
                },
                "strategy_config_snapshot": {
                    "use_assistant": True,
                    "timeout": 600,
                },
            },
            "execution": {
                "position_sizing_inputs": {
                    "entry_price": 100.0,
                    "stop_loss": 99.0,
                    "wallet_balance": 10000.0,
                },
            },
        }

    def test_replay_analysis_success(self, replay_engine, mock_strategy, reproducibility_data):
        """Test successful replay of analysis"""
        result = replay_engine.replay_analysis(mock_strategy, reproducibility_data)

        assert result is not None
        assert result["recommendation"] == "LONG"
        assert result["confidence"] == 0.85
        mock_strategy.analyze.assert_called_once()

    def test_replay_analysis_with_market_data(self, replay_engine, mock_strategy, reproducibility_data):
        """Test replay passes correct market data to strategy"""
        replay_engine.replay_analysis(mock_strategy, reproducibility_data)

        # Verify analyze was called with market data
        call_args = mock_strategy.analyze.call_args
        assert call_args is not None
        assert "market_data" in call_args.kwargs
        assert call_args.kwargs["market_data"]["symbol"] == "BTCUSDT"

    def test_compare_results_identical(self, replay_engine):
        """Test comparison when results are identical"""
        original = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        replayed = original.copy()

        comparison = replay_engine.compare_results(original, replayed)

        assert comparison["is_reproducible"] is True
        assert comparison["similarity_score"] == 100.0
        assert len(comparison["differences"]) == 0

    def test_compare_results_different(self, replay_engine):
        """Test comparison when results differ"""
        original = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        replayed = {
            "recommendation": "LONG",
            "confidence": 0.80,  # Different
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }

        comparison = replay_engine.compare_results(original, replayed)

        assert comparison["is_reproducible"] is False
        assert comparison["similarity_score"] == 80.0  # 4/5 fields match
        assert len(comparison["differences"]) == 1
        assert comparison["differences"][0]["field"] == "confidence"

    def test_get_comparison_summary(self, replay_engine):
        """Test getting comparison summary"""
        original = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        replayed = original.copy()

        replay_engine.compare_results(original, replayed)
        summary = replay_engine.get_comparison_summary()

        assert summary["is_reproducible"] is True
        assert summary["similarity_score"] == 100.0
        assert summary["differences_count"] == 0

    def test_export_replay_report(self, replay_engine, tmp_path):
        """Test exporting replay report"""
        original = {
            "recommendation": "LONG",
            "confidence": 0.85,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
        }
        replayed = original.copy()

        replay_engine.original_result = original
        replay_engine.replayed_result = replayed
        replay_engine.compare_results(original, replayed)

        output_path = str(tmp_path / "replay_report.json")
        report_json = replay_engine.export_replay_report(output_path)

        # Verify report is valid JSON
        report = json.loads(report_json)
        assert "replay_summary" in report
        assert "original_result" in report
        assert "replayed_result" in report

        # Verify file was created
        assert Path(output_path).exists()

    def test_replay_analysis_error_handling(self, replay_engine, mock_strategy):
        """Test error handling in replay analysis"""
        mock_strategy.analyze.side_effect = Exception("Analysis failed")

        with pytest.raises(Exception):
            replay_engine.replay_analysis(mock_strategy, {})

    def test_comparison_without_data(self, replay_engine):
        """Test getting summary without comparison data"""
        summary = replay_engine.get_comparison_summary()
        assert "error" in summary


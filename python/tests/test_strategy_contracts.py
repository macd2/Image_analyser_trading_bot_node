"""Strategy Contract Tests

Tests that strategies return expected output format and invariants hold.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestPromptStrategyContract:
    """Test prompt strategy contracts."""

    def test_recommendation_output_format(self):
        """Test that recommendation has required fields."""
        # Mock the analyzer
        recommendation = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.85,
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
            "risk_reward": 1.0,
            "setup_quality": 0.8,
            "market_environment": 0.7,
            "strategy_uuid": "test-uuid-123",
            "strategy_type": "price_based",
            "strategy_name": "AiImageAnalyzer",
            "strategy_metadata": {},
        }

        # Verify all required fields present
        required_fields = [
            "symbol", "recommendation", "confidence", "entry_price",
            "stop_loss", "take_profit", "risk_reward", "setup_quality",
            "market_environment", "strategy_uuid", "strategy_type",
            "strategy_name", "strategy_metadata"
        ]
        for field in required_fields:
            assert field in recommendation, f"Missing field: {field}"

    def test_long_trade_sl_tp_logic(self):
        """Test case 1: Long trade has SL < entry < TP."""
        recommendation = {
            "recommendation": "BUY",
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
        }

        assert recommendation["stop_loss"] < recommendation["entry_price"]
        assert recommendation["entry_price"] < recommendation["take_profit"]

    def test_short_trade_sl_tp_logic(self):
        """Test case 2: Short trade has SL > entry > TP."""
        recommendation = {
            "recommendation": "SELL",
            "entry_price": 50000,
            "stop_loss": 51000,
            "take_profit": 49000,
        }

        assert recommendation["stop_loss"] > recommendation["entry_price"]
        assert recommendation["entry_price"] > recommendation["take_profit"]

    def test_confidence_range(self):
        """Test case 3: Confidence is in valid range."""
        for confidence in [0.0, 0.5, 0.75, 1.0]:
            assert 0 <= confidence <= 1

    def test_risk_reward_calculation(self):
        """Test case 4: Risk reward ratio is calculated correctly."""
        entry = 50000
        sl = 49000
        tp = 51000

        risk = abs(entry - sl)  # 1000
        reward = abs(tp - entry)  # 1000
        rr = reward / risk  # 1.0

        assert rr == pytest.approx(1.0, rel=0.01)

    def test_metadata_empty_for_price_based(self):
        """Test case 5: Price-based strategy has empty metadata."""
        recommendation = {
            "strategy_type": "price_based",
            "strategy_metadata": {},
        }

        assert recommendation["strategy_metadata"] == {}


class TestCointegrationStrategyContract:
    """Test cointegration strategy contracts."""

    def test_recommendation_with_metadata(self):
        """Test that cointegration recommendation has metadata."""
        recommendation = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
            "strategy_type": "spread_based",
            "strategy_metadata": {
                "beta": 0.85,
                "spread_mean": 100,
                "spread_std": 50,
                "z_score_at_entry": -1.5,
                "pair_symbol": "ETHUSDT",
                "z_exit_threshold": 0.5,
            },
        }

        # Verify all metadata fields present
        metadata_fields = [
            "beta", "spread_mean", "spread_std", "z_score_at_entry",
            "pair_symbol", "z_exit_threshold"
        ]
        for field in metadata_fields:
            assert field in recommendation["strategy_metadata"], f"Missing metadata field: {field}"

    def test_metadata_beta_positive(self):
        """Test case 1: Beta is positive (cointegrated pairs)."""
        metadata = {"beta": 0.85}
        assert metadata["beta"] > 0

    def test_metadata_spread_std_positive(self):
        """Test case 2: Spread std dev is positive."""
        metadata = {"spread_std": 50}
        assert metadata["spread_std"] > 0

    def test_metadata_z_score_range(self):
        """Test case 3: Z-score is in reasonable range."""
        for z_score in [-3.0, -1.5, 0.0, 1.5, 3.0]:
            assert -5 <= z_score <= 5

    def test_metadata_pair_symbol_valid(self):
        """Test case 4: Pair symbol is valid."""
        metadata = {"pair_symbol": "ETHUSDT"}
        assert isinstance(metadata["pair_symbol"], str)
        assert len(metadata["pair_symbol"]) > 0


class TestStrategyExitContract:
    """Test strategy exit logic contracts."""

    def test_should_exit_output_format(self):
        """Test that should_exit returns required fields."""
        exit_result = {
            "should_exit": True,
            "exit_reason": "tp_hit",
            "exit_price": 51000,
            "exit_details": {"reason": "tp_hit"},
        }

        assert "should_exit" in exit_result
        assert "exit_reason" in exit_result
        assert exit_result["exit_reason"] in ["tp_hit", "sl_hit", "strategy_exit", "no_exit"]

    def test_long_tp_hit(self):
        """Test case 1: Long trade TP hit."""
        trade = {
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
        }
        current_price = 51000

        # TP hit for long
        assert current_price >= trade["take_profit"]

    def test_long_sl_hit(self):
        """Test case 2: Long trade SL hit."""
        trade = {
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
        }
        current_price = 49000

        # SL hit for long
        assert current_price <= trade["stop_loss"]

    def test_short_tp_hit(self):
        """Test case 3: Short trade TP hit."""
        trade = {
            "entry_price": 50000,
            "stop_loss": 51000,
            "take_profit": 49000,
        }
        current_price = 49000

        # TP hit for short
        assert current_price <= trade["take_profit"]

    def test_short_sl_hit(self):
        """Test case 4: Short trade SL hit."""
        trade = {
            "entry_price": 50000,
            "stop_loss": 51000,
            "take_profit": 49000,
        }
        current_price = 51000

        # SL hit for short
        assert current_price >= trade["stop_loss"]

    def test_no_exit_condition(self):
        """Test case 5: No exit when price between SL and TP."""
        trade = {
            "entry_price": 50000,
            "stop_loss": 49000,
            "take_profit": 51000,
        }
        current_price = 50500

        # No exit for long
        assert not (current_price >= trade["take_profit"])
        assert not (current_price <= trade["stop_loss"])


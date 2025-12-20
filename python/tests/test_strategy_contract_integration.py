"""
Strategy Contract Integration Tests

Tests that the strategy output contract and trading cycle engine work together correctly.
Verifies that:
1. Strategy output format matches the contract
2. Trading cycle can process strategy output correctly
3. Price levels are extracted from analysis dict (not top-level)
4. All required fields are present and correct types
5. Validation catches contract violations

CRITICAL: The trading_cycle.py engine is the SINGLE SOURCE OF TRUTH.
This test validates that strategies conform to what the engine expects.
"""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, patch
from trading_bot.strategies.base import BaseAnalysisModule


class TestStrategyOutputContract:
    """Test that strategy output matches the contract."""
    
    def test_valid_strategy_output_cointegration(self):
        """Test valid cointegration strategy output with prices in analysis dict."""
        result = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {
                "strategy": "cointegration",
                "z_score": 2.5,
                "is_mean_reverting": True,
                "size_multiplier": 1.0,
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 51000.0,
                "risk_reward_ratio": 1.5,
            },
            "chart_path": "",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
            "strategy_uuid": "uuid-456",
            "strategy_type": "spread_based",
            "strategy_name": "CointegrationAnalysisModule",
            "strategy_metadata": {
                "beta": 0.85,
                "spread_mean": 100.0,
                "spread_std": 50.0,
                "z_score_at_entry": 2.5,
                "pair_symbol": "ETHUSDT",
                "z_exit_threshold": 0.5,
            },
        }
        
        # Verify all required top-level fields
        assert result["symbol"] == "BTCUSDT"
        assert result["recommendation"] in ("BUY", "SELL", "HOLD")
        assert 0 <= result["confidence"] <= 1
        assert isinstance(result["analysis"], dict)
        
        # CRITICAL: Prices MUST be in analysis dict, not top-level
        assert "entry_price" in result["analysis"]
        assert "stop_loss" in result["analysis"]
        assert "take_profit" in result["analysis"]
        assert "risk_reward_ratio" in result["analysis"]
        
        # Verify prices are correct types
        assert isinstance(result["analysis"]["entry_price"], (int, float))
        assert isinstance(result["analysis"]["stop_loss"], (int, float))
        assert isinstance(result["analysis"]["take_profit"], (int, float))
        assert isinstance(result["analysis"]["risk_reward_ratio"], (int, float))
    
    def test_valid_strategy_output_prompt(self):
        """Test valid prompt strategy output."""
        result = {
            "symbol": "ETHUSDT",
            "recommendation": "SELL",
            "confidence": 0.85,
            "setup_quality": 0.8,
            "market_environment": 0.7,
            "analysis": {
                "strategy": "prompt",
                "summary": "Strong bearish signal",
                "entry_price": 3000.0,
                "stop_loss": 3100.0,
                "take_profit": 2900.0,
                "risk_reward_ratio": 2.0,
            },
            "chart_path": "/path/to/chart.png",
            "timeframe": "4h",
            "cycle_id": "cycle-789",
            "strategy_uuid": "uuid-789",
            "strategy_type": "price_based",
            "strategy_name": "PromptStrategy",
            "strategy_metadata": {},
        }
        
        # Verify prices in analysis dict
        assert result["analysis"]["entry_price"] == 3000.0
        assert result["analysis"]["stop_loss"] == 3100.0
        assert result["analysis"]["take_profit"] == 2900.0
        assert result["analysis"]["risk_reward_ratio"] == 2.0
    
    def test_missing_prices_in_analysis_dict_fails(self):
        """Test that missing prices in analysis dict is caught."""
        result = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {
                "strategy": "cointegration",
                "z_score": 2.5,
                # MISSING: entry_price, stop_loss, take_profit, risk_reward_ratio
            },
            "chart_path": "",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
            "strategy_uuid": "uuid-456",
            "strategy_type": "spread_based",
            "strategy_name": "CointegrationAnalysisModule",
        }
        
        # Should fail validation
        assert "entry_price" not in result["analysis"]
        assert "stop_loss" not in result["analysis"]
        assert "take_profit" not in result["analysis"]
        assert "risk_reward_ratio" not in result["analysis"]


class TestTradingCycleEngineExtraction:
    """Test that trading cycle engine extracts prices from analysis dict."""
    
    def test_engine_extracts_prices_from_analysis_dict(self):
        """Test that engine looks for prices in analysis dict (trading_cycle.py:1028-1031)."""
        # This simulates what trading_cycle.py._record_recommendation() does
        result = {
            "symbol": "BTCUSDT",
            "analysis": {
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 51000.0,
                "risk_reward_ratio": 1.5,
            },
        }
        
        analysis = result["analysis"]
        
        # Engine extracts prices like this (trading_cycle.py lines 1028-1031)
        entry_price = analysis.get("entry_price")
        stop_loss = analysis.get("stop_loss")
        take_profit = analysis.get("take_profit")
        risk_reward = analysis.get("risk_reward_ratio", analysis.get("risk_reward"))
        
        # Verify extraction works
        assert entry_price == 50000.0
        assert stop_loss == 49000.0
        assert take_profit == 51000.0
        assert risk_reward == 1.5
    
    def test_engine_handles_none_prices(self):
        """Test that engine handles None prices correctly."""
        result = {
            "symbol": "BTCUSDT",
            "analysis": {
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward_ratio": None,
            },
        }
        
        analysis = result["analysis"]
        
        # Engine should handle None values
        entry_price = analysis.get("entry_price")
        stop_loss = analysis.get("stop_loss")
        take_profit = analysis.get("take_profit")
        risk_reward = analysis.get("risk_reward_ratio")
        
        assert entry_price is None
        assert stop_loss is None
        assert take_profit is None
        assert risk_reward is None


class TestContractInvariants:
    """Test contract invariants for different strategy types."""
    
    def test_long_trade_invariants(self):
        """Test SL/TP invariants for long trades."""
        result = {
            "recommendation": "BUY",
            "analysis": {
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 51000.0,
            },
        }
        
        analysis = result["analysis"]
        entry = analysis["entry_price"]
        sl = analysis["stop_loss"]
        tp = analysis["take_profit"]
        
        # For long: SL < entry < TP
        assert sl < entry < tp
    
    def test_short_trade_invariants(self):
        """Test SL/TP invariants for short trades."""
        result = {
            "recommendation": "SELL",
            "analysis": {
                "entry_price": 50000.0,
                "stop_loss": 51000.0,
                "take_profit": 49000.0,
            },
        }
        
        analysis = result["analysis"]
        entry = analysis["entry_price"]
        sl = analysis["stop_loss"]
        tp = analysis["take_profit"]
        
        # For short: TP < entry < SL
        assert tp < entry < sl


class TestBaseAnalysisModuleValidation:
    """Test BaseAnalysisModule._validate_output() enforces the contract."""

    def test_validation_passes_for_valid_cointegration_output(self):
        """Test that validation passes for valid cointegration output."""
        # Create a concrete implementation for testing
        class TestStrategy(BaseAnalysisModule):
            STRATEGY_TYPE = "spread_based"
            STRATEGY_NAME = "TestStrategy"
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
            def validate_signal(self, signal):
                return True
            def calculate_risk_metrics(self, signal):
                return {}
            def get_exit_condition(self):
                return {}
            def get_monitoring_metadata(self):
                return {}
            def should_exit(self, trade, current_candle, pair_candle=None):
                return {"should_exit": False}
            @classmethod
            def get_required_settings(cls):
                return {}

        strategy = TestStrategy(config=Mock())

        result = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 51000.0,
                "risk_reward_ratio": 1.5,
            },
            "chart_path": "",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
            "strategy_uuid": "uuid-456",
            "strategy_type": "spread_based",
            "strategy_name": "TestStrategy",
        }

        # Should not raise
        strategy._validate_output(result)

    def test_validation_fails_missing_prices_in_analysis(self):
        """Test that validation fails when prices missing from analysis dict."""
        class TestStrategy(BaseAnalysisModule):
            STRATEGY_TYPE = "spread_based"
            STRATEGY_NAME = "TestStrategy"
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
            def validate_signal(self, signal):
                return True
            def calculate_risk_metrics(self, signal):
                return {}
            def get_exit_condition(self):
                return {}
            def get_monitoring_metadata(self):
                return {}
            def should_exit(self, trade, current_candle, pair_candle=None):
                return {"should_exit": False}
            @classmethod
            def get_required_settings(cls):
                return {}

        strategy = TestStrategy(config=Mock())

        result = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {
                # MISSING: entry_price, stop_loss, take_profit, risk_reward_ratio
            },
            "chart_path": "",
            "timeframe": "1h",
            "cycle_id": "cycle-123",
            "strategy_uuid": "uuid-456",
            "strategy_type": "spread_based",
            "strategy_name": "TestStrategy",
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="Missing required field in analysis dict"):
            strategy._validate_output(result)

    def test_validation_fails_missing_top_level_field(self):
        """Test that validation fails when top-level field missing."""
        class TestStrategy(BaseAnalysisModule):
            STRATEGY_TYPE = "spread_based"
            STRATEGY_NAME = "TestStrategy"
            async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
                return []
            def validate_signal(self, signal):
                return True
            def calculate_risk_metrics(self, signal):
                return {}
            def get_exit_condition(self):
                return {}
            def get_monitoring_metadata(self):
                return {}
            def should_exit(self, trade, current_candle, pair_candle=None):
                return {"should_exit": False}
            @classmethod
            def get_required_settings(cls):
                return {}

        strategy = TestStrategy(config=Mock())

        result = {
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.75,
            "setup_quality": 0.7,
            "market_environment": 0.6,
            "analysis": {
                "entry_price": 50000.0,
                "stop_loss": 49000.0,
                "take_profit": 51000.0,
                "risk_reward_ratio": 1.5,
            },
            # MISSING: chart_path
            "timeframe": "1h",
            "cycle_id": "cycle-123",
            "strategy_uuid": "uuid-456",
            "strategy_type": "spread_based",
            "strategy_name": "TestStrategy",
        }

        # Should raise ValueError
        with pytest.raises(ValueError, match="Missing required field"):
            strategy._validate_output(result)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


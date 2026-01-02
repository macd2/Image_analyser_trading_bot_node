"""
Tests for half-life estimation and divergence blowup exit features.
"""

import numpy as np
import pandas as pd
import logging
from unittest.mock import patch
import pytest
import sys
import os

# Add project to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))

from trading_bot.strategies.cointegration.spread_trading_cointegrated import estimate_half_life
from trading_bot.strategies.cointegration.cointegration_analysis_module import CointegrationAnalysisModule


class TestHalfLifeEstimation:
    """Test half-life estimation function."""

    def test_half_life_with_mean_reverting_spread(self):
        """Test half-life calculation with mean-reverting spread."""
        # Create synthetic mean-reverting spread
        np.random.seed(42)
        lambda_true = 0.05  # True mean reversion speed
        spread = [0]
        for _ in range(200):
            spread.append(spread[-1] * (1 - lambda_true) + np.random.normal(0, 0.1))
        
        half_life = estimate_half_life(np.array(spread))
        
        # Should return a finite positive value
        assert np.isfinite(half_life)
        assert half_life > 0
        # Expected half-life ≈ ln(2) / 0.05 ≈ 13.86
        assert 5 < half_life < 30  # Reasonable range

    def test_half_life_with_insufficient_samples(self, caplog):
        """Test half-life returns np.nan with insufficient samples."""
        spread = np.array([1.0, 2.0, 3.0])  # Only 3 samples, need 20
        
        with caplog.at_level(logging.WARNING):
            half_life = estimate_half_life(spread, min_samples=20)
        
        assert np.isnan(half_life)
        assert any("Insufficient samples" in record.message for record in caplog.records)

    def test_half_life_with_zero_variance(self, caplog):
        """Test half-life returns np.nan with zero variance."""
        spread = np.array([1.0] * 50)  # Constant spread
        
        with caplog.at_level(logging.WARNING):
            half_life = estimate_half_life(spread)
        
        assert np.isnan(half_life)
        assert any("Zero variance" in record.message for record in caplog.records)

    def test_half_life_with_non_stationary_spread(self, caplog):
        """Test half-life with non-stationary spread."""
        # Create trending (non-stationary) spread
        spread = np.cumsum(np.random.normal(0.1, 0.1, 100))

        with caplog.at_level(logging.WARNING):
            half_life = estimate_half_life(spread)

        # Should return a value (may be finite or inf depending on regression)
        # The important thing is it doesn't crash and logs appropriately
        assert isinstance(half_life, (float, np.floating))

    def test_half_life_with_pandas_series(self):
        """Test half-life works with pandas Series."""
        np.random.seed(42)
        lambda_true = 0.05
        spread = [0]
        for _ in range(200):
            spread.append(spread[-1] * (1 - lambda_true) + np.random.normal(0, 0.1))
        
        series = pd.Series(spread)
        half_life = estimate_half_life(series)
        
        assert np.isfinite(half_life)
        assert half_life > 0


class TestDivergenceBlowupExit:
    """Test divergence blowup exit logic."""

    def test_divergence_blowup_triggers_exit(self, caplog):
        """Test divergence blowup triggers exit when threshold exceeded."""
        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'):
            strategy = CointegrationAnalysisModule(config={})
        
        trade = {
            "id": "test_trade",
            "symbol": "BTCUSDT",
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 0.5,
                "z_score_at_entry": 2.0,  # Entered at z=2.0
                "pair_symbol": "ETHUSDT",
                "max_spread_deviation": 3.0,
            }
        }
        
        # Current z-score is 6.5, divergence = |6.5 - 2.0| = 4.5 > 4.0 threshold
        current_candle = {"close": 100.0}
        pair_candle = {"close": 106.5}  # This will result in z=6.5
        
        with caplog.at_level(logging.WARNING):
            result = strategy.should_exit(trade, current_candle, pair_candle)
        
        assert result["should_exit"] == True
        assert result["exit_details"]["reason"] == "divergence_blowup"
        assert result["exit_details"]["divergence_exceeded"] == True
        assert any("Divergence blowup" in record.message for record in caplog.records)

    def test_divergence_check_disabled(self):
        """Test divergence check can be disabled."""
        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'):
            strategy = CointegrationAnalysisModule(
                config={},
                strategy_config={"enable_divergence_check": False}
            )
        
        trade = {
            "id": "test_trade",
            "symbol": "BTCUSDT",
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 0.5,
                "z_score_at_entry": 2.0,
                "pair_symbol": "ETHUSDT",
                "max_spread_deviation": 3.0,
            }
        }
        
        current_candle = {"close": 100.0}
        pair_candle = {"close": 106.5}  # Would trigger divergence if enabled
        
        result = strategy.should_exit(trade, current_candle, pair_candle)
        
        # Should not exit due to divergence (check disabled)
        assert result["exit_details"]["reason"] != "divergence_blowup"

    def test_divergence_within_threshold_no_exit(self):
        """Test no exit when divergence is within threshold."""
        with patch('trading_bot.strategies.base.BaseAnalysisModule._init_candle_adapter'):
            strategy = CointegrationAnalysisModule(config={})
        
        trade = {
            "id": "test_trade",
            "symbol": "BTCUSDT",
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 0.5,
                "z_score_at_entry": 2.0,
                "pair_symbol": "ETHUSDT",
                "max_spread_deviation": 3.0,
            }
        }
        
        # Current z-score is 4.5, divergence = |4.5 - 2.0| = 2.5 < 4.0 threshold
        current_candle = {"close": 100.0}
        pair_candle = {"close": 104.5}
        
        result = strategy.should_exit(trade, current_candle, pair_candle)
        
        # Should not exit due to divergence (within threshold)
        assert result["exit_details"]["reason"] != "divergence_blowup"


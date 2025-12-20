"""
Test cointegration strategy spread level calculations.

Validates that spread levels are correctly calculated and converted to Y prices
for database storage. The cointegration strategy trades the SPREAD, not individual
assets, so exit logic uses z-score monitoring, not price levels.
"""

import pytest
import sys
from pathlib import Path

# Add python directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.strategies.cointegration.price_levels import calculate_levels


class TestCointegrationSpreadLevels:
    """Test spread level calculations for cointegration strategy."""

    def test_short_spread_levels_calculation(self):
        """
        Test SHORT spread level calculation.
        
        For SHORT spread (z >= +2.0):
        - Spread is ABOVE mean (overvalued)
        - Entry at +2σ above mean
        - SL further above mean (adaptive)
        - TP at mean (full reversion)
        """
        spread_mean = 0.536
        spread_std = 0.035
        z_entry = 2.0
        
        levels = calculate_levels(
            price_x=0.20,
            price_y=1.50,
            beta=-3.15,
            spread_mean=spread_mean,
            spread_std=spread_std,
            z_entry=z_entry,
            signal=-1,  # SHORT spread
            min_sl_buffer=1.5
        )
        
        spread_levels = levels['spread_levels']
        
        # For SHORT: entry > mean > tp
        assert spread_levels['entry'] > spread_mean, \
            f"SHORT entry {spread_levels['entry']} should be > mean {spread_mean}"
        assert spread_levels['stop_loss'] > spread_levels['entry'], \
            f"SHORT SL {spread_levels['stop_loss']} should be > entry {spread_levels['entry']}"
        assert spread_levels['take_profit_2'] == spread_mean, \
            f"SHORT TP should equal mean {spread_mean}"
        
        print(f"\nShort Spread Levels:")
        print(f"  Entry: {spread_levels['entry']:.6f} (at +{z_entry}σ)")
        print(f"  SL: {spread_levels['stop_loss']:.6f} (adaptive)")
        print(f"  TP: {spread_levels['take_profit_2']:.6f} (at mean)")

    def test_long_spread_levels_calculation(self):
        """
        Test LONG spread level calculation.
        
        For LONG spread (z <= -2.0):
        - Spread is BELOW mean (undervalued)
        - Entry at -2σ below mean
        - SL further below mean (adaptive)
        - TP at mean (full reversion)
        """
        spread_mean = 0.536
        spread_std = 0.035
        z_entry = 2.0
        
        levels = calculate_levels(
            price_x=0.20,
            price_y=1.50,
            beta=-3.15,
            spread_mean=spread_mean,
            spread_std=spread_std,
            z_entry=z_entry,
            signal=1,  # LONG spread
            min_sl_buffer=1.5
        )
        
        spread_levels = levels['spread_levels']
        
        # For LONG: entry < mean < tp
        assert spread_levels['entry'] < spread_mean, \
            f"LONG entry {spread_levels['entry']} should be < mean {spread_mean}"
        assert spread_levels['stop_loss'] < spread_levels['entry'], \
            f"LONG SL {spread_levels['stop_loss']} should be < entry {spread_levels['entry']}"
        assert spread_levels['take_profit_2'] == spread_mean, \
            f"LONG TP should equal mean {spread_mean}"
        
        print(f"\nLong Spread Levels:")
        print(f"  Entry: {spread_levels['entry']:.6f} (at -{z_entry}σ)")
        print(f"  SL: {spread_levels['stop_loss']:.6f} (adaptive)")
        print(f"  TP: {spread_levels['take_profit_2']:.6f} (at mean)")

    def test_spread_levels_are_primary_trading_levels(self):
        """
        Test that spread levels are the primary trading levels.

        The cointegration strategy trades the SPREAD, not individual assets.
        Exit logic uses z-score monitoring, not price levels.

        Spread levels are stored for informational purposes, but actual
        trade management is done via z-score calculation:
        z = (current_spread - spread_mean) / spread_std
        """
        spread_mean = 0.536
        spread_std = 0.035

        levels = calculate_levels(
            price_x=0.20,
            price_y=1.50,
            beta=-3.15,
            spread_mean=spread_mean,
            spread_std=spread_std,
            z_entry=2.0,
            signal=-1,  # SHORT spread
            min_sl_buffer=1.5
        )

        spread_levels = levels['spread_levels']

        # Verify spread levels are in spread space
        print(f"\nSpread Levels (PRIMARY TRADING LEVELS):")
        print(f"  Entry: {spread_levels['entry']:.6f}")
        print(f"  SL: {spread_levels['stop_loss']:.6f}")
        print(f"  TP: {spread_levels['take_profit_2']:.6f}")
        print(f"  Mean: {spread_mean:.6f}")

        # For SHORT spread: entry > mean > tp
        assert spread_levels['entry'] > spread_mean
        assert spread_levels['stop_loss'] > spread_levels['entry']
        assert spread_levels['take_profit_2'] == spread_mean

        # Exit logic will check: if current_spread <= z_exit_threshold
        # These spread levels are reference points, not hard stops


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


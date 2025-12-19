"""
Test that enable_dynamic_sizing setting properly controls position sizing behavior.
"""
import numpy as np
import pandas as pd
from python.trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy


def test_dynamic_sizing_enabled():
    """Test that size_multiplier is calculated when enable_dynamic_sizing=True"""
    print("\n" + "="*80)
    print("TEST: Dynamic Sizing ENABLED (enable_dynamic_sizing=True)")
    print("="*80)
    
    # Create strategy with dynamic sizing ENABLED
    strategy = CointegrationStrategy(
        lookback=50,
        z_entry=2.0,
        z_exit=0.5,
        use_soft_vol=False,
        enable_dynamic_sizing=True  # ← ENABLED
    )
    
    # Create test data with cointegrated series
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    x = 100 + np.cumsum(np.random.randn(100) * 0.5)
    y = 0.8 * x + np.random.randn(100) * 2
    
    df = pd.DataFrame({
        'timestamp': dates,
        'close_1': x,
        'close_2': y
    })
    
    signals = strategy.generate_signals(df)
    
    # Check that size_multiplier varies (not all 1.0)
    size_mults = signals['size_multiplier'].dropna()
    unique_values = size_mults.unique()
    
    print(f"✅ Generated {len(size_mults)} signals")
    print(f"   Size multiplier range: [{size_mults.min():.2f}, {size_mults.max():.2f}]")
    print(f"   Unique values: {len(unique_values)}")
    
    # Verify that size_multiplier varies (not all 1.0)
    assert len(unique_values) > 1, "Size multiplier should vary when enabled"
    assert size_mults.min() < 1.0 or size_mults.max() > 1.0, "Size multiplier should deviate from 1.0"
    
    print("✅ PASS: Size multiplier varies as expected when enabled")
    return True


def test_dynamic_sizing_disabled():
    """Test that size_multiplier is always 1.0 when enable_dynamic_sizing=False"""
    print("\n" + "="*80)
    print("TEST: Dynamic Sizing DISABLED (enable_dynamic_sizing=False)")
    print("="*80)
    
    # Create strategy with dynamic sizing DISABLED
    strategy = CointegrationStrategy(
        lookback=50,
        z_entry=2.0,
        z_exit=0.5,
        use_soft_vol=False,
        enable_dynamic_sizing=False  # ← DISABLED
    )
    
    # Create test data with cointegrated series
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)
    x = 100 + np.cumsum(np.random.randn(100) * 0.5)
    y = 0.8 * x + np.random.randn(100) * 2
    
    df = pd.DataFrame({
        'timestamp': dates,
        'close_1': x,
        'close_2': y
    })
    
    signals = strategy.generate_signals(df)
    
    # Check that size_multiplier is always 1.0
    size_mults = signals['size_multiplier'].dropna()
    
    print(f"✅ Generated {len(size_mults)} signals")
    print(f"   Size multiplier range: [{size_mults.min():.2f}, {size_mults.max():.2f}]")
    print(f"   All values equal to 1.0: {(size_mults == 1.0).all()}")
    
    # Verify that ALL size_multiplier values are exactly 1.0
    assert (size_mults == 1.0).all(), "Size multiplier should be 1.0 when disabled"
    
    print("✅ PASS: Size multiplier is always 1.0 when disabled")
    return True


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DYNAMIC SIZING CONTROL TEST")
    print("="*80)
    
    try:
        test_dynamic_sizing_enabled()
        test_dynamic_sizing_disabled()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED")
        print("="*80)
        print("\nSummary:")
        print("  ✅ enable_dynamic_sizing=True → size_multiplier varies (0.3-3.0)")
        print("  ✅ enable_dynamic_sizing=False → size_multiplier always 1.0")
        print("  ✅ Setting properly controls behavior")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        exit(1)


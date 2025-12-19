"""
Test to verify z_entry threshold issue with SpreadTrader settings.

SpreadTrader uses z_entry=3.0, which is VERY STRICT.
This test uses synthetic data to show the problem.
"""
import sys
sys.path.insert(0, 'python')

import numpy as np
import pandas as pd
from trading_bot.strategies.cointegration.spread_trading_cointegrated import CointegrationStrategy

def test_z_entry_threshold():
    """Test signal generation with different z_entry values."""
    
    print("📊 Testing Z-Entry Threshold Issue")
    print("=" * 70)
    
    # Create synthetic cointegrated pair
    np.random.seed(42)
    n = 200
    
    # Create two correlated series
    x = np.cumsum(np.random.randn(n) * 0.5)
    y = x + np.random.randn(n) * 0.3  # y = x + noise (cointegrated)
    
    df = pd.DataFrame({
        'close_1': x,
        'close_2': y,
    })
    
    print(f"\n✅ Created synthetic pair with {len(df)} candles")
    print(f"   Correlation: {np.corrcoef(x, y)[0,1]:.3f}")
    
    # Test with different z_entry values
    z_entry_values = [1.5, 2.0, 2.5, 3.0]
    
    for z_entry in z_entry_values:
        strategy = CointegrationStrategy(
            lookback=120,
            z_entry=z_entry,
            z_exit=0.5,
            use_adf=True,
            use_soft_vol=False
        )
        
        signals = strategy.generate_signals(df)
        valid_signals = signals[signals['z_score'].notna()]
        
        # Count signals
        buy_signals = (valid_signals['signal'] == 1).sum()
        sell_signals = (valid_signals['signal'] == -1).sum()
        total_signals = buy_signals + sell_signals
        
        # Count z-scores exceeding threshold
        exceed_count = ((valid_signals['z_score'] >= z_entry) | (valid_signals['z_score'] <= -z_entry)).sum()
        
        # Count mean-reverting
        mr_count = valid_signals['is_mean_reverting'].sum()
        
        print(f"\n📈 z_entry = {z_entry}:")
        print(f"   Z-scores exceeding threshold: {exceed_count}/{len(valid_signals)} ({100*exceed_count/len(valid_signals):.1f}%)")
        print(f"   Mean-reverting: {mr_count}/{len(valid_signals)} ({100*mr_count/len(valid_signals):.1f}%)")
        print(f"   Signals generated: {total_signals} (BUY: {buy_signals}, SELL: {sell_signals})")
        print(f"   Z-score range: [{valid_signals['z_score'].min():.2f}, {valid_signals['z_score'].max():.2f}]")
        
        if total_signals == 0:
            print(f"   ⚠️  NO SIGNALS! z_entry={z_entry} is too strict!")
    
    print("\n" + "=" * 70)
    print("💡 Conclusion:")
    print("   SpreadTrader uses z_entry=3.0, which is VERY STRICT")
    print("   Most pairs won't generate signals with this threshold")
    print("   Consider lowering z_entry to 2.0-2.5 for more signals")

if __name__ == "__main__":
    test_z_entry_threshold()


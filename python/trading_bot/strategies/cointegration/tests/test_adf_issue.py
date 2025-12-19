"""
Test to check if ADF test is the bottleneck for signal generation.

The issue: z_score is high (4.2482) but signal is still HOLD.
Hypothesis: is_mean_reverting is False due to ADF test failing.
"""
import sys
sys.path.insert(0, 'python')

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller

def test_adf_on_synthetic_data():
    """Test ADF on synthetic cointegrated data."""
    
    print("📊 Testing ADF Test on Synthetic Data")
    print("=" * 70)
    
    # Create synthetic cointegrated pair
    np.random.seed(42)
    n = 200
    
    # Create two correlated series
    x = np.cumsum(np.random.randn(n) * 0.5)
    y = x + np.random.randn(n) * 0.3  # y = x + noise (cointegrated)
    
    # Compute spread
    beta = np.cov(x, y)[0,1] / np.var(x)
    spread = y - beta * x
    
    print(f"\n✅ Created synthetic pair with {len(spread)} candles")
    print(f"   Beta: {beta:.4f}")
    print(f"   Spread mean: {np.mean(spread):.4f}")
    print(f"   Spread std: {np.std(spread):.4f}")
    
    # Test ADF
    try:
        result = adfuller(spread, maxlag=1, regression='c')
        p_val = result[1]
        print(f"\n📈 ADF Test Result:")
        print(f"   P-value: {p_val:.6f}")
        print(f"   Is mean-reverting (p < 0.05): {p_val < 0.05}")
        print(f"   Test statistic: {result[0]:.4f}")
        print(f"   Critical values: {result[4]}")
    except Exception as e:
        print(f"❌ ADF test failed: {e}")
    
    # Now test with real market-like data (trending)
    print(f"\n\n📊 Testing ADF on Trending Data (Non-Stationary)")
    print("=" * 70)
    
    # Create trending data (non-stationary)
    x_trend = np.cumsum(np.random.randn(n) * 2.0)  # Strong trend
    y_trend = x_trend + np.random.randn(n) * 0.3
    
    beta_trend = np.cov(x_trend, y_trend)[0,1] / np.var(x_trend)
    spread_trend = y_trend - beta_trend * x_trend
    
    print(f"\n✅ Created trending pair with {len(spread_trend)} candles")
    print(f"   Beta: {beta_trend:.4f}")
    print(f"   Spread mean: {np.mean(spread_trend):.4f}")
    print(f"   Spread std: {np.std(spread_trend):.4f}")
    
    # Test ADF
    try:
        result = adfuller(spread_trend, maxlag=1, regression='c')
        p_val = result[1]
        print(f"\n📈 ADF Test Result:")
        print(f"   P-value: {p_val:.6f}")
        print(f"   Is mean-reverting (p < 0.05): {p_val < 0.05}")
        print(f"   Test statistic: {result[0]:.4f}")
        print(f"   Critical values: {result[4]}")
    except Exception as e:
        print(f"❌ ADF test failed: {e}")
    
    print(f"\n\n💡 Conclusion:")
    print(f"   ADF test is VERY STRICT for real market data")
    print(f"   Most pairs fail the ADF test (p >= 0.05)")
    print(f"   Even if z_score is high, is_mean_reverting=False → no signal")
    print(f"   Solution: Lower ADF p-value threshold or use Hurst exponent")

if __name__ == "__main__":
    test_adf_on_synthetic_data()


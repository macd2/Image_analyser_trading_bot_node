"""
Pair Screener - Find cointegrated trading pairs from available symbols.

Screens for cointegrated pairs using:
1. Correlation filter (0.3 < corr < 0.9)
2. ADF test (p < 0.05)
3. Hurst exponent (< 0.5 = mean-reverting)
4. Economic filters (half-life < 15, CV < 0.8)
5. Confidence scoring
"""

import numpy as np
import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from statsmodels.tsa.stattools import adfuller
from statsmodels.regression.linear_model import OLS
import statsmodels.api as sm
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


def candles_to_series(candles: list) -> pd.Series:
    """Convert Bybit candle list to close price series."""
    if not candles:
        return pd.Series(dtype=float)

    # Handle both list and dict formats
    if isinstance(candles[0], list):
        close_prices = [float(c[4]) for c in candles]
        timestamps = [int(c[0]) for c in candles]
    else:  # dict format
        close_prices = [float(c['close']) for c in candles]
        timestamps = [int(c.get('start', c.get('timestamp', 0))) for c in candles]

    return pd.Series(close_prices, index=pd.to_datetime(timestamps, unit='ms')).sort_index()


def estimate_half_life(spread: np.ndarray) -> float:
    """Estimate half-life of mean reversion (Ornstein-Uhlenbeck)."""
    if len(spread) < 10:
        return np.inf
    try:
        lag = np.roll(spread, 1)
        lag[0] = lag[1]
        returns = spread - lag
        model = OLS(returns[1:], sm.add_constant(lag[1:])).fit()
        theta = model.params[1]
        if theta >= 0:
            return np.inf
        return -np.log(2) / theta
    except:
        return np.inf


def compute_hurst(spread: np.ndarray, max_lag: int = 20) -> float:
    """Hurst exponent via R/S analysis. Returns value in [0, 1]."""
    if len(spread) < 50:
        return 0.5
    lags = range(2, min(max_lag, len(spread) // 2))
    if len(lags) < 2:
        return 0.5
    tau = [np.std(np.subtract(spread[lag:], spread[:-lag])) for lag in lags]
    with np.errstate(divide='ignore', invalid='ignore'):
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
    hurst = poly[0] * 2.0 if not np.isnan(poly[0]) else 0.5
    # Clamp to [0, 1] range
    return np.clip(hurst, 0.0, 1.0)


def compute_beta(x: np.ndarray, y: np.ndarray) -> float:
    """Robust OLS hedge ratio."""
    if len(x) < 10 or np.var(x) < 1e-10:
        return 1.0
    try:
        model = OLS(y, sm.add_constant(x)).fit()
        return model.params[1]
    except:
        return np.cov(x, y)[0, 1] / (np.var(x) + 1e-10)


class PairScreener:
    """Screen for cointegrated pairs from candle data."""

    def __init__(self, lookback_days: int = 120, min_data_points: int = 120):
        """
        Initialize screener.

        Args:
            lookback_days: Rolling window for stats (trading days)
            min_data_points: Min candles required per asset
        """
        self.lookback_days = lookback_days
        self.min_data_points = min_data_points

    def screen_pairs(
        self,
        symbol_candles: Dict[str, list],
        min_volume_usd: float = 1_000_000,
        max_pairs: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Screen for cointegrated pairs from Bybit candle data.

        Args:
            symbol_candles: {symbol: list_of_candles}
            min_volume_usd: Min avg daily volume (filters illiquid assets)
            max_pairs: Max pairs to return

        Returns:
            DataFrame with cointegrated pairs sorted by confidence_score
        """
        # ── 1. Preprocess & filter assets ──
        assets = {}
        for symbol, candles in symbol_candles.items():
            if len(candles) < self.min_data_points:
                continue

            series = candles_to_series(candles)
            if len(series) < self.min_data_points:
                continue

            # Estimate daily volume (assume candles are 1h → sum 24h)
            try:
                if isinstance(candles[0], list):
                    volumes = [float(c[5]) * float(c[4]) for c in candles]
                else:
                    volumes = [float(c['volume']) * float(c['close']) for c in candles]
                avg_daily_vol = np.mean(volumes) * 24
                if avg_daily_vol < min_volume_usd:
                    logger.debug(f"Skipping {symbol}: volume {avg_daily_vol:.0f} < {min_volume_usd:.0f}")
                    continue
            except:
                pass

            assets[symbol] = series

        if len(assets) < 2:
            logger.warning(f"Not enough assets: {len(assets)}")
            return pd.DataFrame()

        logger.info(f"Screening {len(assets)} assets")

        # ── 2. Align time series ──
        all_dates = sorted(set().union(*[s.index for s in assets.values()]))
        aligned = {}
        for symbol, series in assets.items():
            aligned[symbol] = series.reindex(all_dates, method='ffill').dropna()

        # Keep only last `lookback_days` points
        recent_dates = sorted(aligned[list(aligned.keys())[0]].index)[-self.lookback_days:]
        for symbol in aligned:
            aligned[symbol] = aligned[symbol].loc[recent_dates]

        # ── 3. Screen pairs ──
        results = []
        symbols = list(aligned.keys())
        total_pairs = len(symbols) * (len(symbols) - 1) // 2
        logger.info(f"Screening {total_pairs} pairs")

        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                sym1, sym2 = symbols[i], symbols[j]
                x = aligned[sym1].values
                y = aligned[sym2].values

                if len(x) < 50 or len(y) < 50:
                    continue

                try:
                    # Correlation filter
                    corr = np.corrcoef(x, y)[0, 1]
                    if not (0.3 < corr < 0.9):
                        continue

                    # Compute hedge ratio & spread
                    beta = compute_beta(x, y)
                    spread = y - beta * x

                    # ADF test
                    try:
                        adf_p = adfuller(spread, maxlag=1, regression='c')[1]
                    except:
                        adf_p = 1.0

                    # Hurst exponent
                    hurst = compute_hurst(spread)

                    # Half-life
                    half_life = estimate_half_life(spread)

                    # Coefficient of variation
                    spread_mean = np.mean(spread)
                    spread_std = np.std(spread)
                    cv = spread_std / (abs(spread_mean) + 1e-10)

                    # Economic filters
                    if not (adf_p < 0.05 and hurst < 0.5 and half_life <= 15 and cv < 0.8):
                        continue

                    # Confidence score (0-1)
                    # Each component is clamped to [0, 1] before weighting
                    c1 = np.clip(1.0 - adf_p, 0.0, 1.0)  # stationarity
                    c2 = np.clip(1.0 - hurst, 0.0, 1.0)  # mean-reversion strength
                    c3 = np.clip(1.0 - cv, 0.0, 1.0)     # spread stability
                    confidence = np.clip(0.4 * c1 + 0.3 * c2 + 0.3 * c3, 0.0, 1.0)

                    results.append({
                        'pair': f"{sym2}/{sym1}",
                        'symbol1': sym1,
                        'symbol2': sym2,
                        'adf_p': adf_p,
                        'hurst': hurst,
                        'half_life': half_life,
                        'cv': cv,
                        'beta': beta,
                        'correlation': corr,
                        'confidence_score': confidence
                    })

                except Exception as e:
                    logger.debug(f"Error screening {sym1}/{sym2}: {e}")
                    continue

        if not results:
            logger.warning("No cointegrated pairs found")
            return pd.DataFrame()

        df = pd.DataFrame(results).sort_values('confidence_score', ascending=False).reset_index(drop=True)

        if max_pairs:
            df = df.head(max_pairs)

        logger.info(f"Found {len(df)} cointegrated pairs")
        return df


import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller
from statsmodels.regression.linear_model import OLS
import warnings
warnings.filterwarnings('ignore')


def calculate_dynamic_position(
    portfolio_value: float,
    risk_percent: float,
    z_entry: float,
    z_score_current: float,
    spread_mean: float,
    spread_std: float,
    beta: float,
    signal: int,
    z_history: list,
    confidence: float = 1.0
):
    """
    Calculate dynamic position size for spread-based trading.

    Integrated dynamic stop + sizing for cointegration strategies.

    Args:
        portfolio_value: Total portfolio value in USD
        risk_percent: Risk percentage per trade (e.g., 0.02 for 2%)
        z_entry: Z-score at entry (e.g., 2.0)
        z_score_current: Current z-score (for confidence adjustment)
        spread_mean: Mean of the spread
        spread_std: Standard deviation of the spread
        beta: Hedge ratio between the two symbols
        signal: Trade signal (-1 for short spread, 1 for long spread)
        z_history: Historical z-scores for adaptive stop calculation
        confidence: Confidence multiplier (0.5-1.5)

    Returns:
        Dict with:
            - units_y: Quantity for Y symbol (pair symbol)
            - units_x: Quantity for X symbol (main symbol)
            - spread_entry: Entry spread level
            - spread_sl: Stop loss spread level
            - z_sl: Z-score stop loss threshold
            - spread_risk_usd: Risk amount in USD
            - spread_risk_units: Risk in spread units
    """
    # 1. Calculate adaptive stop loss
    z_sl_min = z_entry + 1.5

    # TASK 1.4 & 6: NO FALLBACK - z_history must be provided
    if not z_history or len(z_history) == 0:
        error_msg = (
            f"CRITICAL: Empty z_history for position sizing. "
            f"Cannot calculate adaptive stop loss without historical z-scores."
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.critical(error_msg)
        raise ValueError(error_msg)

    z_99 = np.percentile([abs(z) for z in z_history], 99)
    z_sl = max(z_sl_min, z_99)

    # 2. Compute spread levels based on signal direction
    if signal == -1:  # Short spread (sell Y, buy X)
        spread_entry = spread_mean + z_entry * spread_std
        spread_sl = spread_mean + z_sl * spread_std
    else:  # Long spread (buy Y, sell X)
        spread_entry = spread_mean - z_entry * spread_std
        spread_sl = spread_mean - z_sl * spread_std

    # 3. Risk in spread units
    spread_risk = abs(spread_sl - spread_entry)

    # 4. Base position size
    risk_usd = portfolio_value * risk_percent * confidence
    units_y = risk_usd / spread_risk if spread_risk > 0 else 0
    units_x = units_y * abs(beta)

    # 5. Apply direction
    if signal == -1:  # Short spread
        units_y = -units_y  # Sell Y
        # units_x positive (buy X)
    else:  # Long spread
        # units_y positive (buy Y)
        units_x = -units_x  # Sell X

    return {
        "units_y": units_y,
        "units_x": units_x,
        "spread_entry": spread_entry,
        "spread_sl": spread_sl,
        "z_sl": z_sl,
        "spread_risk_usd": risk_usd,
        "spread_risk_units": spread_risk
    }


class CointegrationStrategy:
    """
    Cointegration-based mean-reversion strategy with dynamic sizing.
    
    Matches Pine Script logic:
    - Single-entry per cycle
    - Volatility-adjusted sizing (0.3x–3.0x or 0.5x–2.5x)
    - Hurst/ADF for regime filter
    """
    
    def __init__(self,
                 lookback: int = 120,
                 z_entry: float = 2.0,
                 z_exit: float = 0.5,
                 base_multiplier: float = 1.0,
                 use_soft_vol: bool = False,
                 use_adf: bool = True,
                 enable_dynamic_sizing: bool = True):
        """
        Parameters:
        -----------
        lookback : int
            Rolling window for stats (days)
        z_entry : float
            |z-score| threshold to enter
        z_exit : float
            |z-score| threshold to exit
        base_multiplier : float
            Base risk scaling factor
        use_soft_vol : bool
            Softer volatility scaling (0.5x–2.5x)
        use_adf : bool
            Use ADF test (True) or Hurst (False) for stationarity
        enable_dynamic_sizing : bool
            Enable dynamic position sizing based on edge and volatility
        """
        self.lookback = lookback
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.base_multiplier = base_multiplier
        self.use_soft_vol = use_soft_vol
        self.use_adf = use_adf
        self.enable_dynamic_sizing = enable_dynamic_sizing
        
        # State
        self.in_long = False
        self.in_short = False
        self.beta = 1.0
        self.spread_mean = 0.0
        self.spread_std = 1.0
    
    def _compute_hurst(self, series: np.ndarray) -> float:
        """Hurst exponent: <0.5 = mean-reverting"""
        if len(series) < 50:
            return 0.5
        lags = [2, 4, 8, 16, 32]
        tau = [np.std(np.subtract(series[lag:], series[:-lag])) for lag in lags]
        with np.errstate(divide='ignore', invalid='ignore'):
            poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0] * 2.0 if not np.isnan(poly[0]) else 0.5
    
    def _is_mean_reverting(self, spread: np.ndarray) -> bool:
        """Check stationarity: ADF (preferred) or Hurst"""
        if self.use_adf and len(spread) >= 20:
            try:
                p_val = adfuller(spread, maxlag=1, regression='c')[1]
                return p_val < 0.05
            except:
                pass
        # Fallback to Hurst
        hurst = self._compute_hurst(spread)
        return hurst < 0.5
    
    def _compute_beta(self, x: np.ndarray, y: np.ndarray) -> float:
        """OLS hedge ratio: y = βx + α"""
        if len(x) < 10:
            return 1.0
        try:
            model = OLS(y, sm.add_constant(x)).fit()
            return model.params[1]
        except:
            return np.cov(x, y)[0,1] / np.var(x) if np.var(x) > 1e-8 else 1.0
    

    def compute_confidence(self, spread: np.ndarray, z_score: float) -> float:
        """Compute mathematically sound confidence score [0, 1]"""
        if len(spread) < 20:
            return 0.5  # Not enough data
        
        # Tier 1: Stationarity (ADF p-value)
        try:
            p_adf = adfuller(spread, maxlag=1, regression='c')[1]
            C1 = max(0.0, 1.0 - p_adf)  # Clip to [0,1]
        except:
            C1 = 0.5  # Fallback
        
        # Tier 2: Edge strength (normalized z-score)
        recent_z = self.z_history[-30:] if hasattr(self, 'z_history') else [z_score]
        z_max = max(abs(z) for z in ([z_score] + recent_z))
        z_min = self.z_entry  # e.g., 2.0
        C2 = min(1.0, abs(z_score) / max(z_max, z_min))
        
        # Tier 3: Spread stability (1 / CV)
        mu = np.mean(spread)
        sigma = np.std(spread)
        cv = sigma / (abs(mu) + 1e-8)
        C3 = min(1.0, 1.0 / (cv + 1e-8))
        
        # Composite (weights sum to 1)
        confidence = 0.4 * C1 + 0.3 * C2 + 0.3 * C3
        return np.clip(confidence, 0.0, 1.0)


    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate signals for DataFrame with columns:
        ['timestamp', 'close_1', 'close_2']
        
        Returns:
        --------
        DataFrame with added columns:
        - 'z_score'
        - 'is_mean_reverting'
        - 'size_multiplier'
        - 'signal' (1=long, -1=short, 0=flat)
        - 'exit_signal' (bool)
        """
        # Ensure required columns
        required = ['close_1', 'close_2']
        if not all(col in df.columns for col in required):
            raise ValueError(f"DataFrame must contain: {required}")
        
        # Initialize output
        signals = pd.DataFrame(index=df.index)
        signals['z_score'] = np.nan
        signals['is_mean_reverting'] = False
        signals['size_multiplier'] = 1.0
        signals['signal'] = 0
        signals['exit_signal'] = False
        
        # Rolling computation
        for i in range(self.lookback, len(df)):
            window = df.iloc[i-self.lookback:i+1]
            p1 = window['close_1'].values
            p2 = window['close_2'].values
            
            # Compute beta & spread
            beta = self._compute_beta(p1, p2)
            spread = p2 - beta * p1
            
            # Stats
            spread_mean = np.mean(spread)
            spread_std = np.std(spread)
            if spread_std < 1e-8:
                continue
                
            z_score = (spread[-1] - spread_mean) / spread_std
            confidence = self.compute_confidence(spread, z_score)

            signals.at[df.index[i], 'z_score'] = z_score
            
            # Regime filter
            is_mr = self._is_mean_reverting(spread)
            signals.at[df.index[i], 'is_mean_reverting'] = is_mr
            
            if not is_mr:
                continue
            
            # Dynamic sizing
            if self.enable_dynamic_sizing:
                spread_mean_abs = abs(spread_mean) + 1e-8
                vol_ratio = spread_std / spread_mean_abs
                vol_adjust = (1.0 / np.sqrt(vol_ratio) if self.use_soft_vol
                             else 1.0 / vol_ratio)
                vol_adjust = min(vol_adjust, 1.8 if self.use_soft_vol else 2.0)

                edge_adjust = 1.0 + max(0, abs(z_score) - self.z_entry) * 0.5
                size_mult = self.base_multiplier * edge_adjust * vol_adjust
                size_mult = (
                    np.clip(size_mult, 0.5, 2.5) if self.use_soft_vol
                    else np.clip(size_mult, 0.3, 3.0)
                )
            else:
                size_mult = 1.0
            signals.at[df.index[i], 'size_multiplier'] = size_mult
            
            # State-based signals
            long_cond = (z_score <= -self.z_entry) and is_mr
            short_cond = (z_score >= self.z_entry) and is_mr
            exit_cond = abs(z_score) <= self.z_exit

            # Record signals
            if exit_cond:
                signals.at[df.index[i], 'exit_signal'] = True
                self.in_long = False
                self.in_short = False
            elif long_cond and not self.in_long and not self.in_short:
                signals.at[df.index[i], 'signal'] = 1
                self.in_long = True
            elif short_cond and not self.in_short and not self.in_long:
                signals.at[df.index[i], 'signal'] = -1
                self.in_short = True
        
        return signals

# —————— USAGE EXAMPLE ——————
if __name__ == "__main__":
    # Simulate Bybit data (replace with real data)
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    np.random.seed(42)
    
    # Create cointegrated series: y = 0.8*x + noise
    x = 100 + np.cumsum(np.random.randn(200) * 0.5)
    y = 0.8 * x + np.random.randn(200) * 2
    
    df = pd.DataFrame({
        'timestamp': dates,
        'close_1': x,   # e.g., RNDR
        'close_2': y    # e.g., AKT
    })
    
    # Run strategy
    strategy = CointegrationStrategy(
        lookback=120,
        z_entry=2.0,
        z_exit=0.5,
        use_soft_vol=False  # aggressive sizing
    )
    
    signals = strategy.generate_signals(df)
    result = pd.concat([df, signals], axis=1)
    
    # Show recent signals
    print("\nRecent Signals:")
    print(result[['timestamp', 'close_1', 'close_2', 'z_score', 'size_multiplier', 'signal', 'exit_signal']].tail(10))
    
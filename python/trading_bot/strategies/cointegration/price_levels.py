"""
Price Levels Calculator for Cointegrated Pairs

Calculates entry, stop-loss, and take-profit levels based on spread statistics.
Uses the cointegration equation: spread = y - beta * x

Reference: spread_trading_cointegrated._tpsl.md
"""

import numpy as np
from typing import Dict, Any, Tuple


def calculate_levels(
    price_x: float,
    price_y: float,
    beta: float,
    spread_mean: float,
    spread_std: float,
    z_entry: float = 2.0,
    signal: int = 1,  # 1 = long spread, -1 = short spread
    z_history: list = None,  # rolling |z| values for adaptive SL
    min_sl_buffer: float = 1.5  # min z-distance from entry
) -> Dict[str, Any]:
    """
    Calculate entry, stop-loss, and take-profit levels in SPREAD SPACE.

    Uses empirical tail-adaptive approach: SL is set to max(theoretical min, 99th %ile of z-history).

    Execution engine converts spread levels to asset prices using:
        current_spread = price_y - beta * price_x

    Parameters:
    -----------
    price_x, price_y : float
        Current prices of asset X and Y (e.g., ASTER, LINK)
    beta : float
        Hedge ratio from OLS: spread = y - beta * x
    spread_mean, spread_std : float
        Rolling mean and std of spread (ε_t)
    z_entry : float
        Z-score threshold for entry (e.g., 2.0)
    signal : int
        1 = long spread (long Y, short β×X), -1 = short spread (short Y, long β×X)
    z_history : list, optional
        Rolling |z| values for empirical tail analysis
    min_sl_buffer : float
        Minimum z-distance from entry to SL (e.g., 1.2)

    Returns:
    --------
    dict with keys:
        'spread_levels': {
            'entry': float,        # spread value at entry
            'stop_loss': float,    # spread value at SL
            'take_profit_1': float,  # spread value at 50% reversion
            'take_profit_2': float   # spread value at 100% reversion
        }
        'beta': float,  # hedge ratio for execution engine
        'signal': int,  # 1 or -1
        'risk_metrics': {
            'z_distance_to_sl': float,
            'empirical_sl_buffer': bool,
            'z_99th': float or None
        }
    """
    if spread_std <= 0:
        raise ValueError("spread_std must be > 0")

    # ── 1. Compute adaptive stop loss using empirical tail analysis ──
    # Use max(theoretical min, empirical 95th percentile of z-history)
    # 95th percentile gives wider stops than 99th, better for real trading
    z_sl_min = z_entry + min_sl_buffer  # e.g., 2.0 + 1.2 = 3.2

    # TASK 1.3 & 5: NO FALLBACK - z_history must have at least 30 points
    if not z_history or len(z_history) < 30:
        error_msg = (
            f"CRITICAL: Insufficient z_history points for empirical tail analysis. "
            f"Required: 30 points, Got: {len(z_history) if z_history else 0}. "
            f"Cannot calculate adaptive stop loss without sufficient historical data."
        )
        import logging
        logger = logging.getLogger(__name__)
        logger.critical(error_msg)
        raise ValueError(error_msg)

    z_95 = np.percentile(z_history, 95)
    z_sl = max(z_sl_min, z_95)

    if signal == 1:  # Long spread: z <= -2.0 (spread is BELOW mean, expect RISE to mean)
        # Entry: spread is at -2σ (below mean)
        # SL: spread goes even MORE negative (further below mean) - we give up here
        spread_entry = spread_mean - z_entry * spread_std      # entry at -2σ
        spread_sl    = spread_mean - z_sl * spread_std         # SL further below (adaptive)
        spread_tp1   = spread_mean + 0.5 * (spread_mean - spread_entry)  # 50% reversion toward mean
        spread_tp2   = spread_mean                              # full reversion to mean
    elif signal == -1:  # Short spread: z >= +2.0 (spread is ABOVE mean, expect FALL to mean)
        # Entry: spread is at +2σ (above mean)
        # SL: spread goes even MORE positive (further above mean) - we give up here
        spread_entry = spread_mean + z_entry * spread_std      # entry at +2σ
        spread_sl    = spread_mean + z_sl * spread_std         # SL further above (adaptive)
        spread_tp1   = spread_mean - 0.5 * (spread_entry - spread_mean)  # 50% reversion toward mean
        spread_tp2   = spread_mean                              # full reversion to mean
    else:
        raise ValueError("signal must be 1 (long spread) or -1 (short spread)")

    # ── 2. Convert spread levels → asset prices ──
    # Recall: spread = y - beta * x  →  y = spread + beta * x
    
    return {
        "spread_levels": {
            "entry": spread_entry,
            "stop_loss": spread_sl,
            "take_profit_1": spread_tp1,
            "take_profit_2": spread_tp2
        },
        "beta": beta,
        "signal": signal,
        "risk_metrics": {
            "z_distance_to_sl": abs(z_sl - z_entry),
            "empirical_sl_buffer": z_history is not None and len(z_history) >= 30,
            "z_99th": np.percentile(z_history, 99) if z_history and len(z_history) >= 30 else None
        }
    }


def get_single_asset_level(
    levels: Dict[str, Any],
    asset: str = "y",
    level_type: str = "stop_loss"
) -> float:
    """
    Get a single price level for one asset.
    
    Args:
        levels: Output from calculate_levels()
        asset: "x" or "y"
        level_type: "entry", "stop_loss", "take_profit_1", "take_profit_2"
    
    Returns:
        float: Price level for the specified asset
    """
    return levels[level_type][asset]


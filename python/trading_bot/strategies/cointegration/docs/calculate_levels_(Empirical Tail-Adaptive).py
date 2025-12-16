def calculate_levels_adaptive(
    price_x: float,
    price_y: float,
    beta: float,
    spread_mean: float,
    spread_std: float,
    z_entry: float,
    signal: int,
    z_history: list,  # rolling |z| values (last 60 days)
    min_sl_buffer: float = 1.2  # min z-distance from entry
) -> dict:
    if spread_std <= 0:
        raise ValueError("spread_std must be > 0")
    
    # ── Adaptive stop: max(theoretical min, empirical 99th %ile) ──
    z_sl_min = z_entry + min_sl_buffer  # e.g., 2.37 + 1.2 = 3.57
    if len(z_history) >= 30:
        z_99 = np.percentile(z_history, 99)
        z_sl = max(z_sl_min, z_99)
    else:
        z_sl = z_sl_min  # fallback
    
    # ── Spread levels ──
    if signal == 1:  # Long spread
        spread_entry = spread_mean + z_entry * spread_std
        spread_sl    = spread_mean + z_sl * spread_std
        spread_tp1   = spread_mean + 0.5 * (spread_entry - spread_mean)
        spread_tp2   = spread_mean
    else:  # Short spread
        spread_entry = spread_mean - z_entry * spread_std
        spread_sl    = spread_mean - z_sl * spread_std
        spread_tp1   = spread_mean + 0.5 * (spread_entry - spread_mean)
        spread_tp2   = spread_mean

    # ── Convert to asset prices ──
    def spread_to_y(spread_val):
        return spread_val + beta * price_x

    return {
        "entry": {"x": price_x, "y": price_y},
        "stop_loss": {"x": price_x, "y": spread_to_y(spread_sl)},
        "take_profit_1": {"x": price_x, "y": spread_to_y(spread_tp1)},
        "take_profit_2": {"x": price_x, "y": spread_to_y(spread_tp2)},
        "spread_levels": {
            "entry_z": z_entry,
            "stop_z": z_sl,
            "tp1_z": 0.5 * z_entry,
            "tp2_z": 0.0
        },
        "risk_metrics": {
            "z_distance_to_sl": abs(z_sl - z_entry),
            "empirical_sl_buffer": len(z_history) >= 30,
            "z_99th": np.percentile(z_history, 99) if z_history else None
        }
    }
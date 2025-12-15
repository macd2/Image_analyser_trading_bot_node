# Cointegration Strategy - Configuration Structure

## Current Implementation (Strategy-Specific Config in Code)

```python
# ONLY strategy-specific settings (NOT general trading settings)
STRATEGY_CONFIG = {
    # Analysis timeframe (NOT the cycle timeframe)
    "analysis_timeframe": "1h",

    # Pair mappings: symbol -> pair_symbol
    "pairs": {
        "RNDR": "AKT",
        "BTC": "ETH",
        "SOL": "AVAX",
    },

    # Cointegration parameters (strategy-specific)
    "lookback": 120,           # Lookback period for cointegration analysis
    "z_entry": 2.0,            # Z-score entry threshold
    "z_exit": 0.5,             # Z-score exit threshold
    "use_soft_vol": False,      # Use soft volatility adjustment
}
```

**Note:** This dict contains ONLY strategy-specific settings.
- Price levels (entry, SL, TP) are calculated from the signal, not configured
- Confidence is calculated from z-score, not configured
- General trading settings (risk_percentage, position_size, etc.) come from the main TradingConfig

---

## How It's Used

### 1. Get Config Values
```python
pairs = self.get_config_value('pairs', {})
analysis_timeframe = self.get_config_value('analysis_timeframe', '1h')
lookback = self.get_config_value('lookback', 120)
sl_percent = self.get_config_value('sl_percent', 2.0)
```

### 2. Access Pair Symbol
```python
pair_symbol = pairs.get(symbol)  # e.g., "AKT" for "RNDR"
```

### 3. Calculate Price Levels
```python
sl_percent = self.get_config_value('sl_percent', 2.0)
tp_percent = self.get_config_value('tp_percent', 4.0)

stop_loss = current_price * (1.0 - sl_percent / 100.0)
take_profit = current_price * (1.0 + tp_percent / 100.0)
```

### 4. Map Confidence
```python
min_confidence = self.get_config_value('min_confidence', 0.5)
max_confidence = self.get_config_value('max_confidence', 0.95)

confidence = min(max_confidence, min_confidence + abs(z_score) * 0.15)
```

---

## Future: Move to Instance Settings

Later, this will be read from database:

```python
# In database (instances.settings):
{
    "strategy": "cointegration",
    "strategy_config": {
        # ONLY strategy-specific settings here
        "analysis_timeframe": "1h",
        "pairs": {
            "RNDR": "AKT",
            "BTC": "ETH",
            "SOL": "AVAX"
        },
        "lookback": 120,
        "z_entry": 2.0,
        "z_exit": 0.5,
        "use_soft_vol": false
    }
    // Price levels and confidence are calculated, not configured
    // General trading settings come from main config, NOT here
}
```

**No code changes needed** - `self.get_config_value()` will automatically read from database!

---

## Key Design Points

✅ **Strategy-specific config only** - Not general trading settings
✅ **All in one dict** - Easy to move to database later
✅ **Uses `get_config_value()`** - Automatically reads from database when available
✅ **Sensible defaults** - Second parameter is fallback value
✅ **No hardcoded values** - Everything is configurable
✅ **Ready for UI** - Can add dropdown/input fields for each config value
✅ **Separation of concerns** - Strategy config separate from general trading config

---

## Config Parameters Explained

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `analysis_timeframe` | string | "1h" | Timeframe for cointegration analysis |
| `pairs` | dict | {...} | Symbol pair mappings |
| `lookback` | int | 120 | Bars for cointegration calculation |
| `z_entry` | float | 2.0 | Z-score entry threshold |
| `z_exit` | float | 0.5 | Z-score exit threshold |
| `use_soft_vol` | bool | false | Volatility adjustment |

**Note:** Price levels (SL, TP) and confidence are calculated from the signal, not configured.

---

## Example: Changing Configuration

### Now (in code):
```python
STRATEGY_CONFIG = {
    "sl_percent": 3.0,  # Change from 2.0 to 3.0
    "tp_percent": 6.0,  # Change from 4.0 to 6.0
    ...
}
```

### Later (in UI):
1. User opens instance settings
2. Finds "Cointegration" section
3. Changes "Stop Loss %" to 3.0
4. Changes "Take Profit %" to 6.0
5. Saves
6. Next cycle uses new values

**Same code, different source** ✅

---

## Testing Config

```python
# Test with custom config
strategy = CointegrationAnalysisModule(
    config=config,
    instance_id="test",
    strategy_config={
        "analysis_timeframe": "4h",
        "pairs": {"RNDR": "AKT"},
        "sl_percent": 3.0,
        "tp_percent": 6.0,
    }
)

# Strategy will use these values instead of defaults
```

---

## Migration Path

**Phase 1 (Now):** Config in code dict  
**Phase 2 (Later):** Read from database via `get_config_value()`  
**Phase 3 (Later):** Add UI for editing config  

**No code changes needed between phases** - just move the dict to database!


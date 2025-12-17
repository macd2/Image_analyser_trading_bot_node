# Strategy-Specific Settings Design

## Problem
Different strategy types need different configuration:
- **Price-Based** (PromptStrategy, AlexAnalysisModule): RR tightening, SL tightening, confidence thresholds
- **Spread-Based** (CointegrationAnalysisModule): Z-score thresholds, spread monitoring, beta hedge ratios

Current system treats all settings the same → can't configure spread-specific parameters.

## Solution: Strategy-Aware Configuration

### 1. Settings Structure in Database

```json
{
  "strategy": "CointegrationSpreadTrader",
  "strategy_config": {
    "analysis_timeframe": "1h",
    "pairs": { "RNDR": "AKT", "ASTER": "LINK" },
    "lookback": 120,
    "z_entry": 2.0,
    "z_exit": 0.5
  },
  "trading": {
    "paper_trading": true,
    "auto_approve_trades": true,
    "min_confidence_threshold": 0.75,
    "min_rr": 1.7,
    "risk_percentage": 0.01,
    "max_loss_usd": 10.0,
    "leverage": 2,
    "max_concurrent_trades": 5
  },
  "strategy_specific": {
    "price_based": {
      "enable_position_tightening": true,
      "enable_sl_tightening": true,
      "rr_tightening_steps": {
        "step_1": { "threshold": 2.0, "sl_position": 1.2 },
        "step_2": { "threshold": 2.5, "sl_position": 2.0 }
      }
    },
    "spread_based": {
      "enable_spread_monitoring": true,
      "z_score_monitoring_interval": 60,
      "spread_reversion_threshold": 0.1,
      "max_spread_deviation": 3.0,
      "correlation_min_threshold": 0.7
    }
  }
}
```

### 2. Configuration Loading Flow

```python
# In ConfigV2._load_trading()
strategy_type = strategy.STRATEGY_TYPE  # "price_based" or "spread_based"

# Load common trading settings
trading_config = TradingConfig(...)

# Load strategy-specific settings
if strategy_type == "price_based":
    trading_config.price_based_settings = load_price_based_settings(db_config)
elif strategy_type == "spread_based":
    trading_config.spread_based_settings = load_spread_based_settings(db_config)

return trading_config
```

### 3. Dashboard UI Behavior

**Settings Modal** filters by strategy type:
- User selects strategy → UI shows only relevant settings
- Price-based strategy → show RR tightening, SL tightening tabs
- Spread-based strategy → show Z-score, spread monitoring tabs

### 4. Default Settings

Add to `config_defaults.py`:

```python
# Spread-Based Strategy Settings
("strategy_specific.spread_based.enable_spread_monitoring", True, "boolean", "spread_based", ...),
("strategy_specific.spread_based.z_score_monitoring_interval", 60, "number", "spread_based", ...),
("strategy_specific.spread_based.spread_reversion_threshold", 0.1, "number", "spread_based", ...),
```

## Implementation Steps

1. **Add strategy type to BaseAnalysisModule** → STRATEGY_TYPE property
2. **Extend TradingConfig** → add price_based_settings and spread_based_settings
3. **Update config loading** → load strategy-specific settings based on STRATEGY_TYPE
4. **Add default settings** → spread-based defaults in config_defaults.py
5. **Update SettingsModal** → filter settings by strategy type
6. **Update downstream components** → use strategy-specific settings

## Benefits

✅ **Elegant**: Settings organized by strategy type  
✅ **Extensible**: New strategies can add their own settings  
✅ **Type-Safe**: Each strategy knows its own config structure  
✅ **UI-Friendly**: Dashboard shows only relevant settings  
✅ **Backward Compatible**: Existing price-based settings unchanged


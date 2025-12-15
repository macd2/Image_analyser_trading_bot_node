# Configuration Separation - Strategy vs General

## The Principle

**ONLY strategy-specific settings go in STRATEGY_CONFIG**

General trading settings come from the main TradingConfig and are shared across all strategies.

---

## What Goes in STRATEGY_CONFIG (Strategy-Specific)

```python
STRATEGY_CONFIG = {
    # Cointegration-specific parameters
    "analysis_timeframe": "1h",
    "pairs": {"RNDR": "AKT", ...},
    "lookback": 120,
    "z_entry": 2.0,
    "z_exit": 0.5,
    "use_soft_vol": False,
}
```

**Note:** Price levels and confidence are calculated from the signal, not configured.

---

## What Does NOT Go in STRATEGY_CONFIG (General Settings)

These come from main TradingConfig:

```python
# From TradingConfig (NOT in STRATEGY_CONFIG):
- risk_percentage          # General risk setting
- position_size            # General position sizing
- max_open_positions       # General limit
- kelly_criterion_enabled  # General risk management
- min_position_value_usd   # General minimum
- leverage                 # General leverage
- timeframe                # Cycle timeframe (not strategy timeframe)
- etc.
```

---

## How It Works

### 1. Strategy Gets Both Configs

```python
class CointegrationAnalysisModule(BaseAnalysisModule):
    def __init__(self, config, instance_id, strategy_config):
        super().__init__(config, instance_id, strategy_config)
        # self.config = main TradingConfig (general settings)
        # self.strategy_config = STRATEGY_CONFIG (strategy-specific)
```

### 2. Access General Settings

```python
# From main config (general settings)
risk_pct = self.config.risk_percentage
position_size = self.config.position_size
```

### 3. Access Strategy Settings

```python
# From strategy config (strategy-specific)
pairs = self.get_config_value('pairs', {})
sl_percent = self.get_config_value('sl_percent', 2.0)
```

---

## Example: Chart Strategy vs Cointegration

### Chart Strategy (alex_analysis_module.py)

**Strategy-specific config:**
```python
STRATEGY_CONFIG = {
    "timeframes": ["1h", "4h", "1d"],  # Chart-specific
    "indicator_periods": {...},         # Chart-specific
    "trend_threshold": 0.6,             # Chart-specific
}
```

**Uses general config:**
```python
risk_pct = self.config.risk_percentage  # From main config
```

### Cointegration Strategy (cointegration_analysis_module.py)

**Strategy-specific config:**
```python
STRATEGY_CONFIG = {
    "analysis_timeframe": "1h",         # Cointegration-specific
    "pairs": {...},                     # Cointegration-specific
    "lookback": 120,                    # Cointegration-specific
    "z_entry": 2.0,                     # Cointegration-specific
}
```

**Uses general config:**
```python
risk_pct = self.config.risk_percentage  # From main config
```

---

## Future: Database Structure

```python
# instances table
{
    "id": "instance-1",
    "settings": {
        # General trading settings
        "risk_percentage": 2.0,
        "position_size": 1000,
        "max_open_positions": 5,
        
        # Strategy selection
        "strategy": "cointegration",
        
        # Strategy-specific settings
        "strategy_config": {
            "analysis_timeframe": "1h",
            "pairs": {"RNDR": "AKT", ...},
            "lookback": 120,
            "z_entry": 2.0,
            "z_exit": 0.5,
            "use_soft_vol": false,
            "sl_percent": 2.0,
            "tp_percent": 4.0,
            "min_confidence": 0.5,
            "max_confidence": 0.95
        }
    }
}
```

---

## Key Points

✅ **Separation of concerns** - General vs strategy-specific  
✅ **Reusability** - General settings work with any strategy  
✅ **Flexibility** - Each strategy can have different parameters  
✅ **Clarity** - Clear what's general vs strategy-specific  
✅ **Maintainability** - Easy to add new strategies  

---

## When Adding New Strategy

1. Create new strategy class
2. Define ONLY strategy-specific STRATEGY_CONFIG
3. Use `self.get_config_value()` for strategy settings
4. Use `self.config.xxx` for general settings
5. Return same output format as other strategies

That's it! ✅


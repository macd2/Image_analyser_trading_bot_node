# Strategy Development Guide

This guide explains how to create new trading strategies for the bot. All strategies must inherit from `BaseAnalysisModule` and implement the required abstract methods.

## Quick Start

1. Create a new folder: `python/trading_bot/strategies/your_strategy/`
2. Create `your_strategy_module.py` inheriting from `BaseAnalysisModule`
3. Implement all abstract methods (see below)
4. Register in `factory.py`
5. Add tests in `your_strategy/tests/`

## Strategy Interface

Every strategy must implement these abstract methods:

### 1. `run_analysis_cycle(symbols, timeframe, cycle_id)` → List[Dict]

**Purpose**: Analyze symbols and return trading recommendations.

**Input Parameters**:
- `symbols` (List[str]): Symbols to analyze (e.g., ['BTCUSDT', 'ETHUSDT'])
- `timeframe` (str): Candle timeframe (e.g., '1h', '4h', '1d')
- `cycle_id` (str): Unique cycle identifier for audit trail

**Returns**: List of recommendation dicts with this exact structure:
```python
{
    "symbol": "BTCUSDT",                    # Trading pair
    "recommendation": "BUY",                # BUY, SELL, or HOLD
    "confidence": 0.85,                     # 0.0-1.0 confidence score
    "entry_price": 45000.0,                 # Entry price (can be None for HOLD)
    "stop_loss": 44000.0,                   # Stop loss price (can be None)
    "take_profit": 47000.0,                 # Take profit price (can be None)
    "risk_reward": 2.0,                     # Risk/reward ratio
    "setup_quality": 0.8,                   # Setup quality score (0-1)
    "market_environment": 0.7,              # Market environment score (0-1)
    "analysis": {                           # Strategy-specific analysis data
        "key1": "value1",
        "key2": "value2"
    },
    "chart_path": "/path/to/chart.png",     # Path to chart image (if applicable)
    "timeframe": "1h",                      # Timeframe analyzed
    "cycle_id": "cycle-123",                # Cycle identifier
    "strategy_uuid": "uuid-string",         # Auto-generated, don't set
    "strategy_type": "price_based",         # Auto-generated, don't set
    "strategy_name": "YourStrategy",        # Auto-generated, don't set
    # Optional fields for reproducibility:
    "confidence_components": {...},         # How confidence was calculated
    "setup_quality_components": {...},      # How setup quality was calculated
    "market_environment_components": {...}, # How market environment was calculated
    "validation_results": {...}             # Validation details
}
```

### 2. `validate_signal(signal)` → bool

**Purpose**: Validate that a signal meets strategy-specific requirements.

**Input**: Signal dict with entry_price, stop_loss, take_profit, etc.

**Returns**: True if valid, raises ValueError with details if invalid

**Example (Price-based)**:
```python
def validate_signal(self, signal: Dict[str, Any]) -> bool:
    # Check RR ratio >= minimum
    if signal.get('risk_reward', 0) < self.min_rr:
        raise ValueError(f"RR ratio {signal['risk_reward']} < {self.min_rr}")
    
    # Check prices are in correct order
    if signal['entry_price'] <= signal['stop_loss']:
        raise ValueError("Entry must be above stop loss")
    
    return True
```

### 3. `calculate_risk_metrics(signal)` → Dict[str, Any]

**Purpose**: Calculate strategy-specific risk metrics from a signal.

**Input**: Signal dict with entry_price, stop_loss, take_profit

**Returns**: Dict with risk metrics (varies by strategy type)

**Example (Price-based)**:
```python
def calculate_risk_metrics(self, signal: Dict[str, Any]) -> Dict[str, Any]:
    entry = signal['entry_price']
    sl = signal['stop_loss']
    tp = signal['take_profit']
    
    risk_per_unit = abs(entry - sl)
    reward_per_unit = abs(tp - entry)
    rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0
    
    return {
        "risk_per_unit": risk_per_unit,
        "reward_per_unit": reward_per_unit,
        "rr_ratio": rr_ratio,
        "risk_amount_usd": risk_per_unit * position_size  # If applicable
    }
```

### 4. `get_exit_condition()` → Dict[str, Any]

**Purpose**: Return strategy-specific exit condition metadata for simulator/position monitor.

**Returns**: Dict with exit parameters

**Example (Price-based)**:
```python
def get_exit_condition(self) -> Dict[str, Any]:
    return {
        "type": "price_level",
        "tp_price": self.current_signal['take_profit'],
        "sl_price": self.current_signal['stop_loss']
    }
```

**Example (Spread-based)**:
```python
def get_exit_condition(self) -> Dict[str, Any]:
    return {
        "type": "z_score",
        "z_exit": 0.5,
        "beta": 1.2,
        "spread_mean": 0.05,
        "spread_std": 0.01
    }
```

### 5. `get_monitoring_metadata()` → Dict[str, Any]

**Purpose**: Return strategy-specific monitoring metadata for position monitor.

**Returns**: Dict with monitoring parameters

**Example (Price-based)**:
```python
def get_monitoring_metadata(self) -> Dict[str, Any]:
    return {
        "entry_price": self.current_signal['entry_price'],
        "sl": self.current_signal['stop_loss'],
        "tp": self.current_signal['take_profit'],
        "rr_ratio": self.current_signal['risk_reward']
    }
```

### 6. `get_required_settings()` → Dict[str, Any]

**Purpose**: Declare what settings this strategy needs (class method).

**Returns**: Dict with settings schema

**Example**:
```python
@classmethod
def get_required_settings(cls) -> Dict[str, Any]:
    return {
        "enable_position_tightening": {
            "type": "bool",
            "default": True,
            "description": "Enable SL tightening as price moves favorably"
        },
        "min_rr_ratio": {
            "type": "float",
            "default": 1.5,
            "description": "Minimum risk/reward ratio to accept signals"
        },
        "max_open_positions": {
            "type": "int",
            "default": 5,
            "description": "Maximum concurrent open positions"
        }
    }
```

## Strategy Types

### Price-Based Strategies
- Monitor price levels (entry, SL, TP)
- Exit when price touches TP or SL
- Risk metrics: RR ratio, risk per unit
- Example: PromptStrategy

### Spread-Based Strategies
- Monitor spread/z-score between two assets
- Exit when z-score crosses threshold
- Risk metrics: z-distance, spread volatility
- Example: CointegrationAnalysisModule

## Class Properties (Required)

```python
class YourStrategy(BaseAnalysisModule):
    STRATEGY_TYPE = "price_based"  # or "spread_based"
    STRATEGY_NAME = "YourStrategy"
    STRATEGY_VERSION = "1.0"
    DEFAULT_CONFIG = {
        "param1": value1,
        "param2": value2
    }
```

## Reproducibility Data

Optionally capture reproducibility data by calling:
```python
reproducibility_data = self.capture_reproducibility_data(
    analysis_result=result,
    chart_path="/path/to/chart.png",
    market_data=market_snapshot,
    model_version="gpt-4-vision",
    model_params={"temperature": 0.7},
    prompt_version="v1.0",
    prompt_content="Your prompt here"
)
```

## Helper Methods

- `self.get_config_value(key, default)` - Get config value
- `self.get_strategy_specific_settings()` - Get strategy settings
- `self._heartbeat(message, **kwargs)` - Send UI updates
- `self.logger` - Logging instance

## Testing

Create tests in `your_strategy/tests/`:
```python
def test_validate_signal():
    strategy = YourStrategy(config)
    signal = {...}
    assert strategy.validate_signal(signal) == True

def test_calculate_risk_metrics():
    strategy = YourStrategy(config)
    metrics = strategy.calculate_risk_metrics(signal)
    assert metrics['rr_ratio'] > 0
```

## Registration

Add to `python/trading_bot/strategies/factory.py`:
```python
from your_strategy.your_strategy_module import YourStrategy

STRATEGY_REGISTRY = {
    "your_strategy": YourStrategy,
    ...
}
```

## Complete Example

See `python/trading_bot/strategies/prompt/prompt_strategy.py` for a complete price-based strategy implementation.

See `python/trading_bot/strategies/cointegration/cointegration_analysis_module.py` for a complete spread-based strategy implementation.


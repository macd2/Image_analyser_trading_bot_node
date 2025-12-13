# Pluggable Strategy System - Usage Examples

## Overview

The new strategy system allows different instances to run different analysis strategies with instance-specific configuration.

## Architecture

```
BaseAnalysisModule (abstract base)
├── PromptAnalysisModule (OpenAI-based)
├── AlexAnalysisModule (Top-down technical analysis)
└── Custom strategies (user-defined)

StrategyFactory (loads strategy + config from database)
CandleAdapter (unified candle interface)
```

## Example 1: Using AlexAnalysisModule

### Instance Configuration (in database)

```json
{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["1h", "4h", "1d"],
    "lookback_periods": 20,
    "min_confidence": 0.7,
    "use_volume": true
  }
}
```

### In TradingCycle

```python
from trading_bot.strategies.factory import StrategyFactory

class TradingCycle:
    def __init__(self, config, instance_id, run_id):
        # Create strategy using factory
        # Factory loads config from database automatically
        self.analysis_module = StrategyFactory.create(
            instance_id=instance_id,
            config=config,
            run_id=run_id,
        )
    
    async def run_cycle_async(self):
        # Run analysis with instance-specific strategy
        results = await self.analysis_module.run_analysis_cycle(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframe="1h",
            cycle_id=cycle_id
        )
        
        # Results are standardized format:
        # {
        #   "symbol": "BTCUSDT",
        #   "recommendation": "BUY",
        #   "confidence": 0.75,
        #   "entry_price": None,
        #   "stop_loss": None,
        #   "take_profit": None,
        #   "risk_reward": 0,
        #   "setup_quality": 0.7,
        #   "market_environment": 0.6,
        #   "analysis": {...},
        #   "chart_path": "",
        #   "timeframe": "1h",
        #   "cycle_id": "abc123",
        # }
```

## Example 2: Creating Custom Strategy

### Create `python/trading_bot/strategies/custom/ml_strategy.py`

```python
from trading_bot.strategies.base import BaseAnalysisModule
from typing import List, Dict, Any, Optional
import pickle

class MLAnalysisModule(BaseAnalysisModule):
    """Custom ML-based strategy"""
    
    DEFAULT_CONFIG = {
        "model_path": "/models/default.pkl",
        "lookback_periods": 100,
        "confidence_threshold": 0.70,
    }
    
    def __init__(self, config, instance_id=None, run_id=None, strategy_config=None):
        super().__init__(config, instance_id, run_id, strategy_config)
        
        # Load model from instance-specific path
        model_path = self.get_config_value('model_path')
        with open(model_path, 'rb') as f:
            self.model = pickle.load(f)
    
    async def run_analysis_cycle(self, symbols, timeframe, cycle_id):
        results = []
        
        for symbol in symbols:
            try:
                # Get candles from adapter
                candles = self.candle_adapter.get_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=self.get_config_value('lookback_periods'),
                    use_cache=True
                )
                
                # Run ML model
                prediction = self.model.predict(candles)
                
                # Build result (MUST match output format)
                result = {
                    "symbol": symbol,
                    "recommendation": prediction["action"],
                    "confidence": prediction["confidence"],
                    "entry_price": prediction.get("entry"),
                    "stop_loss": prediction.get("sl"),
                    "take_profit": prediction.get("tp"),
                    "risk_reward": prediction.get("rr", 0),
                    "setup_quality": prediction.get("setup_quality", 0.5),
                    "market_environment": prediction.get("market_env", 0.5),
                    "analysis": prediction,
                    "chart_path": "",
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                }
                
                self._validate_output(result)
                results.append(result)
                
            except Exception as e:
                results.append({
                    "symbol": symbol,
                    "error": str(e),
                    "timeframe": timeframe,
                    "cycle_id": cycle_id,
                })
        
        return results
```

### Register Strategy

```python
from trading_bot.strategies.factory import StrategyFactory
from trading_bot.strategies.custom.ml_strategy import MLAnalysisModule

# Register custom strategy
StrategyFactory.register_strategy("ml", MLAnalysisModule)
```

### Instance Configuration

```json
{
  "strategy": "ml",
  "strategy_config": {
    "model_path": "/models/lstm_v3.pkl",
    "lookback_periods": 100,
    "confidence_threshold": 0.70
  }
}
```

## Example 3: Different Instances, Different Strategies

### Instance A: Aggressive (Prompt-based)

```json
{
  "strategy": "prompt",
  "strategy_config": {
    "prompt_name": "aggressive_scalper",
    "use_assistant": true,
    "confidence_threshold": 0.5
  }
}
```

### Instance B: Conservative (Alex Top-Down)

```json
{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["4h", "1d"],
    "min_confidence": 0.8,
    "use_volume": true
  }
}
```

### Instance C: ML-based

```json
{
  "strategy": "ml",
  "strategy_config": {
    "model_path": "/models/ensemble.pkl",
    "lookback_periods": 200,
    "confidence_threshold": 0.75
  }
}
```

## Key Features

✅ **Instance-Specific**: Each instance can use different strategy  
✅ **Configurable**: Settings editable via UI modal  
✅ **Standardized Output**: All strategies return same format  
✅ **Audit Trail**: Full reproducibility with instance_id, strategy, config  
✅ **Candle Adapter**: Simple interface for candle data (cached or real)  
✅ **Easy to Extend**: Create custom strategies by extending BaseAnalysisModule  

## Output Format (Enforced)

All strategies MUST return:

```python
{
    "symbol": str,                          # e.g., "BTCUSDT"
    "recommendation": "BUY" | "SELL" | "HOLD",
    "confidence": float,                    # 0.0-1.0
    "entry_price": float | None,
    "stop_loss": float | None,
    "take_profit": float | None,
    "risk_reward": float,
    "setup_quality": float,                 # 0.0-1.0
    "market_environment": float,            # 0.0-1.0
    "analysis": dict,                       # Full analysis data
    "chart_path": str,
    "timeframe": str,
    "cycle_id": str,
    # Optional error fields
    "error": str | None,
    "skipped": bool | None,
    "skip_reason": str | None,
}
```

## Database Schema

Instance settings stored in `instances.settings` JSON:

```sql
UPDATE instances 
SET settings = '{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["1h", "4h"],
    "min_confidence": 0.7
  }
}'
WHERE id = 'instance-id';
```

## Audit Trail

All analysis logged to `recommendations` table:

```
instances (id, name, settings)
    ↓
runs (id, instance_id, config_snapshot)
    ↓
cycles (id, run_id, boundary_time)
    ↓
recommendations (id, cycle_id, symbol, recommendation, confidence, ...)
```

Every recommendation is traceable back to:
- Which instance made the decision
- Which run (bot session) it was in
- Which cycle (timeframe boundary) it was analyzed in
- Full strategy config used
- Exact timestamp


# AlexAnalysisModule - Complete Example

## Overview

This document shows how the AlexStrategy (top-down technical analysis) has been converted to work with the new BaseAnalysisModule system.

## Key Changes from AlexStrategy

### Before (AlexStrategy)
```python
class AlexStrategy(BaseStrategy):
    async def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Dict[str, Any]:
        # Returns custom format
        return {
            "strategy": "alex_top_down",
            "recommendation": "BUY",
            "confidence": 0.75,
            "signals": [...],
            "reasoning": "...",
            "analysis": {...}
        }
```

### After (AlexAnalysisModule)
```python
class AlexAnalysisModule(BaseAnalysisModule):
    async def run_analysis_cycle(self, symbols: List[str], timeframe: str, cycle_id: str) -> List[Dict[str, Any]]:
        # Returns standardized format for ALL symbols
        return [
            {
                "symbol": "BTCUSDT",
                "recommendation": "BUY",
                "confidence": 0.75,
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None,
                "risk_reward": 0,
                "setup_quality": 0.7,
                "market_environment": 0.6,
                "analysis": {...},
                "chart_path": "",
                "timeframe": "1h",
                "cycle_id": "abc123",
            },
            ...
        ]
```

## Instance Configuration

### Database Setup

```sql
UPDATE instances 
SET settings = '{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["1h", "4h", "1d"],
    "lookback_periods": 20,
    "indicators": ["RSI", "MACD", "EMA"],
    "min_confidence": 0.7,
    "use_volume": true
  }
}'
WHERE id = 'instance-alex-aggressive';
```

### UI Modal (Instance Settings)

```
Strategy: [Dropdown: prompt | alex | ml | custom]

Alex Strategy Configuration:
├─ Timeframes: [1h, 4h, 1d] (editable array)
├─ Lookback Periods: 20 (number input)
├─ Min Confidence: 0.7 (slider 0-1)
└─ Use Volume: ✓ (toggle)
```

## Complete Flow

### 1. TradingCycle Initialization

```python
from trading_bot.strategies.factory import StrategyFactory

class TradingCycle:
    def __init__(self, config, instance_id, run_id):
        # Factory loads strategy name and config from database
        self.analysis_module = StrategyFactory.create(
            instance_id=instance_id,
            config=config,
            run_id=run_id,
        )
        # Returns: AlexAnalysisModule with instance-specific config
```

### 2. StrategyFactory.create() Flow

```
1. Load instance from database
   SELECT settings FROM instances WHERE id = 'instance-alex-aggressive'
   
2. Parse settings JSON
   {
     "strategy": "alex",
     "strategy_config": {
       "timeframes": ["1h", "4h", "1d"],
       "min_confidence": 0.7,
       ...
     }
   }
   
3. Get strategy class from registry
   STRATEGIES["alex"] = AlexAnalysisModule
   
4. Instantiate with instance-specific config
   AlexAnalysisModule(
     config=config,
     instance_id='instance-alex-aggressive',
     run_id='run-123',
     strategy_config={
       "timeframes": ["1h", "4h", "1d"],
       "min_confidence": 0.7,
       ...
     }
   )
```

### 3. AlexAnalysisModule Initialization

```python
class AlexAnalysisModule(BaseAnalysisModule):
    DEFAULT_CONFIG = {
        "timeframes": ["1h", "4h", "1d"],
        "lookback_periods": 20,
        "min_confidence": 0.7,
        "use_volume": True,
    }
    
    def __init__(self, config, instance_id, run_id, strategy_config):
        super().__init__(config, instance_id, run_id, strategy_config)
        # self.strategy_config now contains instance-specific settings
        # self.candle_adapter is initialized for getting candles
```

### 4. Analysis Cycle

```python
# In TradingCycle.run_cycle_async()
results = await self.analysis_module.run_analysis_cycle(
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    timeframe="1h",
    cycle_id="cycle-abc123"
)
```

### 5. AlexAnalysisModule.run_analysis_cycle()

```
For each symbol:
  1. Get candles from CandleAdapter
     - Checks database cache first
     - Falls back to Bybit API if needed
     - Caches results for future use
  
  2. Convert candles to DataFrame
  
  3. Calculate indicators
     - SMA 20, 50, 200
     - RSI
     - MACD
  
  4. Perform analysis
     - Detect trend (bullish/bearish/neutral)
     - Identify support/resistance
     - Analyze market structure
     - Detect entry signals
  
  5. Determine recommendation
     - Apply instance-specific min_confidence threshold
     - Return BUY/SELL/HOLD
  
  6. Build standardized result
     {
       "symbol": "BTCUSDT",
       "recommendation": "BUY",
       "confidence": 0.75,
       "entry_price": None,
       "stop_loss": None,
       "take_profit": None,
       "risk_reward": 0,
       "setup_quality": 0.7,
       "market_environment": 0.6,
       "analysis": {
         "strategy": "alex_top_down",
         "trend": {"trend": "bullish", "strength": 0.8},
         "support_resistance": {...},
         "market_structure": {...},
         "signals": [...],
         "reasoning": "..."
       },
       "chart_path": "",
       "timeframe": "1h",
       "cycle_id": "cycle-abc123",
     }
  
  7. Validate output format
     - Check all required fields present
     - Check field types correct
     - Check recommendation is BUY/SELL/HOLD
     - Check confidence is 0-1
```

### 6. Results Storage

```sql
INSERT INTO recommendations (
  id, cycle_id, symbol, timeframe, recommendation, confidence,
  entry_price, stop_loss, take_profit, risk_reward,
  reasoning, chart_path, prompt_name, prompt_version,
  model_name, raw_response, analyzed_at, cycle_boundary, created_at
) VALUES (
  'rec-123', 'cycle-abc123', 'BTCUSDT', '1h', 'BUY', 0.75,
  NULL, NULL, NULL, 0,
  'Trend: bullish | ...', '', 'alex_top_down', 'v1.0',
  'AlexAnalysisModule', '{"strategy": "alex_top_down", ...}',
  '2025-12-11T10:30:00Z', '2025-12-11T10:00:00Z', '2025-12-11T10:30:00Z'
);
```

## Audit Trail

Every recommendation is traceable:

```
instances (id='instance-alex-aggressive')
  ↓ (instance_id)
runs (id='run-123', instance_id='instance-alex-aggressive')
  ↓ (run_id)
cycles (id='cycle-abc123', run_id='run-123')
  ↓ (cycle_id)
recommendations (id='rec-123', cycle_id='cycle-abc123', symbol='BTCUSDT')
```

Query to trace a recommendation:

```sql
SELECT 
  i.name as instance_name,
  r.started_at as run_started,
  c.boundary_time as cycle_boundary,
  rec.symbol,
  rec.recommendation,
  rec.confidence,
  rec.analyzed_at
FROM recommendations rec
JOIN cycles c ON rec.cycle_id = c.id
JOIN runs r ON c.run_id = r.id
JOIN instances i ON r.instance_id = i.id
WHERE rec.id = 'rec-123';
```

## Instance-Specific Configuration

### Instance A: Aggressive (Low Confidence Threshold)

```json
{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["1h", "4h"],
    "lookback_periods": 20,
    "min_confidence": 0.5,
    "use_volume": true
  }
}
```

### Instance B: Conservative (High Confidence Threshold)

```json
{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["4h", "1d"],
    "lookback_periods": 50,
    "min_confidence": 0.85,
    "use_volume": true
  }
}
```

Both instances use AlexAnalysisModule but with different settings!

## Key Benefits

✅ **Instance-Specific**: Each instance can have different min_confidence  
✅ **Configurable**: Settings editable via UI without code changes  
✅ **Standardized Output**: All results match same format  
✅ **Audit Trail**: Full reproducibility with instance_id, strategy, config  
✅ **Candle Caching**: Efficient candle fetching with database cache  
✅ **Error Handling**: Consistent error logging with context  


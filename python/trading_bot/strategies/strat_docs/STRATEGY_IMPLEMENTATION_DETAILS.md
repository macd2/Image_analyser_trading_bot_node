# Pluggable Strategy System - Implementation Details

## 1. BaseAnalysisModule Interface (All Strategies Implement This)

### Location
`python/trading_bot/strategies/base.py`

### Required Method
```python
class BaseAnalysisModule(ABC):
    """All strategies must implement this interface"""

    @abstractmethod
    def analyze_symbols(
        self,
        symbols: List[str],
        timeframe: str,
        cycle_id: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Analyze symbols and return recommendations.

        Returns list of dicts with:
        - symbol, timeframe, recommendation, confidence
        - entry_price, stop_loss, take_profit, risk_reward_ratio
        - summary, evidence, direction, market_condition, market_direction
        - chart_path (optional - None if no charts)
        - strategy_name, strategy_version, strategy_config, raw_response
        """
        pass
```

### Key Points
- All strategies implement `analyze_symbols()` method
- Takes: symbols list, timeframe, cycle_id
- Returns: List of standardized recommendation dicts
- Each dict includes reproducibility fields for audit trail

---

## 2. PromptAnalysisModule (Chart-Based Strategy)

### Location
`python/trading_bot/strategies/prompt_analysis_module.py`

### Structure
```python
class PromptAnalysisModule(BaseAnalysisModule):
    """Chart-based strategy using Sourcer + Cleaner + Analyzer"""

    def __init__(self, config, instance_id=None, run_id=None, strategy_config=None):
        super().__init__(config, instance_id, run_id, strategy_config)
        self.sourcer = ChartSourcer(config=config)
        self.cleaner = ChartCleaner(config=config)
        self.analyzer = ChartAnalyzer(
            openai_client=OpenAI(api_key=config.openai.api_key),
            config=config,
            api_manager=BybitAPIManager(config)
        )

    def analyze_symbols(self, symbols, timeframe, cycle_id, **kwargs):
        """Analyze symbols using charts"""
        results = []
        for symbol in symbols:
            # 1. Capture chart
            chart_path = self.sourcer.get_chart(symbol, timeframe)

            # 2. Analyze chart
            analysis = self.analyzer.analyze_chart(chart_path)

            # 3. Clean up
            self.cleaner.cleanup()

            # 4. Return standardized format with reproducibility fields
            results.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "recommendation": analysis["recommendation"],
                "confidence": analysis["confidence"],
                "entry_price": analysis["entry_price"],
                "stop_loss": analysis["stop_loss"],
                "take_profit": analysis["take_profit"],
                "risk_reward_ratio": analysis["risk_reward_ratio"],
                "summary": analysis["summary"],
                "evidence": analysis["evidence"],
                "direction": analysis["direction"],
                "market_condition": analysis["market_condition"],
                "market_direction": analysis["market_direction"],
                "cycle_id": cycle_id,
                "chart_path": chart_path,
                # REPRODUCIBILITY FIELDS
                "strategy_name": "prompt",
                "strategy_version": "1.0",
                "strategy_config": self.strategy_config,
                "raw_response": json.dumps(analysis),
            })
        return results
```

### Key Points
- Wraps existing Sourcer + Cleaner + Analyzer
- No behavior changes - 100% backward compatible
- Includes all reproducibility fields
- Each trade can be traced back to exact strategy version and config

---

## 3. TradingCycle Integration

### Changes Required

**In `__init__()` (Line ~103)**:
```python
# OLD: self.analyzer = ChartAnalyzer(...)
# OLD: self.sourcer = ChartSourcer(...)
# OLD: self.cleaner = ChartCleaner(...)

# NEW:
from trading_bot.strategies.factory import StrategyFactory

self.strategy = StrategyFactory.create(
    instance_id=self.instance_id,
    config=self.config,
    run_id=self.run_id
)
```

**In `_analyze_cycle_async()` (Line ~747)**:
```python
# OLD: Manual sourcing/cleaning/analyzing
# OLD: self.analyzer.analyze_chart(chart_path)

# NEW:
recommendations = self.strategy.analyze_symbols(
    symbols=symbols_to_analyze,
    timeframe=self.timeframe,
    cycle_id=cycle_id
)
```

**In `_record_recommendation()` (Line ~1190)**:
```python
# Extract reproducibility fields from recommendation
strategy_name = rec.get("strategy_name", "unknown")
strategy_version = rec.get("strategy_version", "1.0")
strategy_config = rec.get("strategy_config", {})
raw_response = rec.get("raw_response", "")

# Store in database
execute(db, """
    INSERT INTO recommendations (...)
    VALUES (...)
""", (
    rec_id,
    cycle_id,
    symbol,
    timeframe,
    recommendation,
    confidence,
    entry_price,
    stop_loss,
    take_profit,
    risk_reward,
    reasoning,
    chart_path,  # Can be NULL
    strategy_name,  # NEW: Strategy name
    strategy_version,  # NEW: Strategy version
    json.dumps(strategy_config),  # NEW: Full config
    raw_response,  # NEW: Full response for replay
    analyzed_at,
    cycle_boundary,
    created_at
))
```

---

## 4. StrategyFactory Registration

### In `python/trading_bot/strategies/__init__.py`
```python
from trading_bot.strategies.prompt_analysis_module import PromptAnalysisModule

# Register built-in strategies
StrategyFactory.register_strategy("prompt", PromptAnalysisModule)
StrategyFactory.register_strategy("alex", AlexAnalysisModule)
```

### How It Works
1. `StrategyFactory.create(instance_id, config)` is called
2. Loads instance from database: `SELECT settings FROM instances WHERE id = ?`
3. Parses `settings` JSON: `{"strategy": "prompt", "strategy_config": {...}}`
4. Gets strategy class from registry: `STRATEGIES["prompt"]`
5. Instantiates: `PromptAnalysisModule(config, instance_id, run_id, strategy_config)`
6. Returns strategy instance

---

## 5. Database Schema (Reproducibility Built In)

### Instance Settings (Already Supports This)
```json
{
  "strategy": "prompt",
  "strategy_config": {
    "use_assistant": true,
    "timeout": 600
  }
}
```

### Recommendations Table (Enhanced for Reproducibility)
```sql
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    cycle_id TEXT,
    symbol TEXT,
    timeframe TEXT,
    recommendation TEXT,
    confidence REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_reward REAL,
    reasoning TEXT,
    chart_path TEXT,  -- NULL for non-chart strategies
    strategy_name TEXT,  -- NEW: Which strategy (e.g., "prompt", "technical")
    strategy_version TEXT,  -- NEW: Version (e.g., "1.0", "2.1")
    strategy_config JSONB,  -- NEW: Full config used for analysis
    raw_response TEXT,  -- NEW: Full response for replay/audit
    prompt_name TEXT,
    analyzed_at TIMESTAMPTZ,
    cycle_boundary TIMESTAMPTZ,
    created_at TIMESTAMPTZ
);
```

**Reproducibility Guarantee**: Given same symbol, timeframe, and strategy_config, can replay analysis

---

## 6. Adding New Strategies (Drop-in)

### Example: Technical Analysis Strategy
```python
# python/trading_bot/strategies/technical_analysis_module.py
from trading_bot.strategies.base import BaseAnalysisModule

class TechnicalAnalysisModule(BaseAnalysisModule):
    """API-based technical analysis - no charts needed"""

    def analyze_symbols(self, symbols, timeframe, cycle_id, **kwargs):
        results = []
        for symbol in symbols:
            # Fetch candles from API
            candles = self.api_manager.get_candles(symbol, timeframe)

            # Calculate indicators
            rsi = calculate_rsi(candles)
            macd = calculate_macd(candles)

            # Generate signal
            signal = self.generate_signal(rsi, macd)

            # Return standardized format
            results.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "recommendation": signal["recommendation"],
                "confidence": signal["confidence"],
                "entry_price": signal["entry_price"],
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "risk_reward_ratio": signal["risk_reward_ratio"],
                "summary": signal["summary"],
                "evidence": signal["evidence"],
                "direction": signal["direction"],
                "market_condition": signal["market_condition"],
                "market_direction": signal["market_direction"],
                "cycle_id": cycle_id,
                "chart_path": None,  # No charts
                # REPRODUCIBILITY FIELDS
                "strategy_name": "technical",
                "strategy_version": "1.0",
                "strategy_config": self.strategy_config,
                "raw_response": json.dumps(signal),
            })
        return results

# Register in __init__.py
StrategyFactory.register_strategy("technical", TechnicalAnalysisModule)
```

### That's It!
- No changes to TradingCycle
- No database migrations
- No API changes
- Just implement, register, and use
- Every trade is fully reproducible

---

## 7. Output Format Validation

### BaseAnalysisModule._validate_output()
Ensures all strategies return required fields:
- `symbol`, `timeframe`, `cycle_id` (strings)
- `recommendation` (LONG/SHORT/HOLD)
- `confidence` (0.0-1.0)
- `entry_price`, `stop_loss`, `take_profit` (floats)
- `risk_reward_ratio` (float)
- `summary`, `evidence` (strings)
- `direction` (Long/Short)
- `market_condition`, `market_direction` (enums)
- `strategy_name`, `strategy_version`, `strategy_config`, `raw_response` (reproducibility)

Raises exception if validation fails - prevents bad data from reaching database.


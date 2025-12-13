# Pluggable Strategy System - Executive Summary

## What We're Building
A drop-in strategy system where:
- ✅ Each instance can use a different strategy (Prompt, Technical, ML, Custom, etc.)
- ✅ All strategies return identical output format (100% compatible)
- ✅ Everything after the strategy (ranking, execution, trades) stays the same
- ✅ **Every trade is fully reproducible** (strategy name, version, config, raw response logged)
- ✅ Minimal changes to TradingCycle (~30 lines)
- ✅ New strategies are truly plug-and-play

## Core Principle: Strategies as Black Boxes

Each strategy is completely independent:
- **Input**: symbols, timeframe, cycle_id
- **Processing**: Can use charts, API, ML, indicators, or anything else
- **Output**: Standardized recommendation format
- **Guarantee**: 100% compatibility with downstream code

## Current State
- **Strategy Infrastructure**: Already built! (`BaseAnalysisModule`, `StrategyFactory`)
- **Database Support**: Already supports strategy config in `instances.settings`
- **Current Analyzer**: Hardcoded in TradingCycle, needs to be wrapped

## The Plan (4 Phases)

### Phase 1: Wrap Current Analyzer
**File**: Create `python/trading_bot/strategies/prompt_analysis_module.py`
- Wraps `ChartAnalyzer` in `BaseAnalysisModule`
- Implements `analyze_symbols()` method
- Returns exact same output format + reproducibility fields
- No behavior changes
- **Result**: Current system becomes pluggable

### Phase 2: Update TradingCycle
**File**: Modify `python/trading_bot/engine/trading_cycle.py`
- Remove: `self.analyzer`, `self.sourcer`, `self.cleaner`
- Add: `self.strategy = StrategyFactory.create(instance_id, config)`
- Replace: Manual sourcing/cleaning/analyzing
- With: `self.strategy.analyze_symbols(symbols, timeframe, cycle_id)`
- **Result**: TradingCycle is strategy-agnostic

### Phase 3: UI Strategy Selection (Optional)
**Files**: Instance settings modal
- Add dropdown to select strategy
- Add JSON editor for strategy config
- Save to `instances.settings`
- **Result**: Users can switch strategies per instance

### Phase 4: Add New Strategies (Drop-in)
**For each new strategy**:
1. Create file: `python/trading_bot/strategies/[name]_module.py`
2. Extend `BaseAnalysisModule`
3. Implement `analyze_symbols()` method
4. Return standardized output with reproducibility fields
5. Register in `StrategyFactory`
- **Result**: New strategies work immediately, no TradingCycle changes

## Key Guarantees

### 100% Output Compatibility
All strategies return this exact format per symbol:
```python
{
    "symbol": str,
    "timeframe": str,
    "recommendation": "LONG|SHORT|HOLD",
    "confidence": 0.0-1.0,
    "entry_price": float,
    "stop_loss": float,
    "take_profit": float,
    "risk_reward_ratio": float,
    "summary": str,
    "evidence": str,
    "direction": "Long|Short",
    "market_condition": "TRENDING|RANGING",
    "market_direction": "UP|DOWN|SIDEWAYS",
    "cycle_id": str,
    "chart_path": str | None,  # Optional - not all strategies use charts
    # REPRODUCIBILITY FIELDS
    "strategy_name": str,  # e.g., "prompt", "technical"
    "strategy_version": str,  # e.g., "1.0", "2.1"
    "strategy_config": dict,  # Full config used
    "raw_response": str,  # Full response for replay
}
```

### Database Enhanced for Reproducibility
- `recommendations` table stores all fields
- `chart_path` is nullable - works for all strategies
- `strategy_name`, `strategy_version`, `strategy_config`, `raw_response` logged
- **Every trade is fully reproducible**: Given same inputs and config, can replay

### Backward Compatible
- Default strategy: "prompt" (current analyzer)
- Existing instances: Work without changes
- No migrations needed

## Files to Create/Modify

### Create (1 file):
- `python/trading_bot/strategies/prompt_analysis_module.py` (~80 lines)

### Modify (3 files):
- `python/trading_bot/engine/trading_cycle.py` (~20 line changes)
- `python/trading_bot/strategies/__init__.py` (add export)
- `python/trading_bot/strategies/factory.py` (register strategy)

### Optional (UI):
- Instance settings modal (add strategy selector)

## Why This Works

1. **Output Format is Standardized**: All strategies return same JSON structure
2. **Database is Agnostic**: Stores any strategy output identically
3. **Downstream is Unchanged**: Ranking, execution, trades don't care which strategy
4. **Factory Pattern**: Loads strategy from database per instance
5. **Minimal Coupling**: TradingCycle only knows about `BaseAnalysisModule` interface

## Example: Adding ML Strategy

```python
# Create file: python/trading_bot/strategies/ml_strategy.py
class MLAnalysisModule(BaseAnalysisModule):
    def analyze_chart(self, image_path, target_timeframe=None, **kwargs):
        # Your ML logic here
        return {
            "recommendation": "buy",
            "confidence": 0.85,
            # ... all required fields
        }

# Register in __init__.py
StrategyFactory.register_strategy("ml", MLAnalysisModule)

# Use in instance settings
{"strategy": "ml", "strategy_config": {...}}
```

That's it! No changes to TradingCycle, no database migrations, no API changes.

## Testing Strategy
1. Unit tests: Verify PromptAnalysisModule output format
2. Integration tests: Run TradingCycle with PromptAnalysisModule
3. Compatibility tests: Verify recommendations stored identically
4. Regression tests: Ensure no behavior changes

## Success Criteria
- ✅ PromptAnalysisModule wraps current analyzer perfectly
- ✅ TradingCycle uses StrategyFactory
- ✅ Output format identical to current system
- ✅ Database storage identical to current system
- ✅ New strategies can be added without TradingCycle changes
- ✅ Each instance can use different strategy
- ✅ All tests pass


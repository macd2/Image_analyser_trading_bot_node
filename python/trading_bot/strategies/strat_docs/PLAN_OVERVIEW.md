# Pluggable Strategy System - Complete Plan Overview

## 📋 What We're Building

A drop-in strategy system where:
- ✅ Each instance can use a different strategy (Prompt, Alex, ML, Custom, etc.)
- ✅ All strategies return identical output format (100% compatible)
- ✅ Everything after the strategy (ranking, execution, trades) stays the same
- ✅ No database schema changes needed
- ✅ Minimal changes to TradingCycle (~20 lines)
- ✅ New strategies are truly plug-and-play

## 🎯 Current State

### What Already Exists
1. **Strategy Infrastructure** (in `python/trading_bot/strategies/`)
   - `BaseAnalysisModule`: Abstract base class defining output contract
   - `StrategyFactory`: Factory pattern for creating strategies
   - `CandleAdapter`: Unified candle data interface
   - `AlexAnalysisModule`: Example alternative strategy

2. **Database Support**
   - `instances.settings` JSON blob stores: `{"strategy": "name", "strategy_config": {...}}`
   - `StrategyFactory.create()` loads strategy from database

3. **Current System**
   - Single monolithic strategy: Sourcer → Cleaner → Analyzer
   - Analyzer hardcoded in TradingCycle
   - Output format already standardized

## 📐 The Plan (4 Phases)

### Phase 1: Wrap Current Analyzer
**File**: Create `python/trading_bot/strategies/prompt_analysis_module.py`
- Wraps `ChartAnalyzer` in `BaseAnalysisModule`
- Returns exact same output format
- No behavior changes
- **Result**: Current system becomes pluggable

### Phase 2: Update TradingCycle
**File**: Modify `python/trading_bot/engine/trading_cycle.py`
- Replace: `self.analyzer = ChartAnalyzer(...)`
- With: `self.strategy = StrategyFactory.create(instance_id, config)`
- Replace: `self.analyzer.analyze_chart(...)` 
- With: `self.strategy.analyze_chart(...)`
- **Result**: TradingCycle is strategy-agnostic

### Phase 3: UI Strategy Selection (Optional)
**Files**: Instance settings modal
- Add dropdown to select strategy
- Add JSON editor for strategy config
- **Result**: Users can switch strategies per instance

### Phase 4: Add New Strategies (Drop-in)
**For each new strategy**:
1. Create file: `python/trading_bot/strategies/[name]_module.py`
2. Extend `BaseAnalysisModule`
3. Implement `analyze_chart()` method
4. Return standardized output
5. Register in `StrategyFactory`
- **Result**: New strategies work immediately

## 🔐 Key Guarantees

### 100% Output Compatibility
All strategies return this exact format:
```python
{
    "recommendation": "buy|hold|sell",
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
}
```

### Database Unchanged
- `recommendations` table: Same schema, same storage
- `instances.settings`: Already supports strategy config
- Downstream processing: Completely unchanged

### Backward Compatible
- Default strategy: "prompt" (current analyzer)
- Existing instances: Work without changes
- No migrations needed

## 📝 Files to Create/Modify

### Create (1 file):
- `python/trading_bot/strategies/prompt_analysis_module.py` (~80 lines)

### Modify (3 files):
- `python/trading_bot/engine/trading_cycle.py` (~20 line changes)
- `python/trading_bot/strategies/__init__.py` (add export)
- `python/trading_bot/strategies/factory.py` (register strategy)

### Optional (UI):
- Instance settings modal (add strategy selector)

## 📚 Documentation Files Created

1. **PLUGGABLE_STRATEGY_PLAN.md** - Comprehensive plan with current state analysis
2. **STRATEGY_IMPLEMENTATION_DETAILS.md** - Code structure and examples
3. **STRATEGY_PLAN_SUMMARY.md** - Executive summary
4. **STRATEGY_IMPLEMENTATION_CHECKLIST.md** - Task checklist for implementation
5. **STRATEGY_CODE_LOCATIONS.md** - Exact file locations and line numbers
6. **PLAN_OVERVIEW.md** - This file

## ✅ Success Criteria

- ✅ PromptAnalysisModule wraps current analyzer perfectly
- ✅ TradingCycle uses StrategyFactory
- ✅ Output format identical to current system
- ✅ Database storage identical to current system
- ✅ New strategies can be added without TradingCycle changes
- ✅ Each instance can use different strategy
- ✅ All tests pass
- ✅ No breaking changes

## 🚀 Next Steps

1. Review this plan
2. Approve implementation approach
3. Create PromptAnalysisModule
4. Update TradingCycle
5. Write tests
6. Deploy and verify

---

**Status**: ✅ PLAN COMPLETE - Ready for implementation
**Complexity**: LOW - Minimal code changes, maximum flexibility
**Risk**: VERY LOW - No database changes, backward compatible
**Timeline**: 1-2 days for full implementation

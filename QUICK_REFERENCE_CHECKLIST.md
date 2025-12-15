# Quick Reference - Implementation Checklist

## Files to Modify

### ✅ File 1: `python/trading_bot/strategies/base.py`

- [ ] Line 12: Add `Callable` to imports
- [ ] Line 38: Add `heartbeat_callback: Optional[Callable] = None` parameter
- [ ] Line 52: Add `self.heartbeat_callback = heartbeat_callback`
- [ ] After line 119: Add `_heartbeat()` method

**Total changes:** 4 locations

---

### ✅ File 2: `python/trading_bot/strategies/factory.py`

- [ ] Line 10: Add `Callable` to imports
- [ ] Line 43: Add `heartbeat_callback: Optional[Callable] = None` parameter
- [ ] Line 106: Add `heartbeat_callback=heartbeat_callback,` to return statement

**Total changes:** 3 locations

---

### ✅ File 3: `python/trading_bot/strategies/alex_analysis_module.py`

- [ ] Line 13: Add `Callable` to imports
- [ ] Line 38: Add `heartbeat_callback: Optional[Callable] = None` parameter
- [ ] Line 41: Pass `heartbeat_callback` to `super().__init__()`
- [ ] Line 62: Add `self._heartbeat(f"Starting analysis for {len(symbols)} symbols")`
- [ ] Line 68: Add `self._heartbeat(f"Analyzing {symbol}")`
- [ ] Line 145: Add `self._heartbeat(f"Completed {symbol}")`
- [ ] Line 159: Add `self._heartbeat(f"Error analyzing {symbol}: {e}")`
- [ ] Line 161: Add `self._heartbeat("Analysis cycle complete")`

**Total changes:** 8 locations

---

### ✅ File 4: `python/trading_bot/strategies/cointegration_analysis_module.py`

- [ ] CREATE NEW FILE
- [ ] Copy content from STRATEGY_FILES_ADJUSTMENTS.md section 6
- [ ] Verify PAIR_CONFIG dict is correct
- [ ] Verify all heartbeat calls are present
- [ ] Verify output format matches base.py requirements

**Total lines:** ~200

---

### ✅ File 5: `python/trading_bot/strategies/__init__.py`

- [ ] Line 14: Add import: `from trading_bot.strategies.cointegration_analysis_module import CointegrationAnalysisModule`
- [ ] After line 14: Add registration: `StrategyFactory.register_strategy("cointegration", CointegrationAnalysisModule)`
- [ ] Line 20: Add `"CointegrationAnalysisModule",` to `__all__`

**Total changes:** 3 locations

---

### ✅ File 6: `python/trading_bot/engine/trading_cycle.py`

- [ ] Line 108-112: Replace ChartAnalyzer creation with StrategyFactory.create()
  - Add import: `from trading_bot.strategies.factory import StrategyFactory`
  - Replace hardcoded analyzer with: `self.strategy = StrategyFactory.create(...)`
  
- [ ] Line 730-820: Replace `_analyze_all_charts_parallel()` method
  - Remove old method entirely
  - Add new method that calls `self.strategy.run_analysis_cycle()`
  
- [ ] Remove `_analyze_chart_async()` method (no longer needed)

**Total changes:** 2 major changes

---

## Verification Checklist

After making changes:

- [ ] All imports are correct
- [ ] No syntax errors
- [ ] All files can be imported without errors
- [ ] StrategyFactory can create both strategies
- [ ] Chart strategy still works (backward compatible)
- [ ] Cointegration strategy returns correct format
- [ ] Heartbeat callbacks are called
- [ ] Database queries still work
- [ ] Error handling works for both strategies

---

## Testing Checklist

- [ ] Import all modified files
- [ ] Create chart strategy: `StrategyFactory.create("test", config, heartbeat_callback=...)`
- [ ] Create cointegration strategy: Set instance strategy to "cointegration" in database
- [ ] Run analysis cycle for both strategies
- [ ] Verify output format matches requirements
- [ ] Verify heartbeat messages appear
- [ ] Verify downstream code (ranking, execution) works
- [ ] Run full trading cycle with both strategies

---

## Rollback Plan

If something breaks:

1. Revert `trading_cycle.py` to use hardcoded ChartAnalyzer
2. Keep other files as-is (they're backward compatible)
3. Chart strategy will continue to work

---

## Key Points to Remember

✅ Each strategy is COMPLETELY INDEPENDENT  
✅ Both strategies return SAME output format  
✅ Heartbeat is strategy's responsibility  
✅ Pair config is simple dict (can move to settings later)  
✅ No changes to downstream code  
✅ Fully backward compatible  

---

## File Dependencies

```
base.py (foundation)
  ↓
factory.py (uses base.py)
  ↓
alex_analysis_module.py (extends base.py)
cointegration_analysis_module.py (extends base.py)
  ↓
__init__.py (registers both)
  ↓
trading_cycle.py (uses factory.py)
```

**Implementation order matters** - start with base.py, end with trading_cycle.py

---

## Quick Copy-Paste Locations

| File | Location | What to Add |
|------|----------|------------|
| base.py | Line 12 | `Callable` import |
| base.py | Line 38 | `heartbeat_callback` param |
| base.py | Line 52 | Store `heartbeat_callback` |
| base.py | After 119 | `_heartbeat()` method |
| factory.py | Line 10 | `Callable` import |
| factory.py | Line 43 | `heartbeat_callback` param |
| factory.py | Line 106 | Pass `heartbeat_callback` |
| alex_analysis_module.py | Line 13 | `Callable` import |
| alex_analysis_module.py | Line 38 | `heartbeat_callback` param |
| alex_analysis_module.py | Line 41 | Pass to super() |
| alex_analysis_module.py | Lines 62,68,145,159,161 | `_heartbeat()` calls |
| cointegration_analysis_module.py | NEW | Entire file |
| __init__.py | Line 14 | Import |
| __init__.py | After 14 | Register |
| __init__.py | Line 20 | Add to __all__ |
| trading_cycle.py | Line 108 | Replace analyzer creation |
| trading_cycle.py | Line 730 | Replace _analyze_all_charts_parallel() |

---

## Estimated Time

- base.py: 5 minutes
- factory.py: 3 minutes
- alex_analysis_module.py: 5 minutes
- cointegration_analysis_module.py: 10 minutes
- __init__.py: 2 minutes
- trading_cycle.py: 10 minutes
- Testing: 15 minutes

**Total: ~50 minutes**

---

## Success Criteria

✅ All files compile without errors  
✅ Both strategies can be instantiated  
✅ Both strategies return correct output format  
✅ Heartbeat callbacks are called  
✅ Downstream code works unchanged  
✅ Backward compatible with existing instances  


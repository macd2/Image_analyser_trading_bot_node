# Pluggable Strategy System - Implementation Checklist

## Phase 1: Create PromptAnalysisModule ✓ PLAN COMPLETE

### Tasks
- [ ] Create `python/trading_bot/strategies/prompt_analysis_module.py`
  - [ ] Extend `BaseAnalysisModule`
  - [ ] Initialize `ChartSourcer`, `ChartCleaner`, `ChartAnalyzer` in `__init__`
  - [ ] Implement `analyze_symbols()` method
  - [ ] Loop through symbols and analyze each
  - [ ] Return list of standardized recommendation dicts
  - [ ] Include reproducibility fields: strategy_name, strategy_version, strategy_config, raw_response
  - [ ] Add docstring and type hints

- [ ] Update `python/trading_bot/strategies/__init__.py`
  - [ ] Import `PromptAnalysisModule`
  - [ ] Add to `__all__` exports

- [ ] Update `python/trading_bot/strategies/factory.py`
  - [ ] Register "prompt" strategy in module initialization
  - [ ] Verify `StrategyFactory.register_strategy("prompt", PromptAnalysisModule)`

### Verification
- [ ] PromptAnalysisModule returns exact same output as current system
- [ ] Output format matches BaseAnalysisModule contract
- [ ] All required fields present including reproducibility fields
- [ ] No behavior changes from current system
- [ ] Each recommendation includes: strategy_name, strategy_version, strategy_config, raw_response

---

## Phase 2: Update TradingCycle ✓ PLAN COMPLETE

### Tasks
- [ ] Modify `python/trading_bot/engine/trading_cycle.py`

  **In `__init__()` method (around line 103)**:
  - [ ] Remove: `self.analyzer = ChartAnalyzer(...)`
  - [ ] Remove: `self.sourcer = ChartSourcer(...)`
  - [ ] Remove: `self.cleaner = ChartCleaner(...)`
  - [ ] Add: `from trading_bot.strategies.factory import StrategyFactory`
  - [ ] Add: `self.strategy = StrategyFactory.create(self.instance_id, self.config, self.run_id)`

  **In `_analyze_cycle_async()` method (around line 747)**:
  - [ ] Replace: Manual sourcing/cleaning/analyzing
  - [ ] With: `recommendations = self.strategy.analyze_symbols(symbols, timeframe, cycle_id)`
  - [ ] Keep: All downstream processing unchanged

  **In `_record_recommendation()` method (around line 1190)**:
  - [ ] Extract reproducibility fields from recommendation dict
  - [ ] Store: strategy_name, strategy_version, strategy_config, raw_response to database
  - [ ] Example: `strategy_name = rec.get("strategy_name", "unknown")`

### Verification
- [ ] TradingCycle initializes without errors
- [ ] Strategy is loaded from database per instance
- [ ] Analysis results identical to before
- [ ] Recommendations stored with all reproducibility fields
- [ ] Every trade can be traced back to exact strategy, version, and config

---

## Phase 3: Testing ✓ PLAN COMPLETE

### Unit Tests
- [ ] Test PromptAnalysisModule output format
- [ ] Test reproducibility fields present (strategy_name, strategy_version, strategy_config, raw_response)
- [ ] Test output validation
- [ ] Test error handling
- [ ] Test config loading from database

### Integration Tests
- [ ] Run TradingCycle with PromptAnalysisModule
- [ ] Verify recommendations stored identically
- [ ] Verify reproducibility fields stored in database
- [ ] Verify downstream processing unchanged
- [ ] Test with multiple instances using same strategy

### Regression Tests
- [ ] Compare output with current system
- [ ] Verify no behavior changes
- [ ] Check database schema unchanged
- [ ] Verify all tests pass
- [ ] Verify trades are reproducible with stored config

---

## Phase 4: UI Updates (Optional) ✓ PLAN COMPLETE

### Instance Settings Modal
- [ ] Add "Strategy" dropdown
  - [ ] Options: prompt, technical, ml, custom, etc.
  - [ ] Default: "prompt"

- [ ] Add "Strategy Config" JSON editor
  - [ ] Load from `instances.settings.strategy_config`
  - [ ] Save to database
  - [ ] Validate JSON format

### Instance Card
- [ ] Display current strategy name
- [ ] Display strategy version
- [ ] Show strategy config summary

---

## Phase 5: Database Updates ✓ PLAN COMPLETE

### Recommendations Table
- [ ] Add `strategy_name` column (TEXT)
- [ ] Add `strategy_version` column (TEXT)
- [ ] Add `strategy_config` column (JSONB)
- [ ] Verify `raw_response` column exists
- [ ] Verify `chart_path` is nullable

### Migration
- [ ] Create migration script if needed
- [ ] Set defaults for existing records
- [ ] Verify backward compatibility

---

## Phase 6: Documentation ✓ PLAN COMPLETE

### User Documentation
- [ ] How to select strategy per instance
- [ ] How to configure strategy settings
- [ ] Available strategies and their configs
- [ ] How to replay/reproduce trades

### Developer Documentation
- [ ] How to create new strategy
- [ ] BaseAnalysisModule interface
- [ ] Output format contract with reproducibility fields
- [ ] Registration process
- [ ] Example: Technical Analysis Strategy
- [ ] Example: ML Strategy

---

## Phase 7: Add Example Strategies (Optional) ✓ PLAN COMPLETE

### For Each New Strategy
- [ ] Create file: `python/trading_bot/strategies/[name]_module.py`
- [ ] Extend `BaseAnalysisModule`
- [ ] Implement `analyze_symbols()` method
- [ ] Return standardized output format
- [ ] Include reproducibility fields
- [ ] Add docstring and type hints
- [ ] Register in `StrategyFactory`
- [ ] Add to `__init__.py` exports
- [ ] Add to UI dropdown
- [ ] Add documentation

### Example Strategies
- [ ] TechnicalAnalysisModule (API-based, no charts)
- [ ] MLAnalysisModule (ML-based, historical data)
- [ ] HybridAnalysisModule (mix of sources)

---

## Verification Checklist

### Code Quality
- [ ] All type hints present
- [ ] Docstrings complete
- [ ] Error handling robust
- [ ] Logging comprehensive
- [ ] No hardcoded values

### Reproducibility
- [ ] strategy_name stored for every recommendation
- [ ] strategy_version stored for every recommendation
- [ ] strategy_config stored for every recommendation
- [ ] raw_response stored for every recommendation
- [ ] Can replay analysis with stored config

### Compatibility
- [ ] Output format 100% identical
- [ ] Database schema backward compatible
- [ ] API signatures unchanged
- [ ] Backward compatible
- [ ] No breaking changes

### Testing
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All regression tests pass
- [ ] Reproducibility tests pass
- [ ] No new warnings/errors
- [ ] Coverage maintained

### Documentation
- [ ] Plan documented
- [ ] Implementation documented
- [ ] Examples provided
- [ ] User guide complete
- [ ] Developer guide complete
- [ ] Reproducibility guide complete

---

## Success Criteria

✅ **Phase 1**: PromptAnalysisModule wraps current analyzer perfectly
✅ **Phase 2**: TradingCycle uses StrategyFactory
✅ **Phase 3**: All tests pass
✅ **Phase 4**: UI allows strategy selection
✅ **Phase 5**: Database stores reproducibility fields
✅ **Phase 6**: Documentation complete
✅ **Phase 7**: New strategies can be added without TradingCycle changes
✅ **CRITICAL**: Every trade is fully reproducible

## Notes
- No database migrations needed (columns can be added)
- No API changes
- Backward compatible
- Minimal code changes
- Maximum flexibility
- **Full reproducibility guaranteed**


# Strategy Type Handling - Complete Implementation Plan

## Overview
Elegant solution to handle different strategy types (price-based vs spread-based) without code duplication.

## Two-Part Solution

### Part 1: Strategy Type Declaration & Polymorphism (5 tasks)
Makes strategies self-aware and encapsulates their own logic.

1. **Add STRATEGY_TYPE to BaseAnalysisModule**
   - Add `STRATEGY_TYPE` class property
   - Add `get_exit_condition()` abstract method
   - Add `get_monitoring_metadata()` abstract method

2. **Implement in PromptStrategy**
   - `STRATEGY_TYPE = "price_based"`
   - `get_exit_condition()` → price-level checks
   - `get_monitoring_metadata()` → entry, SL, TP

3. **Implement in CointegrationAnalysisModule**
   - `STRATEGY_TYPE = "spread_based"`
   - `get_exit_condition()` → z-score checks
   - `get_monitoring_metadata()` → spread data, beta, pair

4. **Update Simulator**
   - Call `strategy.get_exit_condition()` instead of hardcoded checks
   - Works for any strategy type automatically

5. **Update Position Monitor**
   - Call `strategy.get_monitoring_metadata()` to know what to track
   - Applies correct monitoring logic per strategy type

### Part 2: Strategy-Specific Settings (4 tasks)
Allows each strategy type to have its own configuration.

1. **Add Settings to Defaults**
   - Spread-based: z_score_monitoring_interval, spread_reversion_threshold, etc.
   - Price-based: existing RR tightening, SL tightening settings

2. **Extend TradingConfig**
   - Add `price_based_settings` field
   - Add `spread_based_settings` field
   - Each with proper dataclass structure

3. **Update Config Loading**
   - Detect strategy type from instance
   - Load appropriate strategy-specific settings
   - Merge with common trading settings

4. **Update SettingsModal UI**
   - Filter settings by strategy type
   - Show only relevant configuration options
   - Improve UX for multi-strategy system

## Architecture Benefits

✅ **Elegant**: Each strategy encapsulates its own logic  
✅ **Extensible**: New strategies don't require simulator/monitor changes  
✅ **Type-Safe**: Clear contract between strategy and downstream  
✅ **No Duplication**: Logic lives in one place  
✅ **Configurable**: Each strategy has its own settings  
✅ **UI-Friendly**: Dashboard shows only relevant options  

## Execution Order

**Phase 1** (Strategy Polymorphism):
1. Add STRATEGY_TYPE and abstract methods to BaseAnalysisModule
2. Implement in PromptStrategy
3. Implement in CointegrationAnalysisModule
4. Update simulator
5. Update position monitor

**Phase 2** (Settings):
1. Add settings to defaults
2. Extend TradingConfig
3. Update config loading
4. Update SettingsModal

## Key Files Modified

**Python**:
- `python/trading_bot/strategies/base.py` (BaseAnalysisModule)
- `python/trading_bot/strategies/prompt/prompt_strategy.py`
- `python/trading_bot/strategies/cointegration/cointegration_analysis_module.py`
- `python/trading_bot/engine/paper_trade_simulator.py`
- `python/trading_bot/engine/enhanced_position_monitor.py`
- `python/trading_bot/config/settings_v2.py`
- `python/trading_bot/db/config_defaults.py`

**TypeScript**:
- `app/api/bot/simulator/auto-close/route.ts`
- `components/instance/modals/SettingsModal.tsx`
- `lib/config-defaults.ts`

## Testing Strategy

- Unit tests for each strategy's `get_exit_condition()` and `get_monitoring_metadata()`
- Integration tests for simulator with both strategy types
- Integration tests for position monitor with both strategy types
- UI tests for SettingsModal filtering


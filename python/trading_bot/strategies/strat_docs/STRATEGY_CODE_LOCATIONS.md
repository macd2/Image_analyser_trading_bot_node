# Pluggable Strategy System - Code Locations

## Files to Create

### `python/trading_bot/strategies/prompt_analysis_module.py` (NEW)
Wraps current ChartAnalyzer as pluggable strategy

---

## Files to Modify

### 1. `python/trading_bot/engine/trading_cycle.py`

**Change 1 - Line 103-108**: Replace analyzer init
```python
# OLD: self.analyzer = ChartAnalyzer(...)
# NEW: self.strategy = StrategyFactory.create(instance_id, config, run_id)
```

**Change 2 - Line 747-754**: Replace analyzer call
```python
# OLD: self.analyzer.analyze_chart(...)
# NEW: self.strategy.analyze_chart(...)
```

**Change 3 - Line 1190**: Update prompt_name
```python
# OLD: prompt_name = self.config.prompt_name or "default"
# NEW: strategy_name = self.strategy.__class__.__name__
#      prompt_name = f"{strategy_name}_{self.config.prompt_name or 'default'}"
```

### 2. `python/trading_bot/strategies/__init__.py`

Add import and export:
```python
from trading_bot.strategies.prompt_analysis_module import PromptAnalysisModule

__all__ = [
    "BaseAnalysisModule",
    "CandleAdapter",
    "StrategyFactory",
    "AlexAnalysisModule",
    "PromptAnalysisModule",  # ADD THIS
]
```

### 3. `python/trading_bot/strategies/factory.py`

Register strategy (after class definition):
```python
StrategyFactory.register_strategy("prompt", PromptAnalysisModule)
```

---

## Key Locations Reference

### Strategy Infrastructure (Already Exists)
- `BaseAnalysisModule`: `strategies/base.py` line 19-176
- `StrategyFactory`: `strategies/factory.py` line 15-118
- `CandleAdapter`: `strategies/candle_adapter.py`
- `AlexAnalysisModule`: `strategies/alex_analysis_module.py`

### Database (No Changes Needed)
- Recommendations table: `lib/db/schema.sql` line 59-79
- Instance settings: `lib/db/trading-db.ts` line 315-327
- Python DB client: `python/trading_bot/db/client.py`

### Output Format Contract
- Analyzer output: `core/analyzer.py` line 478-530
- Prompt format: `core/prompts/analyzer_prompt.py` line 2517-2538
- Validation: `strategies/base.py` line 140-176

---

## Import Statements Needed

### In trading_cycle.py
```python
from trading_bot.strategies.factory import StrategyFactory
```

### In prompt_analysis_module.py
```python
from trading_bot.strategies.base import BaseAnalysisModule
from trading_bot.core.analyzer import ChartAnalyzer
from trading_bot.core.bybit_api_manager import BybitAPIManager
from openai import OpenAI
```

---

## Summary of Changes

| File | Type | Lines | Change |
|------|------|-------|--------|
| `prompt_analysis_module.py` | CREATE | ~80 | New wrapper |
| `trading_cycle.py` | MODIFY | 103-108 | Replace init |
| `trading_cycle.py` | MODIFY | 747-754 | Replace call |
| `trading_cycle.py` | MODIFY | 1190 | Update name |
| `strategies/__init__.py` | MODIFY | 1-21 | Add export |
| `strategies/factory.py` | MODIFY | ~20 | Register |

**Total**: ~6 locations, ~20 lines of code changes

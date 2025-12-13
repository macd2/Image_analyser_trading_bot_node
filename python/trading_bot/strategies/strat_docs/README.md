# Pluggable Strategy System - Documentation Index

## Quick Start

Start here to understand the architecture:
1. **[STRATEGY_PLAN_SUMMARY.md](STRATEGY_PLAN_SUMMARY.md)** - Executive summary (5 min read)
2. **[PLUGGABLE_STRATEGY_PLAN.md](PLUGGABLE_STRATEGY_PLAN.md)** - Full architecture (15 min read)
3. **[REPRODUCIBILITY_GUARANTEE.md](REPRODUCIBILITY_GUARANTEE.md)** - How trades are reproducible (10 min read)

## Implementation

For developers implementing the system:
1. **[STRATEGY_IMPLEMENTATION_DETAILS.md](STRATEGY_IMPLEMENTATION_DETAILS.md)** - Code structure and examples
2. **[STRATEGY_IMPLEMENTATION_CHECKLIST.md](STRATEGY_IMPLEMENTATION_CHECKLIST.md)** - Step-by-step tasks
3. **[STRATEGY_CODE_LOCATIONS.md](STRATEGY_CODE_LOCATIONS.md)** - Exact file locations and line numbers

## Examples & Testing

For creating new strategies:
1. **[EXAMPLE_USAGE.md](EXAMPLE_USAGE.md)** - How to use strategies
2. **[ALEX_EXAMPLE.md](ALEX_EXAMPLE.md)** - Example: AlexAnalysisModule
3. **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - How to test strategies

## Core Concepts

### What is a Strategy?

A strategy is a **black box** that:
- **Takes**: symbols, timeframe, cycle_id
- **Does**: Analyzes data (charts, API, ML, indicators, etc.)
- **Returns**: Standardized recommendation format
- **Guarantees**: 100% compatibility with downstream code

### Key Principle: Strategies are Independent

Each strategy can have completely different implementation:
- **Chart-based**: Uses TradingView charts + AI analysis
- **API-based**: Uses Bybit API candles + technical indicators
- **ML-based**: Uses historical data + machine learning
- **Hybrid**: Mix of sources

All return the same standardized format.

### Reproducibility is Built In

Every recommendation includes:
- `strategy_name`: Which strategy (e.g., "prompt", "technical")
- `strategy_version`: Version (e.g., "1.0", "2.1")
- `strategy_config`: Full config used
- `raw_response`: Full response for replay

**This means**: Every trade can be replayed and debugged.

## Architecture Overview

```
TradingCycle (Orchestrator)
    ↓
StrategyFactory.create(instance_id, config)
    ↓
Strategy (Black Box)
    ├── Chart-based: Sourcer → Cleaner → Analyzer
    ├── API-based: Fetch candles → Calculate indicators
    ├── ML-based: Extract features → Run model
    └── Custom: Whatever you want
    ↓
Standardized Output
    ├── recommendation, confidence, entry_price, stop_loss, take_profit
    ├── strategy_name, strategy_version, strategy_config, raw_response
    └── chart_path (optional)
    ↓
Database Storage
    ├── recommendations table
    ├── Full audit trail
    └── Fully reproducible
    ↓
Downstream Processing
    ├── Ranking (unchanged)
    ├── Execution (unchanged)
    └── Trades (unchanged)
```

## File Structure

```
python/trading_bot/strategies/
├── strat_docs/                          # This directory
│   ├── README.md                        # This file
│   ├── STRATEGY_PLAN_SUMMARY.md         # Executive summary
│   ├── PLUGGABLE_STRATEGY_PLAN.md       # Full architecture
│   ├── REPRODUCIBILITY_GUARANTEE.md     # Reproducibility details
│   ├── STRATEGY_IMPLEMENTATION_DETAILS.md
│   ├── STRATEGY_IMPLEMENTATION_CHECKLIST.md
│   ├── STRATEGY_CODE_LOCATIONS.md
│   ├── EXAMPLE_USAGE.md
│   ├── ALEX_EXAMPLE.md
│   └── TESTING_GUIDE.md
├── base.py                              # BaseAnalysisModule (interface)
├── factory.py                           # StrategyFactory
├── prompt_analysis_module.py            # Chart-based strategy (TO CREATE)
├── alex_analysis_module.py              # Technical analysis example
├── candle_adapter.py                    # Unified candle interface
└── __init__.py                          # Exports
```

## Implementation Phases

### Phase 1: Create PromptAnalysisModule
- Wrap current ChartAnalyzer
- Implement `analyze_symbols()` method
- Include reproducibility fields
- Register in StrategyFactory

### Phase 2: Update TradingCycle
- Remove hardcoded analyzer/sourcer/cleaner
- Load strategy via StrategyFactory
- Call `strategy.analyze_symbols()`
- Store reproducibility fields

### Phase 3: UI Strategy Selection (Optional)
- Add strategy dropdown
- Add config JSON editor
- Display strategy info

### Phase 4: Add New Strategies (Drop-in)
- Create new strategy file
- Extend BaseAnalysisModule
- Implement `analyze_symbols()`
- Register and use

## Key Files to Modify

1. **python/trading_bot/strategies/prompt_analysis_module.py** (CREATE)
   - Wrap current analyzer
   - Implement analyze_symbols()

2. **python/trading_bot/engine/trading_cycle.py** (MODIFY)
   - Remove analyzer/sourcer/cleaner
   - Load strategy via factory
   - Call strategy.analyze_symbols()

3. **python/trading_bot/strategies/__init__.py** (MODIFY)
   - Export PromptAnalysisModule

4. **python/trading_bot/strategies/factory.py** (MODIFY)
   - Register PromptAnalysisModule

## Database Changes

### New Columns in recommendations table
- `strategy_name` (TEXT): Which strategy
- `strategy_version` (TEXT): Version
- `strategy_config` (JSONB): Full config
- `raw_response` (TEXT): Full response

### Existing Columns (Unchanged)
- `chart_path` (TEXT, nullable): For chart-based strategies
- All other fields unchanged

## Success Criteria

✅ PromptAnalysisModule wraps current analyzer perfectly
✅ TradingCycle uses StrategyFactory
✅ Output format 100% identical
✅ Database stores reproducibility fields
✅ Every trade is fully reproducible
✅ New strategies can be added without TradingCycle changes
✅ All tests pass

## Questions?

Refer to the specific documentation files:
- **"How do I create a new strategy?"** → STRATEGY_IMPLEMENTATION_DETAILS.md
- **"What's the output format?"** → PLUGGABLE_STRATEGY_PLAN.md
- **"How do I test?"** → TESTING_GUIDE.md
- **"How are trades reproducible?"** → REPRODUCIBILITY_GUARANTEE.md
- **"What are the exact changes?"** → STRATEGY_IMPLEMENTATION_CHECKLIST.md
- **"Where do I make changes?"** → STRATEGY_CODE_LOCATIONS.md

# Prompt Strategy - Self-Contained Implementation

## Overview

The Prompt Strategy is a **completely independent, self-contained trading strategy** that replicates all functionality from the current trading cycle.

## Architecture

```
python/trading_bot/strategies/prompt/
├── __init__.py                 # Package initialization
├── prompt_strategy.py          # Main strategy orchestration
├── sourcer.py                  # Chart capture (local copy)
├── cleaner.py                  # Chart cleanup (local copy)
├── analyzer.py                 # Chart analysis (local copy)
└── README.md                   # This file
```

## Key Features

✅ **Completely Independent**
- Full copies of sourcer, cleaner, analyzer (not wrappers)
- No dependencies on core modules
- Can be modified without affecting core

✅ **Full Functionality**
- Captures charts from TradingView watchlist
- Cleans outdated chart files
- Analyzes charts using OpenAI Assistant API
- Returns standardized recommendations

✅ **Pluggable**
- Extends BaseAnalysisModule
- Registered in StrategyFactory
- Can be swapped with other strategies

✅ **Instance-Aware**
- Loads config from database
- Tracks cycle_id for audit trail
- Supports multi-instance trading

## Data Flow

```
PromptStrategy.run_analysis_cycle()
    ↓
Sourcer: Capture charts from watchlist
    ↓
Cleaner: Remove outdated files
    ↓
Analyzer: Analyze with OpenAI
    ↓
Returns List[Dict] with recommendations
    ↓
TradingCycle._record_recommendation()
    ↓
INSERT INTO recommendations table
```

## Output Format

Each recommendation includes:
- Trading fields: symbol, recommendation, confidence, prices
- Analysis data: full analyzer result with metadata
- Audit trail: prompt_id, prompt_version, assistant_model
- Market snapshot: market data fed to AI

## Usage

```python
from trading_bot.strategies.factory import StrategyFactory

# Create strategy
strategy = StrategyFactory.create(
    instance_id="my-instance",
    config=config,
    run_id="run-123"
)

# Run analysis
recommendations = await strategy.run_analysis_cycle(
    symbols=[],  # Ignored - uses watchlist
    timeframe="",  # Ignored - uses config
    cycle_id="cycle-456"
)
```

## Independence

This strategy is **completely independent**:
- Has its own copies of sourcer, cleaner, analyzer
- Can be modified without affecting core modules
- Can be tested in isolation
- Can be deployed separately


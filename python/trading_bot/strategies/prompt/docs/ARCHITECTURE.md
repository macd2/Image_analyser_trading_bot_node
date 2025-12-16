# PromptStrategy Architecture

## Overview

PromptStrategy is a **completely self-contained, pluggable trading strategy** that replicates all functionality from the current trading cycle. It can be swapped with other strategies through the StrategyFactory without modifying TradingCycle.

## Directory Structure

```
python/trading_bot/strategies/prompt/
├── __init__.py                          # Package initialization
├── prompt_strategy.py                   # Main strategy orchestration (281 lines)
├── sourcer.py                           # Chart capture (3.8K lines - local copy)
├── cleaner.py                           # Chart cleanup (330 lines - local copy)
├── analyzer.py                          # Chart analysis (1085 lines - local copy)
├── ARCHITECTURE.md                      # This file
├── README.md                            # Quick start guide
├── TEST_RESULTS.md                      # Test results and how to run tests
└── test_prompt_strategy_*.py            # Test files
```

## Component Architecture

### 1. PromptStrategy (Main Orchestrator)
**File:** `prompt_strategy.py`

Extends `BaseAnalysisModule` and orchestrates the entire analysis cycle:

```
run_analysis_cycle()
    ↓
STEP 0: Clean outdated charts
    ↓
STEP 1: Capture charts from TradingView
    ↓
STEP 2: Analyze charts with OpenAI
    ↓
Return List[Dict] with recommendations
```

**Key Methods:**
- `run_analysis_cycle()` - Main entry point
- `_analyze_all_charts_parallel()` - Parallel chart analysis
- `_analyze_chart_async()` - Single chart analysis
- `_validate_output()` - Output format validation

### 2. ChartSourcer (Chart Capture)
**File:** `sourcer.py` (local copy from core)

Captures chart images from TradingView watchlist:
- Authenticates with TradingView
- Navigates to chart URLs
- Captures screenshots
- Stores locally or in Supabase

### 3. ChartCleaner (Cleanup)
**File:** `cleaner.py` (local copy from core)

Manages outdated chart files:
- Removes charts older than max_file_age_hours
- Moves to backup folder
- Respects timeframe filters
- Handles both local and Supabase storage

### 4. ChartAnalyzer (Analysis)
**File:** `analyzer.py` (local copy from core)

Analyzes charts using OpenAI:
- Encodes images to base64
- Fetches market data (bid/ask, volume, etc.)
- Calls OpenAI Assistant API
- Extracts trading signals
- Validates recommendations

## Data Flow

```
TradingView Watchlist
    ↓
Sourcer: Capture charts
    ↓
Cleaner: Remove old files
    ↓
Analyzer: Analyze with AI
    ↓
Output: List[Dict] with:
  - symbol, recommendation, confidence
  - entry_price, stop_loss, take_profit
  - risk_reward, setup_quality, market_environment
  - analysis (full metadata), chart_path, timeframe, cycle_id
    ↓
TradingCycle._record_recommendation()
    ↓
Database: recommendations table
```

## Configuration

PromptStrategy loads configuration from:

1. **Database (instances.settings)**
   - Trading parameters (confidence, risk, leverage, etc.)
   - Timeframe
   - Strategy-specific settings

2. **YAML (config.yaml)**
   - Paths (charts, logs, database)
   - TradingView browser settings
   - Circuit breaker configuration

3. **Environment Variables**
   - API keys (OpenAI, Bybit)
   - Credentials

## Independence

PromptStrategy is **completely independent**:

✅ Has its own copies of sourcer, cleaner, analyzer
✅ No imports of TradingCycle
✅ No references to trading_cycle module
✅ Can be tested in isolation
✅ Can be deployed separately
✅ Can be modified without affecting core

## Integration with TradingCycle

When ready to integrate, TradingCycle will:

1. Create strategy via StrategyFactory
2. Call `strategy.run_analysis_cycle()`
3. Receive recommendations
4. Store via `_record_recommendation()`

**No changes needed to TradingCycle logic** - just swap the sourcer/cleaner/analyzer with the strategy.

## Testing

Two test suites available:

1. **Mock Tests** (no database required)
   - Tests instantiation with mock config
   - Tests component initialization
   - Tests output validation
   - Tests independence from TradingCycle

2. **Standalone Tests** (requires database instance)
   - Tests with real database config
   - Tests factory registration
   - Tests full integration

See TEST_RESULTS.md for details.


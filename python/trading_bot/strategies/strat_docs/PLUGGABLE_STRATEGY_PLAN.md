# Pluggable Strategy System - Final Architecture

## Core Principle: Strategies as Black Boxes

Each strategy is a **completely independent implementation** that:
1. Takes: `symbols`, `timeframe`, `cycle_id`
2. Does: Whatever it needs (charts, API, ML, indicators, etc.)
3. Returns: Standardized recommendation format
4. Guarantees: 100% compatibility with downstream code

---

## What Stays the Same (100% Compatibility)

### Output Format Contract (CRITICAL)
All strategies MUST return this exact format for each symbol:
```python
{
    "symbol": str,
    "timeframe": str,
    "recommendation": "LONG" | "SHORT" | "HOLD",
    "confidence": 0.0-1.0,
    "entry_price": float,
    "stop_loss": float,
    "take_profit": float,
    "risk_reward_ratio": float,
    "summary": str,
    "evidence": str,
    "direction": "Long" | "Short",
    "market_condition": "TRENDING" | "RANGING",
    "market_direction": "UP" | "DOWN" | "SIDEWAYS",
    "cycle_id": str,
    "chart_path": str | None,  # Optional - not all strategies use charts
    # CRITICAL FOR REPRODUCIBILITY
    "strategy_name": str,  # e.g., "prompt", "technical", "ml_ensemble"
    "strategy_version": str,  # e.g., "1.0", "2.1"
    "strategy_config": dict,  # Full config used for this analysis
    "raw_response": str,  # Raw output from strategy (for audit trail)
    "skipped": bool (optional),
    "skip_reason": str (optional),
    "error": bool (optional)
}
```

**Key Points**:
- `chart_path` is optional. Strategies that don't use charts set it to `None`.
- `strategy_name`, `strategy_version`, `strategy_config`, `raw_response` are **REQUIRED** for reproducibility
- Every trade can be traced back to exact strategy, version, and config used
- `raw_response` allows replaying the analysis with same inputs

### Database Storage (CRITICAL - Reproducibility Built In)
- `recommendations` table stores all strategy outputs identically
- `chart_path` column is nullable - works for all strategies
- `prompt_name` field stores strategy name for audit trail
- `raw_response` field stores full strategy output for reproducibility
- Additional fields for strategy tracking:
  - `strategy_name`: Which strategy generated this (e.g., "prompt", "technical")
  - `strategy_version`: Version of strategy (e.g., "1.0", "2.1")
  - `strategy_config`: Full config JSON used for analysis
- All downstream processing (ranking, execution, trades) is strategy-agnostic
- **Every trade is fully reproducible**: Given same symbol, timeframe, and strategy config, can replay analysis

### TradingCycle Role (Entry Point & Orchestrator)
- Loads strategy via `StrategyFactory`
- Calls `strategy.analyze_symbols(symbols, timeframe, cycle_id)`
- Records recommendations to database
- Ranks signals
- Executes trades
- **Does NOT care** how strategy gets data or processes it

---

## What Changes Per Strategy

Each strategy decides independently:
- **Input source**: Charts? API candles? Historical data? Mix?
- **Processing**: AI analysis? Technical indicators? ML model? Custom logic?
- **Implementation**: Sourcer? Cleaner? Analyzer? None of the above?

### Example: Different Strategy Implementations

**Strategy 1: Chart-Based (Current)**
```python
class PromptAnalysisModule(BaseAnalysisModule):
    def analyze_symbols(self, symbols, timeframe, cycle_id, **kwargs):
        results = []
        for symbol in symbols:
            # 1. Capture chart (sourcer)
            chart_path = self.sourcer.get_chart(symbol, timeframe)

            # 2. Clean files (cleaner)
            self.cleaner.cleanup()

            # 3. Analyze chart (analyzer)
            analysis = self.analyzer.analyze_chart(chart_path)

            # 4. Return standardized format with reproducibility fields
            results.append({
                "symbol": symbol,
                "recommendation": analysis["recommendation"],
                "confidence": analysis["confidence"],
                "entry_price": analysis["entry_price"],
                "stop_loss": analysis["stop_loss"],
                "take_profit": analysis["take_profit"],
                "risk_reward_ratio": analysis["risk_reward_ratio"],
                "chart_path": chart_path,  # Has chart
                "cycle_id": cycle_id,
                # REPRODUCIBILITY FIELDS
                "strategy_name": "prompt",
                "strategy_version": "1.0",
                "strategy_config": self.strategy_config,  # Full config
                "raw_response": json.dumps(analysis),  # Full response for replay
                # ... all other required fields
            })
        return results
```

**Strategy 2: API-Based (No Charts)**
```python
class TechnicalAnalysisModule(BaseAnalysisModule):
    def analyze_symbols(self, symbols, timeframe, cycle_id, **kwargs):
        results = []
        for symbol in symbols:
            # 1. Fetch candles from API (no sourcer)
            candles = self.api_manager.get_candles(symbol, timeframe)

            # 2. Calculate indicators (no cleaner)
            rsi = calculate_rsi(candles)
            macd = calculate_macd(candles)

            # 3. Generate signal (no analyzer)
            signal = self.generate_signal(rsi, macd)

            # 4. Return standardized format with reproducibility fields
            results.append({
                "symbol": symbol,
                "recommendation": signal["recommendation"],
                "confidence": signal["confidence"],
                "entry_price": signal["entry_price"],
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "risk_reward_ratio": signal["risk_reward_ratio"],
                "chart_path": None,  # No chart
                "cycle_id": cycle_id,
                # REPRODUCIBILITY FIELDS
                "strategy_name": "technical",
                "strategy_version": "1.0",
                "strategy_config": self.strategy_config,  # Full config
                "raw_response": json.dumps(signal),  # Full response for replay
                # ... all other required fields
            })
        return results
```

**Strategy 3: ML-Based (Historical Data)**
```python
class MLAnalysisModule(BaseAnalysisModule):
    def analyze_symbols(self, symbols, timeframe, cycle_id, **kwargs):
        results = []
        for symbol in symbols:
            # 1. Load historical data (no sourcer, no charts)
            features = self.feature_extractor.extract(symbol, timeframe)

            # 2. Run ML model (no analyzer)
            prediction = self.model.predict(features)

            # 3. Return standardized format with reproducibility fields
            results.append({
                "symbol": symbol,
                "recommendation": prediction["recommendation"],
                "confidence": prediction["confidence"],
                "entry_price": prediction["entry_price"],
                "stop_loss": prediction["stop_loss"],
                "take_profit": prediction["take_profit"],
                "risk_reward_ratio": prediction["risk_reward_ratio"],
                "chart_path": None,  # No chart
                "cycle_id": cycle_id,
                # REPRODUCIBILITY FIELDS
                "strategy_name": "ml_ensemble",
                "strategy_version": "2.1",
                "strategy_config": self.strategy_config,  # Full config
                "raw_response": json.dumps(prediction),  # Full response for replay
                # ... all other required fields
            })
        return results
```

---

## Implementation Plan

### Phase 1: Create PromptAnalysisModule (Wrap Current Analyzer)
**Goal**: Make current analyzer pluggable without changing behavior

**Steps**:
1. Create `python/trading_bot/strategies/prompt_analysis_module.py`
   - Extends `BaseAnalysisModule`
   - Implements `analyze_symbols()` method
   - Uses Sourcer + Cleaner + Analyzer (current implementation)
   - Returns standardized output format
   - Handles all error cases identically

2. Register strategy in `StrategyFactory`
   - Add to `__init__.py` exports
   - Register as "prompt" strategy (default)

3. **NO database changes needed** - output format already compatible

### Phase 2: Update TradingCycle to Use StrategyFactory
**Goal**: Make trading cycle strategy-agnostic

**Changes**:
1. In `TradingCycle.__init__()`:
   - Remove: `self.analyzer = ChartAnalyzer(...)`
   - Remove: `self.sourcer = ChartSourcer(...)`
   - Remove: `self.cleaner = ChartCleaner(...)`
   - Add: Load strategy via `StrategyFactory.create(instance_id, config)`
   - Store as: `self.strategy` (generic interface)

2. In `TradingCycle._analyze_cycle_async()`:
   - Replace: Manual sourcing/cleaning/analyzing
   - With: `self.strategy.analyze_symbols(symbols, timeframe, cycle_id)`
   - Output format unchanged - all downstream code works identically

3. In `TradingCycle._record_recommendation()`:
   - Add `strategy_name` to `prompt_name` field for audit trail
   - Example: `"prompt_v2"` or `"technical_analysis"` or `"ml_ensemble"`

### Phase 3: Create Strategy Selection UI
**Goal**: Allow users to select/configure strategies per instance

**Changes**:
1. Instance settings modal:
   - Add dropdown: "Strategy" (prompt, technical, ml, custom, etc.)
   - Add JSON editor for strategy_config
   - Save to `instances.settings`

2. Display current strategy in instance card

### Phase 4: Add New Strategies (Drop-in)
**Goal**: Demonstrate pluggability

**For each new strategy**:
1. Create file: `python/trading_bot/strategies/[name]_module.py`
2. Extend `BaseAnalysisModule`
3. Implement `analyze_symbols()` method
4. Return standardized output format
5. Register in `StrategyFactory`
6. Add to UI dropdown
7. **No changes to TradingCycle or database needed**

---

## Key Design Principles

### 1. **100% Output Compatibility**
- All strategies return identical format
- Database schema unchanged
- Downstream processing (ranking, execution, trades) unchanged
- Strategies are truly drop-in replacements

### 2. **Strategy Independence**
- Each strategy is a black box
- Can use completely different implementation
- No shared sourcer/cleaner/analyzer required
- Each strategy owns its data sourcing and processing

### 3. **Instance-Aware**
- Each instance can use different strategy
- Strategy config stored in `instances.settings`
- `StrategyFactory` loads per-instance config

### 4. **Minimal Changes to Existing Code**
- TradingCycle changes: ~30 lines
- No database migrations needed
- No API changes
- Backward compatible (default to "prompt" strategy)

### 5. **Extensible**
- New strategies just extend `BaseAnalysisModule`
- No need to modify TradingCycle or factory
- Register and use immediately

---

## Files to Create/Modify

### Create:
- `python/trading_bot/strategies/prompt_analysis_module.py` (NEW)

### Modify:
- `python/trading_bot/engine/trading_cycle.py` (TradingCycle integration)
- `python/trading_bot/strategies/__init__.py` (export PromptAnalysisModule)
- `python/trading_bot/strategies/factory.py` (register PromptAnalysisModule)

### Optional (UI):
- Instance settings modal (add strategy selector)
- Instance card (display strategy name)

---

## Testing Strategy

1. **Unit Tests**: Verify each strategy returns correct output format
2. **Integration Tests**: Run TradingCycle with different strategies
3. **Compatibility Tests**: Verify recommendations stored identically
4. **Regression Tests**: Ensure no behavior changes from current system


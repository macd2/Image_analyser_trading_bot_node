# Strategy System Testing Guide

## Overview

The pluggable strategy system has been fully implemented and tested. This guide shows how to run the tests locally.

## Test Files

### 1. **test_strategy_local.py** - Unit Tests
Tests the core strategy system components without database or API calls.

```bash
python python/test_strategy_local.py
```

**Tests:**
- ✅ Output format validation
- ✅ Instance-specific configuration loading
- ✅ Candle to DataFrame conversion
- ✅ Analysis with insufficient data
- ✅ Error handling
- ✅ StrategyFactory registration

**Result:** 6/6 tests pass

---

### 2. **test_strategy_functional.py** - Functional Tests
Tests the strategy system with real database and components.

```bash
python python/test_strategy_functional.py
```

**Tests:**
- ✅ Load instance config from database
- ✅ StrategyFactory.create() with database config
- ✅ Analysis cycle with mock candles
- ✅ Multiple instances with different configs

**Result:** 4/4 tests pass

---

### 3. **test_strategy_integration.py** - Integration Tests
Tests complete analysis cycles with realistic mock data.

```bash
python python/test_strategy_integration.py
```

**Tests:**
- ✅ Single symbol analysis
- ✅ Multiple symbols analysis
- ✅ Instance-specific configuration
- ✅ Output format consistency

**Result:** 4/4 tests pass

---

### 4. **test_strategy_live_output.py** - Live Output Demo
Shows actual strategy output with realistic candle data.

```bash
python python/test_strategy_live_output.py
```

**Output:**
- Strategy configuration
- Analysis results for 3 symbols
- Pretty-printed results with all fields
- Raw JSON output

---

### 5. **test_strategy_market_conditions.py** - Market Conditions Test
Tests strategy response to different market conditions (bullish, bearish, sideways).

```bash
python python/test_strategy_market_conditions.py
```

**Tests:**
- Strong bullish trend
- Strong bearish trend
- Sideways/neutral market

---

### 6. **test_strategy_real_candles.py** - Real Candles Test
Tests strategy with real cached candles from database.

```bash
python python/test_strategy_real_candles.py
```

**Features:**
- Fetches real candles from database cache
- Falls back to Bybit API if needed
- Shows actual market conditions detected
- Requires min_candles parameter

---

## Running All Tests

```bash
# Run all tests in sequence
python python/test_strategy_local.py && \
python python/test_strategy_functional.py && \
python python/test_strategy_integration.py && \
python python/test_strategy_live_output.py
```

---

## Key Components Tested

### BaseAnalysisModule
- Output format enforcement
- Instance-specific config loading
- Error handling
- Validation

### CandleAdapter
- Database cache lookup
- API fallback
- Minimum candles requirement
- Timeframe conversion

### StrategyFactory
- Strategy registration
- Instance-aware creation
- Config loading from database

### AlexAnalysisModule
- Trend detection
- Support/resistance identification
- Market structure analysis
- Recommendation generation

---

## Output Format

All strategies return standardized format:

```json
{
  "symbol": "BTCUSDT",
  "recommendation": "BUY|SELL|HOLD",
  "confidence": 0.75,
  "entry_price": null,
  "stop_loss": null,
  "take_profit": null,
  "risk_reward": 0,
  "setup_quality": 0.7,
  "market_environment": 0.6,
  "analysis": {
    "strategy": "alex_top_down",
    "trend": {...},
    "support_resistance": {...},
    "market_structure": {...},
    "signals": [],
    "reasoning": "..."
  },
  "chart_path": "",
  "timeframe": "1h",
  "cycle_id": "cycle-123"
}
```

---

## Instance Configuration

Strategies are configured per instance via database:

```json
{
  "strategy": "alex",
  "strategy_config": {
    "timeframes": ["1h", "4h"],
    "lookback_periods": 20,
    "min_confidence": 0.65,
    "use_volume": true
  }
}
```

Different instances can run different strategies with different settings!

---

## Next Steps

1. **Integrate with TradingCycle**: Update TradingCycle to use StrategyFactory
2. **Create PromptAnalysisModule**: Wrap existing analyzer as strategy
3. **Update UI**: Add strategy selector to instance settings modal
4. **Test with Real Data**: Run with actual Bybit candles


# Strategy Contract Integration Tests

## Overview

The `test_strategy_contract_integration.py` file contains comprehensive tests that verify:

1. **Strategy Output Format** - All strategies return the correct structure
2. **Trading Cycle Integration** - Engine can process strategy output correctly
3. **Price Level Extraction** - Prices are in the analysis dict (not top-level)
4. **Contract Validation** - BaseAnalysisModule validates output against contract
5. **Contract Invariants** - SL/TP relationships are correct for long/short trades

## Critical Contract Rule

⚠️ **The trading_cycle.py engine is the SINGLE SOURCE OF TRUTH**

- Strategies MUST conform to what the engine expects
- The engine extracts prices from `analysis.entry_price`, `analysis.stop_loss`, etc.
- Validation in `BaseAnalysisModule._validate_output()` enforces this contract
- If the engine changes, validation MUST be updated immediately

## Test Classes

### TestStrategyOutputContract
Tests that strategy output matches the contract specification.

**Tests:**
- `test_valid_strategy_output_cointegration()` - Valid cointegration output
- `test_valid_strategy_output_prompt()` - Valid prompt strategy output
- `test_missing_prices_in_analysis_dict_fails()` - Detects missing prices

### TestTradingCycleEngineExtraction
Tests that the trading cycle engine extracts prices correctly.

**Tests:**
- `test_engine_extracts_prices_from_analysis_dict()` - Engine finds prices in analysis dict
- `test_engine_handles_none_prices()` - Engine handles None values

### TestContractInvariants
Tests contract invariants for different strategy types.

**Tests:**
- `test_long_trade_invariants()` - For long: SL < entry < TP
- `test_short_trade_invariants()` - For short: TP < entry < SL

### TestBaseAnalysisModuleValidation
Tests that BaseAnalysisModule._validate_output() enforces the contract.

**Tests:**
- `test_validation_passes_for_valid_cointegration_output()` - Valid output passes
- `test_validation_fails_missing_prices_in_analysis()` - Missing prices fails
- `test_validation_fails_missing_top_level_field()` - Missing top-level field fails

## Running the Tests

```bash
# Run all contract tests
python -m pytest python/tests/test_strategy_contract_integration.py -v

# Run specific test class
python -m pytest python/tests/test_strategy_contract_integration.py::TestStrategyOutputContract -v

# Run with output
python -m pytest python/tests/test_strategy_contract_integration.py -v -s
```

## Contract Specification

### Required Top-Level Fields
```python
{
    "symbol": str,
    "recommendation": "BUY" | "SELL" | "HOLD",
    "confidence": float (0.0-1.0),
    "setup_quality": float (0.0-1.0),
    "market_environment": float (0.0-1.0),
    "analysis": dict,  # MUST contain price levels
    "chart_path": str,
    "timeframe": str,
    "cycle_id": str,
    "strategy_uuid": str,
    "strategy_type": str,
    "strategy_name": str,
}
```

### Required Analysis Dict Fields
```python
"analysis": {
    "entry_price": float | None,
    "stop_loss": float | None,
    "take_profit": float | None,
    "risk_reward_ratio": float | None,
    # ... strategy-specific fields
}
```

## Key Insights

1. **Prices in Analysis Dict** - Engine looks for prices in `analysis.entry_price`, not `result.entry_price`
2. **Validation Enforces Contract** - `_validate_output()` ensures all strategies follow the contract
3. **Engine is Source of Truth** - If engine behavior changes, validation must change immediately
4. **No Assumptions** - Always verify against actual engine code, not documentation


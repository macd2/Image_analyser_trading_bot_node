# Reproducibility Requirements - PHASE 3

## Overview

Complete reproducibility means: Given the same inputs (chart, config, market data, model version), we can replay the analysis and get identical outputs (recommendation, entry/SL/TP, confidence).

## Data Capture Points

### 1. ANALYSIS PHASE - Input Snapshots

**What to capture:**
- Chart image hash (MD5 of chart file)
- Chart metadata (symbol, timeframe, resolution)
- Model version (GPT-4, GPT-4-Vision, etc.)
- Model parameters (temperature, max_tokens, etc.)
- All input parameters to strategy.analyze()
- Market data snapshot (OHLCV candles, last price, volume, etc.)
- Strategy config snapshot (all settings used)
- Prompt version and content

**Where stored:**
- `recommendations.raw_response` JSON:
  ```json
  {
    "input_snapshot": {
      "chart_hash": "abc123...",
      "chart_metadata": {...},
      "model_version": "gpt-4-vision",
      "model_params": {...},
      "market_data": {...},
      "strategy_config": {...},
      "prompt_version": "1.0",
      "prompt_content": "..."
    }
  }
  ```

### 2. ANALYSIS PHASE - Intermediate Calculations

**What to capture:**
- All intermediate analysis steps
- Confidence component breakdown (trend: 0.8, support: 0.7, etc.)
- Setup quality components (pattern: 0.9, volume: 0.8, etc.)
- Market environment components (volatility: 0.6, trend_strength: 0.7, etc.)
- Raw model response (full text)
- Validation results (price sanity checks, etc.)

**Where stored:**
- `recommendations.raw_response` JSON:
  ```json
  {
    "intermediate_calculations": {
      "confidence_components": {...},
      "setup_quality_components": {...},
      "market_environment_components": {...},
      "raw_model_response": "...",
      "validation_results": {...}
    }
  }
  ```

### 3. RANKING PHASE - Decision Context

**What to capture:**
- All signals analyzed (count)
- Ranking scores for each signal
- Ranking positions (1st, 2nd, 3rd, etc.)
- Available slots at ranking time
- Selection criteria used
- Total signals ranked

**Where stored:**
- `trades.ranking_context` JSON (already implemented):
  ```json
  {
    "ranking_score": 0.85,
    "ranking_position": 1,
    "total_signals_analyzed": 50,
    "total_signals_ranked": 10,
    "available_slots": 5,
    "ranking_weights": {...}
  }
  ```

### 4. EXECUTION PHASE - Execution Context

**What to capture:**
- Wallet balance at execution time
- Kelly fraction used (if Kelly enabled)
- Kelly metrics (win_rate, avg_win, avg_loss, etc.)
- Position sizing inputs (risk_amount, account_size, etc.)
- Position sizing outputs (position_size, quantity, etc.)
- Validation results (all checks passed)
- Order parameters (exact entry, SL, TP sent to exchange)
- Execution timestamp

**Where stored:**
- `trades.wallet_balance_at_trade` REAL
- `trades.kelly_metrics` JSON (already implemented):
  ```json
  {
    "kelly_fraction_used": 0.3,
    "win_rate": 0.65,
    "avg_win_percent": 2.5,
    "avg_loss_percent": -1.5,
    "trade_history_count": 20,
    "kelly_calculation_timestamp": "2025-12-17T10:30:00Z"
  }
  ```

### 5. MONITORING PHASE - Monitoring Context

**What to capture:**
- Original position size at entry
- All adjustments made (SL tightening, TP proximity, etc.)
- Adjustment reasons and calculations
- Monitoring metadata used (entry_price, sl, tp, etc.)
- Exit condition checks (z-score crosses, price touches, etc.)
- Exit trigger details (which condition triggered, at what price)

**Where stored:**
- `position_monitor_logs` table (already created):
  ```sql
  id, trade_id, action_type, original_value, adjusted_value, 
  reason, monitoring_metadata, exit_condition_result, timestamp
  ```

## Reproducibility Flow

```
Chart Image
    ↓
[ANALYSIS PHASE]
├─ Input Snapshot (chart hash, model version, market data, config)
├─ Intermediate Calculations (confidence components, setup quality, etc.)
└─ Store in recommendations.raw_response
    ↓
Recommendation Generated
    ↓
[RANKING PHASE]
├─ Ranking Context (score, position, total analyzed, etc.)
└─ Store in trades.ranking_context
    ↓
Signal Selected for Trading
    ↓
[EXECUTION PHASE]
├─ Execution Context (wallet balance, kelly metrics, position sizing)
└─ Store in trades (wallet_balance_at_trade, kelly_metrics)
    ↓
Trade Executed
    ↓
[MONITORING PHASE]
├─ Monitoring Context (adjustments, exit checks, exit trigger)
└─ Store in position_monitor_logs
    ↓
Trade Closed
```

## Replay Scenario

To replay a trade with identical inputs:

1. **Load input snapshot** from `recommendations.raw_response.input_snapshot`
2. **Load chart image** using chart_hash
3. **Load market data** from `recommendations.raw_response.input_snapshot.market_data`
4. **Load strategy config** from `recommendations.raw_response.input_snapshot.strategy_config`
5. **Call strategy.analyze()** with same inputs
6. **Compare output** with stored recommendation

If all inputs are identical and model version is same, output should be identical.

## Implementation Checklist

- [x] PHASE 1D: Decision context (ranking_context) - DONE
- [x] PHASE 1D: Execution context (wallet_balance_at_trade, kelly_metrics) - DONE
- [x] PHASE 1D: Monitoring context (position_monitor_logs table) - DONE
- [ ] PHASE 3.1: Capture input snapshot in analysis phase
- [ ] PHASE 3.2: Capture intermediate calculations in analysis phase
- [ ] PHASE 3.3: Verify ranking context capture in ranking phase
- [ ] PHASE 3.4: Verify execution context capture in execution phase
- [ ] PHASE 3.5: Verify monitoring context capture in monitoring phase


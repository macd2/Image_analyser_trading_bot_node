# Trading Cycle Contract Specification

## Overview
Defines the contract for the complete trading cycle: recommendation → trade creation → simulator → position monitor.

---

## 1. TRADE CREATION CONTRACT

### Method: `create_trade(recommendation, instance_id, run_id, cycle_id)`

**Purpose:** Create a trade record from a recommendation

**Input Constraints:**
- `recommendation.symbol`: Non-empty string, valid trading pair
- `recommendation.entry_price`: Float > 0
- `recommendation.stop_loss`: Float > 0
- `recommendation.take_profit`: Float > 0
- `recommendation.confidence`: Float 0-1
- `recommendation.strategy_name`: Non-empty string (e.g., "CointegrationSpreadTrader")
- `recommendation.strategy_type`: One of ["price_based", "spread_based", "ml_based"]
- `recommendation.strategy_metadata`: Dict with required fields per strategy type
- `instance_id`: Non-empty UUID string
- `run_id`: Non-empty UUID string
- `cycle_id`: Non-empty UUID string

**Output Constraints:**
- `trade.id`: Non-empty UUID string
- `trade.symbol`: Matches recommendation.symbol
- `trade.entry_price`: Equals recommendation.entry_price
- `trade.stop_loss`: Equals recommendation.stop_loss
- `trade.take_profit`: Equals recommendation.take_profit
- `trade.status`: "pending"
- `trade.created_at`: Current timestamp
- `trade.strategy_name`: Matches recommendation.strategy_name
- `trade.strategy_type`: Matches recommendation.strategy_type
- `trade.strategy_metadata`: Matches recommendation.strategy_metadata
- `trade.instance_id`: Matches input instance_id
- `trade.run_id`: Matches input run_id
- `trade.cycle_id`: Matches input cycle_id

**Invariants:**
- `SL < entry < TP` for long trades
- `SL > entry > TP` for short trades
- `RR_ratio = (TP - entry) / (entry - SL)` for longs
- `RR_ratio = (entry - TP) / (SL - entry)` for shorts
- `RR_ratio > 0`
- Trade not created if duplicate exists for (instance_id, symbol, cycle_id)
- All required strategy_metadata fields present

**Test Cases:**

```yaml
test_case_1:
  name: "Long trade creation"
  inputs:
    recommendation:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      stop_loss: 44000
      take_profit: 46000
      confidence: 0.85
      strategy_name: "CointegrationSpreadTrader"
      strategy_type: "spread_based"
      strategy_metadata:
        beta: 0.85
        spread_mean: 100.5
        spread_std: 25.3
        pair_symbol: "ETH"
        z_exit_threshold: 0.5
    instance_id: "inst_123"
    run_id: "run_456"
    cycle_id: "cycle_789"
  
  expected_output:
    status: "pending"
    symbol: "BTC"
    entry_price: 45000
    stop_loss: 44000
    take_profit: 46000
    strategy_name: "CointegrationSpreadTrader"
    strategy_type: "spread_based"
    instance_id: "inst_123"
    run_id: "run_456"
    cycle_id: "cycle_789"
  
  invariants_to_verify:
    - "SL < entry < TP"
    - "RR_ratio > 0"
    - "strategy_metadata has all required fields"

test_case_2:
  name: "Short trade creation"
  inputs:
    recommendation:
      symbol: "ETH"
      side: "Sell"
      entry_price: 2500
      stop_loss: 2600
      take_profit: 2400
      confidence: 0.75
      strategy_name: "AiImageAnalyzer"
      strategy_type: "price_based"
      strategy_metadata: {}
    instance_id: "inst_123"
    run_id: "run_456"
    cycle_id: "cycle_789"
  
  expected_output:
    status: "pending"
    symbol: "ETH"
    entry_price: 2500
    stop_loss: 2600
    take_profit: 2400
    strategy_type: "price_based"
  
  invariants_to_verify:
    - "SL > entry > TP"
    - "RR_ratio > 0"

test_case_3:
  name: "Duplicate prevention"
  inputs:
    recommendation:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      stop_loss: 44000
      take_profit: 46000
      confidence: 0.85
      strategy_name: "CointegrationSpreadTrader"
      strategy_type: "spread_based"
      strategy_metadata: {}
    instance_id: "inst_123"
    run_id: "run_456"
    cycle_id: "cycle_789"
  
  expected_behavior: "Should reject if trade already exists for (instance_id, symbol, cycle_id)"
  expected_error: "DuplicateTradeError"
```

---

## 2. SIMULATOR CONTRACT

### Method: `simulate_trade(trade, candles, strategy=None)`

**Purpose:** Simulate paper trade through fill and exit

**Input Constraints:**
- `trade.entry_price`: Float > 0
- `trade.stop_loss`: Float > 0
- `trade.take_profit`: Float > 0
- `trade.quantity`: Float > 0
- `trade.side`: "Buy" or "Sell"
- `candles`: List of Candle objects with (timestamp, open, high, low, close)
- `candles`: Sorted by timestamp ascending
- `strategy`: Optional strategy instance with `should_exit()` method

**Output Constraints:**
- `result.status`: "filled" or "closed"
- `result.fill_price`: Float > 0 (if filled)
- `result.fill_candle_index`: Integer >= 0 (if filled)
- `result.exit_price`: Float > 0 (if closed)
- `result.exit_candle_index`: Integer > fill_candle_index (if closed)
- `result.exit_reason`: One of ["tp_hit", "sl_hit", "z_score_exit", "strategy_exit", "max_bars_exceeded"]
- `result.pnl`: Float (can be negative)
- `result.pnl_percent`: Float (can be negative)

**Invariants:**
- If trade fills: `fill_price` within candle range (low ≤ fill_price ≤ high)
- If trade exits: `exit_price` within candle range
- For long: `fill_price ≤ entry_price` (filled at or better than entry)
- For short: `fill_price ≥ entry_price` (filled at or better than entry)
- P&L calculation: `(exit_price - fill_price) * quantity = pnl` for longs
- P&L calculation: `(fill_price - exit_price) * quantity = pnl` for shorts
- `pnl_percent = (pnl / (fill_price * quantity)) * 100`
- If strategy provided and non-price_based: `should_exit()` called for each candle after fill
- If strategy exit triggered: `exit_reason` matches strategy type

**Test Cases:**

```yaml
test_case_1:
  name: "Long trade fills and hits TP"
  inputs:
    trade:
      side: "Buy"
      entry_price: 45000
      stop_loss: 44000
      take_profit: 46000
      quantity: 1.0
    candles:
      - {timestamp: 1000, open: 44500, high: 45500, low: 44000, close: 45000}  # Fill
      - {timestamp: 2000, open: 45000, high: 45200, low: 44900, close: 45100}
      - {timestamp: 3000, open: 45100, high: 46100, low: 45000, close: 46000}  # TP hit
    strategy: null
  
  expected_output:
    status: "closed"
    fill_price: 45000
    fill_candle_index: 0
    exit_price: 46000
    exit_candle_index: 2
    exit_reason: "tp_hit"
    pnl: 1000  # (46000 - 45000) * 1
    pnl_percent: 2.22
  
  invariants_to_verify:
    - "fill_price within candle range"
    - "exit_price within candle range"
    - "P&L calculation correct"
    - "exit_candle_index > fill_candle_index"

test_case_2:
  name: "Short trade fills and hits SL"
  inputs:
    trade:
      side: "Sell"
      entry_price: 2500
      stop_loss: 2600
      take_profit: 2400
      quantity: 1.0
    candles:
      - {timestamp: 1000, open: 2600, high: 2700, low: 2400, close: 2500}  # Fill
      - {timestamp: 2000, open: 2500, high: 2550, low: 2450, close: 2520}
      - {timestamp: 3000, open: 2520, high: 2650, low: 2500, close: 2600}  # SL hit
    strategy: null
  
  expected_output:
    status: "closed"
    fill_price: 2500
    exit_price: 2600
    exit_reason: "sl_hit"
    pnl: -100  # (2500 - 2600) * 1
    pnl_percent: -4.0

test_case_3:
  name: "Strategy exit triggered (cointegration)"
  inputs:
    trade:
      side: "Buy"
      entry_price: 45000
      stop_loss: 44000
      take_profit: 46000
      quantity: 1.0
      strategy_name: "CointegrationSpreadTrader"
      strategy_type: "spread_based"
      strategy_metadata:
        beta: 0.85
        pair_symbol: "ETH"
        z_exit_threshold: 0.5
    candles:
      - {timestamp: 1000, open: 44500, high: 45500, low: 44000, close: 45000}  # Fill
      - {timestamp: 2000, open: 45000, high: 45200, low: 44900, close: 45100}
      - {timestamp: 3000, open: 45100, high: 45300, low: 45000, close: 45200}  # Strategy exit
    strategy: MockCointegrationStrategy
  
  expected_output:
    status: "closed"
    exit_reason: "z_score_exit"
    exit_price: 45200
  
  invariants_to_verify:
    - "should_exit() called for candles after fill"
    - "pair_candle=None passed to strategy"
    - "exit_reason matches strategy type"

test_case_4:
  name: "Trade never fills"
  inputs:
    trade:
      side: "Buy"
      entry_price: 45000
      stop_loss: 44000
      take_profit: 46000
      quantity: 1.0
    candles:
      - {timestamp: 1000, open: 44000, high: 44500, low: 43500, close: 44200}
      - {timestamp: 2000, open: 44200, high: 44800, low: 44000, close: 44500}
    strategy: null
  
  expected_output: null  # No result if never filled
```

---

## 3. POSITION MONITOR CONTRACT

### Method: `check_all_tightening(position, state, strategy=None, current_candle=None)`

**Purpose:** Check if position should be tightened or exited

**Input Constraints:**
- `position.symbol`: Non-empty string
- `position.side`: "Buy" or "Sell"
- `position.entry_price`: Float > 0
- `position.mark_price`: Float > 0
- `position.stop_loss`: Float > 0
- `position.take_profit`: Float > 0
- `state.rr_ratio`: Float > 0
- `current_candle`: Dict with {timestamp, open, high, low, close} or None
- `strategy`: Optional strategy instance or None

**Output Constraints:**
- `result.action`: One of ["none", "tighten_sl", "close_position"]
- `result.new_stop_loss`: Float > 0 (if tightening)
- `result.reason`: String describing why action taken
- `result.exit_price`: Float > 0 (if closing)

**Invariants:**
- If strategy exit triggered: position closed immediately (highest priority)
- If TP proximity: SL tightened to breakeven or better
- If RR tightening: SL adjusted based on RR ratio
- New SL never worse than current SL
- For long: new_sl > current_sl (tightening upward)
- For short: new_sl < current_sl (tightening downward)
- If strategy provided: `should_exit()` called before other tightening
- If strategy exit: other tightening skipped

**Test Cases:**

```yaml
test_case_1:
  name: "Strategy exit triggered (highest priority)"
  inputs:
    position:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      mark_price: 45200
      stop_loss: 44000
      take_profit: 46000
    state:
      rr_ratio: 2.0
    strategy: MockCointegrationStrategy
    current_candle: {timestamp: 1000, open: 45200, high: 45300, low: 45100, close: 45200}
  
  strategy_should_exit_returns:
    should_exit: true
    exit_reason: "z_score_exit"
  
  expected_output:
    action: "close_position"
    reason: "Strategy exit: z_score_exit"
    exit_price: 45200
  
  invariants_to_verify:
    - "Strategy exit checked first"
    - "Other tightening skipped"
    - "Position closed immediately"

test_case_2:
  name: "TP proximity tightening"
  inputs:
    position:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      mark_price: 45900  # 90% to TP
      stop_loss: 44000
      take_profit: 46000
    state:
      rr_ratio: 2.0
  
  expected_output:
    action: "tighten_sl"
    new_stop_loss: 45000  # Tighten to breakeven
    reason: "TP proximity: 90% to target"
  
  invariants_to_verify:
    - "new_sl > current_sl"
    - "new_sl never worse than current"

test_case_3:
  name: "RR-based tightening"
  inputs:
    position:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      mark_price: 45500  # 50% profit
      stop_loss: 44000
      take_profit: 46000
    state:
      rr_ratio: 2.0
  
  expected_output:
    action: "tighten_sl"
    new_stop_loss: 45000  # Move to breakeven
    reason: "RR tightening: 50% profit achieved"
  
  invariants_to_verify:
    - "new_sl >= entry_price"
    - "Locks in profit"

test_case_4:
  name: "No tightening needed"
  inputs:
    position:
      symbol: "BTC"
      side: "Buy"
      entry_price: 45000
      mark_price: 45100  # Only 10% profit
      stop_loss: 44000
      take_profit: 46000
    state:
      rr_ratio: 2.0
  
  expected_output:
    action: "none"
    reason: "No tightening conditions met"
```

---

## 4. CROSS-COMPONENT INVARIANTS

These invariants must hold across the entire trading cycle:

```yaml
invariants:
  - "Every trade has strategy_name and strategy_type"
  - "strategy_type matches strategy_name (e.g., CointegrationSpreadTrader → spread_based)"
  - "All strategy_metadata required fields present for strategy type"
  - "Trade created within cycle boundary"
  - "No duplicate trades for (instance_id, symbol, cycle_id)"
  - "Simulator fills before exit"
  - "Position monitor only tracks filled trades"
  - "Strategy exit checked before other tightening"
  - "Exit reason matches strategy type or SL/TP logic"
  - "P&L calculation consistent across simulator and position monitor"
  - "Timestamps follow order: created_at → submitted_at → filled_at → closed_at"
```


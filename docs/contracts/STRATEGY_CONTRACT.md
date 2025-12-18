# Strategy Contract Specification

## Overview

Strategies analyze market data and generate trading recommendations. All strategies must return the same output format for downstream compatibility.

---

## Contract 1: Prompt Strategy (AiImageAnalyzer)

### Method
```python
run_analysis_cycle(
    symbols: List[str],
    timeframe: str,
    cycle_id: str,
) -> List[Dict[str, Any]]
```

### Input Constraints
- `symbols`: List of trading symbols (e.g., ["BTC", "ETH"])
- `timeframe`: Valid timeframe (e.g., "1h", "4h", "1d")
- `cycle_id`: Unique cycle identifier (UUID)

### Output Constraints (Per Recommendation)
- `symbol`: Normalized symbol (e.g., "BTCUSDT")
- `recommendation` ∈ ["BUY", "SELL", "HOLD"]
- `confidence` ∈ [0, 1]
- `entry_price`: float > 0
- `stop_loss`: float > 0
- `take_profit`: float > 0
- `risk_reward`: float > 0
- `setup_quality`: float ∈ [0, 1]
- `market_environment`: float ∈ [0, 1]
- `strategy_uuid`: UUID string
- `strategy_type`: "price_based"
- `strategy_name`: "AiImageAnalyzer"
- `strategy_metadata`: {} (empty dict for price-based)

### Invariants
1. **SL/TP Logic**: For BUY: SL < entry < TP; For SELL: SL > entry > TP
2. **Risk Reward**: `risk_reward = (TP - entry) / (entry - SL)` for long
3. **Confidence Range**: confidence ∈ [0, 1]
4. **Metadata Empty**: strategy_metadata = {} (no strategy-specific data)
5. **Strategy UUID**: Same UUID for all recommendations in cycle
6. **Output Format**: Same format as cointegration strategy

### Test Cases

#### Known Input Tests
1. **Single Symbol Analysis**: ["BTC"], "1h", cycle_id
   - Expected: 1 recommendation with BUY/SELL/HOLD

2. **Multiple Symbols**: ["BTC", "ETH"], "1h", cycle_id
   - Expected: 2 recommendations, both with same strategy_uuid

3. **Long Trade**: BUY recommendation
   - Expected: SL < entry < TP, risk_reward > 0

4. **Short Trade**: SELL recommendation
   - Expected: SL > entry > TP, risk_reward > 0

#### Property-Based Tests
- For any symbol list, all recommendations have same strategy_uuid
- For any BUY recommendation, SL < entry < TP
- For any SELL recommendation, SL > entry > TP
- For any recommendation, confidence ∈ [0, 1]

---

## Contract 2: Cointegration Strategy

### Method
```python
run_analysis_cycle(
    symbols: List[str],
    timeframe: str,
    cycle_id: str,
) -> List[Dict[str, Any]]
```

### Input Constraints
- Same as Prompt Strategy
- Symbols must have configured pairs in strategy config

### Output Constraints (Per Recommendation)
- All fields from Prompt Strategy PLUS:
- `strategy_metadata`: Dict with:
  - `beta`: float (regression coefficient)
  - `spread_mean`: float (mean of spread)
  - `spread_std`: float (std dev of spread)
  - `z_score_at_entry`: float (z-score at entry)
  - `pair_symbol`: str (paired symbol)
  - `z_exit_threshold`: float (exit threshold)

### Invariants
1. All Prompt Strategy invariants apply
2. **Metadata Required**: strategy_metadata must have all 6 fields
3. **Z-Score Range**: z_score_at_entry typically ∈ [-3, 3]
4. **Beta Positive**: beta > 0 (cointegrated pairs)
5. **Spread Stats**: spread_std > 0
6. **Pair Symbol**: pair_symbol is valid trading symbol

### Test Cases

#### Known Input Tests
1. **Cointegration Analysis**: ["BTC"], "1h", cycle_id
   - Expected: recommendation with all metadata fields

2. **Metadata Validation**: Check all 6 metadata fields present
   - Expected: beta, spread_mean, spread_std, z_score_at_entry, pair_symbol, z_exit_threshold

3. **Z-Score Entry**: z_score_at_entry at extreme (e.g., -2.5)
   - Expected: Valid recommendation with z_score_at_entry = -2.5

#### Property-Based Tests
- For any cointegration recommendation, all 6 metadata fields present
- For any metadata, beta > 0
- For any metadata, spread_std > 0
- For any z_score_at_entry, value ∈ [-5, 5]

---

## Contract 3: Strategy Exit Logic

### Method
```python
should_exit(
    trade: Dict[str, Any],
    current_candle: Dict[str, Any],
    pair_candle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]
```

### Input Constraints
- `trade`: Trade record with entry_price, stop_loss, take_profit
- `current_candle`: {timestamp, open, high, low, close}
- `pair_candle`: Optional, for cointegration strategy

### Output Constraints
- `should_exit`: bool
- `exit_reason`: str ∈ ["tp_hit", "sl_hit", "strategy_exit", "no_exit"]
- `exit_price`: float (if should_exit=True)
- `exit_details`: dict with reason details

### Invariants (Prompt Strategy)
1. **Price-Based Exit**: Exit when price touches TP or SL
2. **TP Hit**: For long: close >= TP; For short: close <= TP
3. **SL Hit**: For long: close <= SL; For short: close >= SL
4. **No Exit**: If price between SL and TP

### Invariants (Cointegration Strategy)
1. **Z-Score Exit**: Exit when z-score crosses threshold
2. **Strategy Priority**: Strategy exit checked before price levels
3. **Pair Data**: Uses pair_candle for z-score calculation

### Test Cases

#### Known Input Tests (Prompt)
1. **TP Hit - Long**: entry=50000, TP=51000, close=51000
   - Expected: should_exit=True, exit_reason="tp_hit"

2. **SL Hit - Long**: entry=50000, SL=49000, close=49000
   - Expected: should_exit=True, exit_reason="sl_hit"

3. **No Exit**: entry=50000, SL=49000, TP=51000, close=50500
   - Expected: should_exit=False, exit_reason="no_exit"

#### Known Input Tests (Cointegration)
1. **Z-Score Exit**: z_score=0.8, threshold=0.5
   - Expected: should_exit=True, exit_reason="strategy_exit"

2. **No Z-Score Exit**: z_score=0.3, threshold=0.5
   - Expected: should_exit=False, exit_reason="no_exit"



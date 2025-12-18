# Position Sizer Contract Specification

## Overview

The Position Sizer calculates optimal position size based on risk parameters, confidence weighting, and Kelly Criterion.

---

## Contract 1: Basic Position Sizing (Fixed Risk)

### Method
```python
calculate_position_size(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    wallet_balance: float,
    confidence: float = 0.75,
    leverage: int = 1,
    trade_history: Optional[List] = None,
    strategy: Optional[Any] = None,
) -> Dict[str, Any]
```

### Input Constraints
- `entry_price` > 0
- `stop_loss` > 0 and `stop_loss` ≠ `entry_price`
- `wallet_balance` > 0
- `confidence` ∈ [0, 1]
- `risk_percentage` ∈ (0, 0.5] (default: 0.01 = 1%)
- `min_position_value` ≥ 0 (default: 50 USD)

### Output Constraints
- `position_size` > 0
- `position_value` ≥ `min_position_value`
- `risk_amount` > 0
- `risk_percentage` ≤ `risk_percentage` setting
- `confidence_weight` ∈ [0.5, 1.5] (with confidence weighting)
- `sizing_method` ∈ ["fixed", "kelly"]

### Invariants
1. **Risk Calculation**: `risk_amount = position_size * abs(entry_price - stop_loss)`
2. **Position Value**: `position_value = position_size * entry_price`
3. **Risk Percentage**: `risk_percentage = risk_amount / wallet_balance`
4. **Minimum Enforcement**: `position_value ≥ min_position_value`
5. **Confidence Weighting**: If enabled, `confidence_weight` adjusts risk based on confidence score
6. **Max Loss Cap**: If `max_loss_usd > 0`, then `risk_amount ≤ max_loss_usd`

### Test Cases

#### Known Input Tests
1. **Basic Long Trade**: Entry=50000, SL=49000, Balance=10000, Risk=1%
   - Expected: position_size ≈ 0.2, risk_amount ≈ 100, position_value ≈ 10000

2. **Short Trade**: Entry=50000, SL=51000, Balance=10000, Risk=1%
   - Expected: position_size ≈ 0.2, risk_amount ≈ 100, position_value ≈ 10000

3. **Min Position Value Enforcement**: Entry=50000, SL=49000, Balance=10000, MinValue=500
   - Expected: position_value ≥ 500

4. **Max Loss Cap**: Entry=50000, SL=49000, Balance=10000, MaxLoss=50
   - Expected: risk_amount ≤ 50

5. **Confidence Weighting - Low**: Confidence=0.6, LowThreshold=0.7, LowWeight=0.8
   - Expected: confidence_weight = 0.8, risk_amount reduced

6. **Confidence Weighting - High**: Confidence=0.9, HighThreshold=0.85, HighWeight=1.2
   - Expected: confidence_weight = 1.2, risk_amount increased

#### Property-Based Tests
- For any valid (entry, sl, balance, risk%), invariants hold
- For any confidence ∈ [0, 1], confidence_weight is calculated correctly
- For any min_position_value, position_value ≥ min_position_value
- For any max_loss_usd > 0, risk_amount ≤ max_loss_usd

---

## Contract 2: Kelly Criterion Position Sizing

### Input Constraints
- `use_kelly_criterion` = True
- `trade_history` is list of closed trades with `pnl_percent` field
- `kelly_fraction` ∈ (0, 1] (default: 0.3)
- `kelly_window` > 0 (default: 30)

### Output Constraints
- `sizing_method` = "kelly"
- `kelly_metrics` dict with:
  - `kelly_fraction_used`: float
  - `win_rate`: float ∈ [0, 1]
  - `avg_win_percent`: float > 0
  - `avg_loss_percent`: float > 0
  - `trade_history_count`: int

### Invariants
1. **Fallback to Fixed**: If trade_history < 10 trades, use fixed risk_percentage
2. **Kelly Formula**: `f* = (b*p - q) / b` where p=win_rate, q=1-p, b=avg_win/avg_loss
3. **Safety Clipping**: `f* ∈ [0, 0.5]` (never risk more than 50%)
4. **Fractional Kelly**: `kelly_risk = kelly_fraction * f*`
5. **Window Limit**: Only use last `kelly_window` trades

### Test Cases

#### Known Input Tests
1. **Insufficient History**: < 10 trades
   - Expected: sizing_method = "fixed", use risk_percentage

2. **Perfect Win Rate**: 10 wins, 0 losses
   - Expected: Fallback to fixed (no losses to calculate ratio)

3. **50% Win Rate**: 5 wins (2% each), 5 losses (1% each)
   - Expected: kelly_risk calculated, sizing_method = "kelly"

4. **Window Limit**: 50 trades, kelly_window=30
   - Expected: Only last 30 trades used

#### Property-Based Tests
- For any trade_history with wins/losses, kelly_risk ∈ [0, 0.5]
- For any kelly_fraction, kelly_risk = kelly_fraction * f*
- For any kelly_window, only last N trades used



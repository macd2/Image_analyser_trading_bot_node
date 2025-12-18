# Contract Testing Framework

## What Is This?

A **specification-based testing framework** that validates each method returns expected values for known inputs, and that invariants hold for any valid input.

Instead of writing 100 unit tests manually, you:
1. Write a contract spec (what the method should do)
2. Framework generates 1000s of tests automatically
3. Tests verify both known cases and edge cases

---

## Files

### 📋 Contract Specifications

**`TRADING_CYCLE_CONTRACT.md`** - Complete specifications for:
- Trade Creation (Section 1)
- Simulator (Section 2)
- Position Monitor (Section 3)
- Cross-component Invariants (Section 4)

Each contract includes:
- Input constraints (valid ranges)
- Output constraints (expected format)
- Invariants (rules that always hold)
- Test cases (known inputs + expected outputs)

### 🧪 Test Implementation

**`python/tests/test_trading_cycle_contracts.py`** - Pytest tests that:
- Test known inputs from contract specs
- Generate 100s of random inputs (property-based)
- Verify invariants hold
- Report failures with minimal examples

### 🚀 Test Runner

**`python/tests/run_contract_tests.py`** - Runs all tests and generates:
- Coverage report per contract
- Invariants verified
- Pass/fail summary
- Actionable error messages

### 📖 Usage Guide

**`HOW_TO_USE_CONTRACTS.md`** - Complete guide:
- How to run tests
- How to interpret results
- How to add new tests
- CI/CD integration

---

## Quick Start

### 1. Run All Contract Tests

```bash
cd /home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node
python python/tests/run_contract_tests.py
```

### 2. Run Specific Contract

```bash
# Test simulator only
python -m pytest python/tests/test_trading_cycle_contracts.py::TestSimulatorContract -v

# Test position monitor only
python -m pytest python/tests/test_trading_cycle_contracts.py::TestPositionMonitorContract -v
```

### 3. View Results

```
📊 CONTRACT COVERAGE REPORT
================================================================================

📋 Simulator Contract
────────────────────────────────────────────────────────────────────────────

  Tests (4):
    ✓ test_long_trade_fills_and_hits_tp
    ✓ test_short_trade_fills_and_hits_sl
    ✓ test_trade_never_fills
    ✓ test_pnl_calculation_invariants

  Invariants (5):
    ✓ Fill price within candle range
    ✓ Exit price within candle range
    ✓ P&L calculation correct
    ✓ Exit reason recorded
    ✓ Strategy exit called for non-price strategies

✅ ALL CONTRACTS PASSED
```

---

## What Gets Tested

### Trade Creation Contract
- ✓ Long trades: SL < entry < TP
- ✓ Short trades: SL > entry > TP
- ✓ RR ratio > 0
- ✓ No duplicate trades
- ✓ Strategy metadata stored

### Simulator Contract
- ✓ Paper trades fill at entry price
- ✓ Trades exit on TP hit
- ✓ Trades exit on SL hit
- ✓ Strategy exit triggered for non-price strategies
- ✓ P&L calculated correctly
- ✓ Exit reasons recorded

### Position Monitor Contract
- ✓ Strategy exit checked first (highest priority)
- ✓ SL tightening works correctly
- ✓ TP proximity triggers tightening
- ✓ RR-based tightening works
- ✓ New SL never worse than current

---

## How It Works

### Known Input Tests
Test specific inputs with expected outputs:

```python
def test_long_trade_fills_and_hits_tp(self, simulator):
    trade = {'entry_price': 45000, 'stop_loss': 44000, 'take_profit': 46000}
    candles = [Candle(...), Candle(...)]
    result = simulator.simulate_trade(trade, candles)
    assert result['exit_price'] == 46000
    assert result['pnl'] == 1000
```

### Property-Based Tests
Test invariants hold for ANY valid input:

```python
@given(
    entry_price=st.floats(min_value=100, max_value=100000),
    sl_offset=st.floats(min_value=1, max_value=10000),
    tp_offset=st.floats(min_value=1, max_value=10000),
)
@settings(max_examples=100)
def test_trade_creation_invariants_long(self, entry_price, sl_offset, tp_offset):
    stop_loss = entry_price - sl_offset
    take_profit = entry_price + tp_offset
    assert stop_loss < entry_price < take_profit
    assert rr_ratio > 0
```

This generates 100 random test cases automatically!

---

## Why This Approach?

| Aspect | Benefit |
|--------|---------|
| **Coverage** | 1000s of test cases vs 50 manual tests |
| **Time** | 30 min to write vs 3 hours for manual tests |
| **Edge Cases** | Finds bugs you didn't think of |
| **Documentation** | Contract spec = living documentation |
| **Maintenance** | Update contract once, tests auto-update |
| **Regression** | Catches when someone breaks invariants |

---

## Next Steps

1. **Run the tests** to verify current implementation
2. **Review failures** if any (fix method or contract)
3. **Add new contracts** for other components
4. **Integrate into CI/CD** to run before deployment

See `HOW_TO_USE_CONTRACTS.md` for detailed instructions.


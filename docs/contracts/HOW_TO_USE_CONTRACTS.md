# How to Use Contract Specifications

## Quick Start

### 1. Run Contract Tests

```bash
cd /home/slicks/projects/^^Python/Analyse_Chart_Screenshot_Node

# Run all contract tests
python python/tests/run_contract_tests.py

# Or run specific contract
python -m pytest python/tests/test_trading_cycle_contracts.py::TestSimulatorContract -v
```

### 2. Understand the Output

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

## What Each Contract Tests

### 1. Trade Creation Contract
**File:** `docs/contracts/TRADING_CYCLE_CONTRACT.md` (Section 1)

**Tests that:**
- ✓ Trades created with correct symbol, prices, strategy
- ✓ SL/TP logic correct for longs and shorts
- ✓ RR ratio calculated correctly
- ✓ Duplicate trades prevented
- ✓ Strategy metadata stored

**Run:**
```bash
python -m pytest python/tests/test_trading_cycle_contracts.py::TestTradeCreationContract -v
```

### 2. Simulator Contract
**File:** `docs/contracts/TRADING_CYCLE_CONTRACT.md` (Section 2)

**Tests that:**
- ✓ Paper trades fill at entry price
- ✓ Trades exit on TP hit
- ✓ Trades exit on SL hit
- ✓ Strategy exit triggered for non-price strategies
- ✓ P&L calculated correctly
- ✓ Exit reasons recorded

**Run:**
```bash
python -m pytest python/tests/test_trading_cycle_contracts.py::TestSimulatorContract -v
```

### 3. Position Monitor Contract
**File:** `docs/contracts/TRADING_CYCLE_CONTRACT.md` (Section 3)

**Tests that:**
- ✓ Strategy exit checked first (highest priority)
- ✓ SL tightening works correctly
- ✓ TP proximity triggers tightening
- ✓ RR-based tightening works
- ✓ New SL never worse than current

**Run:**
```bash
python -m pytest python/tests/test_trading_cycle_contracts.py::TestPositionMonitorContract -v
```

---

## How Contracts Work

### Known Input Tests
Test specific inputs with expected outputs:

```python
def test_long_trade_fills_and_hits_tp(self, simulator):
    """Test case 1: Long trade fills and hits TP"""
    trade = {
        'entry_price': 45000,
        'stop_loss': 44000,
        'take_profit': 46000,
        'quantity': 1.0,
    }
    
    candles = [
        Candle(timestamp=1000, open=44500, high=45500, low=44000, close=45000),  # Fill
        Candle(timestamp=3000, open=45100, high=46100, low=45000, close=46000),  # TP hit
    ]
    
    result = simulator.simulate_trade(trade, candles)
    
    # Verify exact output
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
    """Property test: SL/TP invariants hold for any long trade"""
    stop_loss = entry_price - sl_offset
    take_profit = entry_price + tp_offset
    
    # Verify invariants
    assert stop_loss < entry_price < take_profit
    assert rr_ratio > 0
```

This generates 100 random test cases automatically!

---

## Adding New Tests

### 1. Add Test Case to Contract Spec

Edit `docs/contracts/TRADING_CYCLE_CONTRACT.md`:

```yaml
test_case_5:
  name: "My new test case"
  inputs:
    # Define inputs
  expected_output:
    # Define expected output
  invariants_to_verify:
    # List invariants to check
```

### 2. Implement Test in Python

Edit `python/tests/test_trading_cycle_contracts.py`:

```python
def test_my_new_case(self, simulator):
    """Test case 5: My new test case"""
    # Implement test based on contract spec
    pass
```

### 3. Run Tests

```bash
python python/tests/run_contract_tests.py
```

---

## Interpreting Failures

### If a Known Input Test Fails

```
FAILED test_long_trade_fills_and_hits_tp
AssertionError: assert 45999 == 46000
```

**What it means:** The method returned 45999 instead of 46000
**What to do:** 
1. Check if the method implementation changed
2. Verify the contract spec is correct
3. Fix the method or update the contract

### If a Property Test Fails

```
Falsifying example: test_pnl_calculation_invariants(
    entry_price=45000.5,
    fill_price_offset=-100.2,
    exit_price_offset=200.1,
    quantity=0.5
)
AssertionError: assert 50.05 == 50.049999999
```

**What it means:** Found an edge case where invariant fails
**What to do:**
1. The minimal failing case is shown
2. Debug with this exact input
3. Fix the method or adjust the invariant

---

## CI/CD Integration

### Run Before Deployment

```bash
#!/bin/bash
# scripts/validate-contracts.sh

echo "Running contract tests..."
python python/tests/run_contract_tests.py

if [ $? -ne 0 ]; then
    echo "❌ Contract tests failed - deployment blocked"
    exit 1
fi

echo "✅ All contracts passed - safe to deploy"
```

### Add to GitHub Actions

```yaml
# .github/workflows/test.yml
- name: Run Contract Tests
  run: python python/tests/run_contract_tests.py
```

---

## Best Practices

1. **Keep Contracts Updated**
   - When you change a method, update the contract spec
   - Contract spec = living documentation

2. **Test Both Paths**
   - Known inputs: verify exact behavior
   - Property tests: verify invariants always hold

3. **Use Meaningful Names**
   - `test_long_trade_fills_and_hits_tp` ✓
   - `test_trade_1` ✗

4. **Document Invariants**
   - Why does this invariant matter?
   - What breaks if it's violated?

5. **Run Regularly**
   - Before committing
   - Before deploying
   - In CI/CD pipeline

---

## Contract Spec Structure

Every contract has:

```
1. Method Name & Purpose
2. Input Constraints (valid ranges)
3. Output Constraints (expected format)
4. Invariants (rules that always hold)
5. Test Cases (known inputs + expected outputs)
```

This structure ensures:
- ✓ Clear expectations
- ✓ Comprehensive testing
- ✓ Easy to maintain
- ✓ Living documentation


# Contract Testing - Quick Reference

## Files Created

```
docs/contracts/
├── README.md                          # Overview & quick start
├── TRADING_CYCLE_CONTRACT.md          # Contract specifications
├── HOW_TO_USE_CONTRACTS.md            # Detailed usage guide
├── IMPLEMENTATION_SUMMARY.md          # What was created
└── QUICK_REFERENCE.md                 # This file

python/tests/
├── test_trading_cycle_contracts.py    # Test implementation
└── run_contract_tests.py              # Test runner
```

---

## Run Tests

### All Tests
```bash
python python/tests/run_contract_tests.py
```

### Specific Contract
```bash
# Trade Creation
python -m pytest python/tests/test_trading_cycle_contracts.py::TestTradeCreationContract -v

# Simulator
python -m pytest python/tests/test_trading_cycle_contracts.py::TestSimulatorContract -v

# Position Monitor
python -m pytest python/tests/test_trading_cycle_contracts.py::TestPositionMonitorContract -v
```

### Specific Test
```bash
python -m pytest python/tests/test_trading_cycle_contracts.py::TestSimulatorContract::test_long_trade_fills_and_hits_tp -v
```

---

## Contract Structure

Each contract has:

```yaml
Method: simulate_trade(trade, candles, strategy=None)

Input Constraints:
  - trade.entry_price: Float > 0
  - trade.stop_loss: Float > 0
  - candles: List sorted by timestamp

Output Constraints:
  - result.status: "filled" or "closed"
  - result.exit_price: Float > 0
  - result.pnl: Float (can be negative)

Invariants:
  - Fill price within candle range
  - Exit price within candle range
  - P&L calculation correct

Test Cases:
  - test_case_1: Long trade fills and hits TP
  - test_case_2: Short trade fills and hits SL
  - test_case_3: Trade never fills
```

---

## Test Types

### Known Input Tests
Test specific inputs with expected outputs:

```python
def test_long_trade_fills_and_hits_tp(self, simulator):
    trade = {'entry_price': 45000, 'stop_loss': 44000, 'take_profit': 46000}
    candles = [Candle(...), Candle(...)]
    result = simulator.simulate_trade(trade, candles)
    assert result['exit_price'] == 46000
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
```

---

## What Gets Tested

### Trade Creation
- ✓ Long: SL < entry < TP
- ✓ Short: SL > entry > TP
- ✓ RR ratio > 0
- ✓ No duplicates
- ✓ Strategy metadata stored

### Simulator
- ✓ Fills at entry price
- ✓ Exits on TP hit
- ✓ Exits on SL hit
- ✓ Strategy exit triggered
- ✓ P&L calculated correctly

### Position Monitor
- ✓ Strategy exit checked first
- ✓ SL tightening works
- ✓ TP proximity triggers tightening
- ✓ RR-based tightening works
- ✓ New SL never worse than current

---

## Interpreting Results

### ✅ All Pass
```
✅ ALL CONTRACTS PASSED
The trading cycle, simulator, and position monitor work as expected.
All invariants verified for known inputs and property-based tests.
```

### ❌ Known Input Test Fails
```
FAILED test_long_trade_fills_and_hits_tp
AssertionError: assert 45999 == 46000
```
→ Method returned wrong value. Fix method or update contract.

### ❌ Property Test Fails
```
Falsifying example: test_pnl_calculation_invariants(
    entry_price=45000.5,
    fill_price_offset=-100.2,
    exit_price_offset=200.1,
    quantity=0.5
)
AssertionError: assert 50.05 == 50.049999999
```
→ Found edge case where invariant fails. Debug with this exact input.

---

## Adding New Tests

### 1. Add to Contract Spec
Edit `docs/contracts/TRADING_CYCLE_CONTRACT.md`:

```yaml
test_case_5:
  name: "My new test case"
  inputs:
    # Define inputs
  expected_output:
    # Define expected output
  invariants_to_verify:
    # List invariants
```

### 2. Implement in Python
Edit `python/tests/test_trading_cycle_contracts.py`:

```python
def test_my_new_case(self, simulator):
    """Test case 5: My new test case"""
    # Implement based on contract spec
    pass
```

### 3. Run Tests
```bash
python python/tests/run_contract_tests.py
```

---

## CI/CD Integration

### GitHub Actions
```yaml
# .github/workflows/test.yml
- name: Run Contract Tests
  run: python python/tests/run_contract_tests.py
```

### Pre-Commit Hook
```bash
#!/bin/bash
# .git/hooks/pre-commit
python python/tests/run_contract_tests.py
if [ $? -ne 0 ]; then
    echo "❌ Contract tests failed"
    exit 1
fi
```

---

## Key Concepts

| Term | Meaning |
|------|---------|
| **Contract** | Specification of what a method should do |
| **Input Constraints** | Valid ranges for inputs |
| **Output Constraints** | Expected format of outputs |
| **Invariant** | Rule that always holds |
| **Known Input Test** | Test specific inputs with expected outputs |
| **Property-Based Test** | Test invariants hold for random valid inputs |
| **Hypothesis** | Python library for property-based testing |

---

## Resources

- **Overview:** `docs/contracts/README.md`
- **Detailed Guide:** `docs/contracts/HOW_TO_USE_CONTRACTS.md`
- **Implementation:** `docs/contracts/IMPLEMENTATION_SUMMARY.md`
- **Contracts:** `docs/contracts/TRADING_CYCLE_CONTRACT.md`
- **Tests:** `python/tests/test_trading_cycle_contracts.py`
- **Runner:** `python/tests/run_contract_tests.py`


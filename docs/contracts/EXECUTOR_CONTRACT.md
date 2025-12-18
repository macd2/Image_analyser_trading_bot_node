# Order Executor Contract Specification

## Overview

The Order Executor handles order placement, validation, and error handling with Bybit API.

---

## Contract 1: Limit Order Placement

### Method
```python
place_limit_order(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None,
    order_link_id: Optional[str] = None,
    time_in_force: str = "GTC",
) -> Dict[str, Any]
```

### Input Constraints
- `symbol`: Valid trading symbol (e.g., "BTCUSDT")
- `side` ∈ ["Buy", "Sell"]
- `qty` > 0
- `price` > 0
- `take_profit` > 0 (if provided)
- `stop_loss` > 0 (if provided)
- `time_in_force` ∈ ["GTC", "IOC", "FOK"]

### Output Constraints (Success)
- `order_id`: Non-empty string
- `order_link_id`: Non-empty string
- `symbol`: Normalized symbol
- `side`: "Buy" or "Sell"
- `qty`: float > 0
- `price`: float > 0
- `status`: "submitted"
- No `error` field

### Output Constraints (Error)
- `error`: Non-empty error message
- `retCode`: Non-zero integer (if from API)
- No `order_id` field

### Invariants
1. **Symbol Normalization**: Symbol is normalized for Bybit (e.g., "BTC" → "BTCUSDT")
2. **Order Link ID**: Generated if not provided (UUID-based)
3. **TP/SL Validation**: If provided, TP and SL are included in request
4. **Error Handling**: All exceptions caught and returned as error dict
5. **Session Check**: Returns error if session not initialized

### Test Cases

#### Known Input Tests
1. **Basic Limit Order**: BTC, Buy, 0.1, 50000
   - Expected: order_id present, status="submitted"

2. **With Take Profit**: BTC, Buy, 0.1, 50000, TP=51000
   - Expected: order_id present, TP included

3. **With Stop Loss**: BTC, Buy, 0.1, 50000, SL=49000
   - Expected: order_id present, SL included

4. **With Both TP and SL**: BTC, Buy, 0.1, 50000, TP=51000, SL=49000
   - Expected: order_id present, both TP and SL included

5. **Invalid Symbol**: "INVALID", Buy, 0.1, 50000
   - Expected: error returned

6. **Invalid Side**: "INVALID", "INVALID", 0.1, 50000
   - Expected: error returned

#### Property-Based Tests
- For any valid (symbol, side, qty, price), order succeeds or returns error
- For any TP/SL provided, they are included in request
- For any exception, error dict is returned (never raises)

---

## Contract 2: Market Order Placement

### Method
```python
place_market_order(
    symbol: str,
    side: str,
    qty: float,
    take_profit: Optional[float] = None,
    stop_loss: Optional[float] = None,
    order_link_id: Optional[str] = None,
) -> Dict[str, Any]
```

### Input Constraints
- Same as limit order (except no `price` parameter)

### Output Constraints
- Same as limit order (no `price` in response)

### Invariants
- Same as limit order (except no price validation)

---

## Contract 3: Order Cancellation

### Method
```python
cancel_order(
    symbol: str,
    order_id: Optional[str] = None,
    order_link_id: Optional[str] = None,
) -> Dict[str, Any]
```

### Input Constraints
- `symbol`: Valid trading symbol
- Either `order_id` OR `order_link_id` must be provided

### Output Constraints (Success)
- `order_id`: Non-empty string
- `status`: "cancelled"
- No `error` field

### Output Constraints (Error)
- `error`: Non-empty error message
- No `order_id` field

### Invariants
1. **ID Requirement**: At least one of order_id or order_link_id required
2. **Error if Missing**: Returns error if neither provided
3. **Symbol Normalization**: Symbol normalized for Bybit

### Test Cases

#### Known Input Tests
1. **Cancel by Order ID**: symbol="BTC", order_id="123456"
   - Expected: status="cancelled" or error

2. **Cancel by Link ID**: symbol="BTC", order_link_id="abc123"
   - Expected: status="cancelled" or error

3. **Missing Both IDs**: symbol="BTC"
   - Expected: error="Either order_id or order_link_id required"

#### Property-Based Tests
- For any valid symbol and ID, cancellation succeeds or returns error
- For missing IDs, error is returned



#!/usr/bin/env python3
"""
Test closing validation - validates trades and candles for closing logic.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from python.tests.validate_closing_trades import validate_trade_for_closing, validate_candles_for_closing


def test_valid_trade():
    """Test that a valid trade passes validation."""
    trade = {
        "id": "trade_1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "status": "filled",
        "created_at": "2024-01-01T00:00:00Z",
        "entry_price": 50000,
        "stop_loss": 49000,
        "take_profit": 52000,
        "pnl": None,
        "strategy_type": "price_based"
    }
    is_valid, error, context = validate_trade_for_closing(trade)
    assert is_valid, f"Valid trade should pass: {error}"
    print("✅ test_valid_trade PASSED")


def test_missing_trade_id():
    """Test that missing trade id is caught."""
    trade = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "status": "filled",
        "created_at": "2024-01-01T00:00:00Z",
        "entry_price": 50000,
        "stop_loss": 49000,
        "take_profit": 52000
    }
    is_valid, error, context = validate_trade_for_closing(trade)
    assert not is_valid, "Should reject missing id"
    assert "id" in error.lower()
    print("✅ test_missing_trade_id PASSED")


def test_already_closed_trade():
    """Test that already closed trades are rejected."""
    trade = {
        "id": "trade_1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "status": "filled",
        "created_at": "2024-01-01T00:00:00Z",
        "entry_price": 50000,
        "stop_loss": 49000,
        "take_profit": 52000,
        "pnl": 100.50  # Already has PnL
    }
    is_valid, error, context = validate_trade_for_closing(trade)
    assert not is_valid, "Should reject already closed trade"
    assert "closed" in error.lower() or "pnl" in error.lower()
    print("✅ test_already_closed_trade PASSED")


def test_invalid_status():
    """Test that invalid status is caught."""
    trade = {
        "id": "trade_1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "status": "invalid_status",
        "created_at": "2024-01-01T00:00:00Z",
        "entry_price": 50000,
        "stop_loss": 49000,
        "take_profit": 52000,
        "pnl": None
    }
    is_valid, error, context = validate_trade_for_closing(trade)
    assert not is_valid, "Should reject invalid status"
    assert "status" in error.lower()
    print("✅ test_invalid_status PASSED")


def test_missing_price_field():
    """Test that missing price field is caught."""
    trade = {
        "id": "trade_1",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "status": "filled",
        "created_at": "2024-01-01T00:00:00Z",
        "entry_price": 50000,
        "stop_loss": 49000,
        # Missing take_profit
        "pnl": None
    }
    is_valid, error, context = validate_trade_for_closing(trade)
    assert not is_valid, "Should reject missing take_profit"
    assert "take_profit" in error.lower()
    print("✅ test_missing_price_field PASSED")


def test_valid_candles():
    """Test that valid candles pass validation."""
    candles = [
        {"timestamp": "2024-01-01T00:00:00Z", "open": 50000, "high": 50100, "low": 49900, "close": 50050},
        {"timestamp": "2024-01-01T01:00:00Z", "open": 50050, "high": 50200, "low": 49950, "close": 50100},
    ]
    is_valid, error, context = validate_candles_for_closing("trade_1", "BTCUSDT", candles)
    assert is_valid, f"Valid candles should pass: {error}"
    print("✅ test_valid_candles PASSED")


def test_empty_candles():
    """Test that empty candles are rejected."""
    is_valid, error, context = validate_candles_for_closing("trade_1", "BTCUSDT", [])
    assert not is_valid, "Should reject empty candles"
    assert "no candles" in error.lower() or "empty" in error.lower()
    print("✅ test_empty_candles PASSED")


def test_missing_candle_field():
    """Test that candle with missing field is caught."""
    candles = [
        {"timestamp": "2024-01-01T00:00:00Z", "open": 50000, "high": 50100, "low": 49900},
        # Missing close
    ]
    is_valid, error, context = validate_candles_for_closing("trade_1", "BTCUSDT", candles)
    assert not is_valid, "Should reject candle with missing field"
    assert "close" in error.lower() or "missing" in error.lower()
    print("✅ test_missing_candle_field PASSED")


def test_non_chronological_candles():
    """Test that non-chronological candles are rejected."""
    candles = [
        {"timestamp": "2024-01-01T01:00:00Z", "open": 50050, "high": 50200, "low": 49950, "close": 50100},
        {"timestamp": "2024-01-01T00:00:00Z", "open": 50000, "high": 50100, "low": 49900, "close": 50050},
        # Earlier timestamp
    ]
    is_valid, error, context = validate_candles_for_closing("trade_1", "BTCUSDT", candles)
    assert not is_valid, "Should reject non-chronological candles"
    assert "chronological" in error.lower() or "order" in error.lower()
    print("✅ test_non_chronological_candles PASSED")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("RUNNING CLOSING VALIDATION TESTS")
    print("="*70 + "\n")
    
    try:
        test_valid_trade()
        test_missing_trade_id()
        test_already_closed_trade()
        test_invalid_status()
        test_missing_price_field()
        test_valid_candles()
        test_empty_candles()
        test_missing_candle_field()
        test_non_chronological_candles()
        
        print("\n" + "="*70)
        print("✅ ALL CLOSING VALIDATION TESTS PASSED")
        print("="*70)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


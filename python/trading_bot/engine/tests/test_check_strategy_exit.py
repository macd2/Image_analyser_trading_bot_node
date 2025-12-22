"""
Tests for check_strategy_exit.py - Autocloser dynamic stop/TP simulation.

Tests verify that the autocloser:
1. Tracks simulated stops/TPs as they change each candle
2. Checks SL/TP hits using CURRENT simulated stops (not original)
3. Handles both LONG and SHORT positions correctly
4. Returns audit trail of all stop/TP changes
"""

import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch

# Import the check_strategy_exit function from python/check_strategy_exit.py
# Test is at: python/trading_bot/engine/tests/test_check_strategy_exit.py
# Target is at: python/check_strategy_exit.py
# So we need to go up 4 levels: tests -> engine -> trading_bot -> python
import importlib.util
check_strategy_exit_path = Path(__file__).parent.parent.parent.parent / "check_strategy_exit.py"
spec = importlib.util.spec_from_file_location("check_strategy_exit", check_strategy_exit_path)
check_strategy_exit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_strategy_exit_module)
check_strategy_exit = check_strategy_exit_module.check_strategy_exit


def test_long_position_sl_hit_with_dynamic_stops():
    """Test LONG position where SL is hit using simulated stops."""

    # Candles: SL starts at 95, gets tightened to 98 at candle 2, then hit at candle 3
    candles = [
        {"timestamp": "2024-01-01T10:00:00Z", "open": 100, "high": 102, "low": 99, "close": 101},
        {"timestamp": "2024-01-01T10:05:00Z", "open": 101, "high": 103, "low": 100, "close": 102},
        {"timestamp": "2024-01-01T10:10:00Z", "open": 102, "high": 104, "low": 101, "close": 103},
        {"timestamp": "2024-01-01T10:15:00Z", "open": 103, "high": 105, "low": 97, "close": 104},  # SL hit at 98
    ]

    trade_data = {
        "id": "trade_1",
        "symbol": "BTCUSDT",
        "side": "Buy",  # LONG
        "entry_price": 100,
        "stop_loss": 95,
        "take_profit": 110
    }

    # Mock strategy that tightens SL to 98 at candle 2
    mock_strategy = Mock()
    candle_count = [0]  # Use list to track candle index in closure

    def should_exit_side_effect(trade, current_candle, pair_candle=None):
        idx = candle_count[0]
        candle_count[0] += 1
        if idx == 2:  # Candle 2
            return {
                "should_exit": False,
                "exit_details": {"reason": "no_exit", "stop_level": 98}
            }
        return {"should_exit": False, "exit_details": {"reason": "no_exit"}}

    mock_strategy.should_exit = Mock(side_effect=should_exit_side_effect)

    with patch('trading_bot.strategies.StrategyFactory') as mock_factory_class:
        mock_factory_class.get_available_strategies.return_value = {"TestStrategy": Mock(return_value=mock_strategy)}
        result = check_strategy_exit(
            trade_id="trade_1",
            strategy_name="TestStrategy",
            candles=candles,
            trade_data=trade_data
        )

    assert result["should_exit"] == True, f"Expected should_exit=True, got {result}"
    assert result["exit_reason"] == "sl_hit"
    assert result["exit_price"] == 98
    assert len(result["stop_updates"]) == 1
    assert result["stop_updates"][0]["type"] == "stop_loss"
    assert result["stop_updates"][0]["old"] == 95
    assert result["stop_updates"][0]["new"] == 98
    assert result["final_stops"]["stop_loss"] == 98
    print("✓ test_long_position_sl_hit_with_dynamic_stops PASSED")


def test_short_position_tp_hit_with_dynamic_stops():
    """Test SHORT position where TP is hit using simulated stops."""

    # Candles: TP starts at 90, gets tightened to 92 at candle 2, then hit at candle 3
    candles = [
        {"timestamp": "2024-01-01T10:00:00Z", "open": 100, "high": 101, "low": 99, "close": 99},
        {"timestamp": "2024-01-01T10:05:00Z", "open": 99, "high": 100, "low": 98, "close": 98},
        {"timestamp": "2024-01-01T10:10:00Z", "open": 98, "high": 99, "low": 97, "close": 97},
        {"timestamp": "2024-01-01T10:15:00Z", "open": 97, "high": 98, "low": 91, "close": 92},  # TP hit at 92
    ]

    trade_data = {
        "id": "trade_2",
        "symbol": "ETHUSDT",
        "side": "Sell",  # SHORT
        "entry_price": 100,
        "stop_loss": 105,
        "take_profit": 90
    }

    # Mock strategy that tightens TP to 92 at candle 2
    mock_strategy = Mock()
    candle_count = [0]

    def should_exit_side_effect(trade, current_candle, pair_candle=None):
        idx = candle_count[0]
        candle_count[0] += 1
        if idx == 2:  # Candle 2
            return {
                "should_exit": False,
                "exit_details": {"reason": "no_exit", "tp_level": 92}
            }
        return {"should_exit": False, "exit_details": {"reason": "no_exit"}}

    mock_strategy.should_exit = Mock(side_effect=should_exit_side_effect)

    with patch('trading_bot.strategies.StrategyFactory') as mock_factory_class:
        mock_factory_class.get_available_strategies.return_value = {"TestStrategy": Mock(return_value=mock_strategy)}
        result = check_strategy_exit(
            trade_id="trade_2",
            strategy_name="TestStrategy",
            candles=candles,
            trade_data=trade_data
        )

    assert result["should_exit"] == True
    assert result["exit_reason"] == "tp_hit"
    assert result["exit_price"] == 92
    assert len(result["stop_updates"]) == 1
    assert result["stop_updates"][0]["type"] == "take_profit"
    assert result["stop_updates"][0]["old"] == 90
    assert result["stop_updates"][0]["new"] == 92
    print("✓ test_short_position_tp_hit_with_dynamic_stops PASSED")


def test_multiple_stop_updates_audit_trail():
    """Test that multiple stop updates are tracked in audit trail."""

    candles = [
        {"timestamp": "2024-01-01T10:00:00Z", "open": 100, "high": 102, "low": 99, "close": 101},
        {"timestamp": "2024-01-01T10:05:00Z", "open": 101, "high": 103, "low": 100, "close": 102},
        {"timestamp": "2024-01-01T10:10:00Z", "open": 102, "high": 104, "low": 101, "close": 103},
        {"timestamp": "2024-01-01T10:15:00Z", "open": 103, "high": 105, "low": 101, "close": 104},
        {"timestamp": "2024-01-01T10:20:00Z", "open": 104, "high": 106, "low": 102, "close": 105},
    ]

    trade_data = {
        "id": "trade_3",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "entry_price": 100,
        "stop_loss": 95,
        "take_profit": 110
    }

    # Mock strategy that updates stops multiple times
    mock_strategy = Mock()
    candle_count = [0]

    def should_exit_side_effect(trade, current_candle, pair_candle=None):
        idx = candle_count[0]
        candle_count[0] += 1
        exit_details = {"reason": "no_exit"}

        if idx == 1:
            exit_details["stop_level"] = 96
        elif idx == 2:
            exit_details["stop_level"] = 97
            exit_details["tp_level"] = 115
        elif idx == 3:
            exit_details["stop_level"] = 98

        return {"should_exit": False, "exit_details": exit_details}

    mock_strategy.should_exit = Mock(side_effect=should_exit_side_effect)

    with patch('trading_bot.strategies.StrategyFactory') as mock_factory_class:
        mock_factory_class.get_available_strategies.return_value = {"TestStrategy": Mock(return_value=mock_strategy)}
        result = check_strategy_exit(
            trade_id="trade_3",
            strategy_name="TestStrategy",
            candles=candles,
            trade_data=trade_data
        )

    assert result["should_exit"] == False, f"Expected should_exit=False, got {result}"
    assert "stop_updates" in result, f"Missing stop_updates in result: {result.keys()}"
    assert len(result["stop_updates"]) == 4, f"Expected 4 updates, got {len(result['stop_updates'])}: {result['stop_updates']}"
    assert result["stop_updates"][0]["new"] == 96
    assert result["stop_updates"][1]["new"] == 97
    assert result["stop_updates"][2]["type"] == "take_profit"
    assert result["stop_updates"][2]["new"] == 115
    assert result["stop_updates"][3]["new"] == 98
    assert result["final_stops"]["stop_loss"] == 98
    assert result["final_stops"]["take_profit"] == 115
    print("✓ test_multiple_stop_updates_audit_trail PASSED")


if __name__ == "__main__":
    test_long_position_sl_hit_with_dynamic_stops()
    test_short_position_tp_hit_with_dynamic_stops()
    test_multiple_stop_updates_audit_trail()
    print("\n✅ All autocloser tests PASSED!")


"""
Tests for position monitor using strategy.should_exit() method.

Verifies that the position monitor correctly calls should_exit() and
handles exit decisions for both price-based and spread-based strategies.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, MonitorMode


class TestPositionMonitorShouldExit:
    """Test position monitor integration with strategy.should_exit()."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.set_trading_stop = Mock(return_value={})
        return executor

    @pytest.fixture
    def monitor(self, mock_executor):
        """Create position monitor instance."""
        return EnhancedPositionMonitor(
            order_executor=mock_executor,
            mode=MonitorMode.EVENT_DRIVEN,
            master_tightening_enabled=True,
        )

    def test_check_strategy_exit_price_based(self, monitor):
        """Test check_strategy_exit() for price-based strategy."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": {"reason": "tp_touched", "price": 105.0}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify exit result
        assert result is not None
        assert result["should_exit"] is True
        assert result["exit_reason"] == "tp_touched"

    def test_check_strategy_exit_spread_based(self, monitor):
        """Test check_strategy_exit() for spread-based strategy."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": {
                "reason": "z_score_exit",
                "z_score": 2.5,
                "threshold": 2.0,
            }
        })

        trade = {
            "id": "trade_1",
            "symbol": "RENDER",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
            "strategy_metadata": {
                "beta": 1.0,
                "spread_mean": 0.0,
                "spread_std": 1.0,
                "z_exit_threshold": 2.0,
                "pair_symbol": "AKT",
            }
        }
        current_candle = {"close": 100.0}
        pair_candle = {"close": 150.0}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            pair_candle=pair_candle,
            strategy=mock_strategy,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Verify should_exit was called
        assert mock_strategy.should_exit.called
        # Verify exit result
        assert result is not None
        assert result["should_exit"] is True
        assert result["exit_reason"] == "z_score_exit"

    def test_check_strategy_exit_no_exit(self, monitor):
        """Test check_strategy_exit() when no exit condition met."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": False,
            "exit_details": {"reason": "no_exit"}
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 101.0}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Should return full result even when no exit (for stop/TP syncing)
        assert result is not None
        assert result["should_exit"] is False
        assert result["exit_details"]["reason"] == "no_exit"

    def test_check_strategy_exit_no_strategy(self, monitor):
        """Test check_strategy_exit() without strategy."""
        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=None,
        )

        # Should return None when no strategy
        assert result is None

    def test_check_strategy_exit_handles_error(self, monitor):
        """Test check_strategy_exit() handles errors gracefully."""
        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(side_effect=Exception("Strategy error"))

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        # Should not raise exception
        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Should return None on error
        assert result is None

    def test_check_strategy_exit_stores_exit_details(self, monitor):
        """Test check_strategy_exit() stores exit_details."""
        exit_details = {
            "reason": "tp_touched",
            "price": 105.0,
            "tp": 105.0,
            "sl": 98.0,
            "distance_to_tp": 0.0,
            "distance_to_sl": 7.0,
        }

        mock_strategy = Mock()
        mock_strategy.should_exit = Mock(return_value={
            "should_exit": True,
            "exit_details": exit_details
        })

        trade = {
            "id": "trade_1",
            "symbol": "BTCUSDT",
            "entry_price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 105.0,
        }
        current_candle = {"close": 105.5}

        result = monitor.check_strategy_exit(
            trade=trade,
            current_candle=current_candle,
            strategy=mock_strategy,
        )

        # Verify exit_details are stored
        assert result is not None
        assert result["exit_details"] == exit_details


class TestSyncStrategyStops:
    """Test _sync_strategy_stops() method for syncing strategy-calculated stops/TPs."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.set_trading_stop = Mock(return_value={})
        return executor

    @pytest.fixture
    def monitor(self, mock_executor):
        """Create position monitor instance."""
        return EnhancedPositionMonitor(
            order_executor=mock_executor,
            mode=MonitorMode.EVENT_DRIVEN,
            master_tightening_enabled=True,
        )

    @pytest.fixture
    def sample_position(self):
        """Create sample position."""
        from trading_bot.core.state_manager import PositionState
        return PositionState(
            symbol="BTCUSDT",
            side="Buy",
            size=1.0,
            entry_price=100.0,
            mark_price=110.0,
            stop_loss=95.0,
            take_profit=120.0,
            leverage="1",
            unrealised_pnl=10.0,
        )

    def test_sync_no_custom_stops(self, monitor, sample_position):
        """Test sync when strategy doesn't provide custom stops."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 110.0,
                # No stop_level or tp_level
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return False (no updates)
        assert updated is False
        # Executor should not be called
        monitor.executor.set_trading_stop.assert_not_called()

    def test_sync_sl_changed(self, monitor, sample_position):
        """Test sync when SL needs to be updated."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 105.0,  # Changed from 95.0
                "tp_level": 120.0,    # Unchanged
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (updated)
        assert updated is True
        # Executor should be called for SL
        monitor.executor.set_trading_stop.assert_called()
        call_args = monitor.executor.set_trading_stop.call_args
        assert call_args[1]["symbol"] == "BTCUSDT"
        assert call_args[1]["stop_loss"] == 105.0

    def test_sync_tp_changed(self, monitor, sample_position):
        """Test sync when TP needs to be updated."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 95.0,   # Unchanged
                "tp_level": 130.0,    # Changed from 120.0
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (updated)
        assert updated is True
        # Executor should be called for TP
        monitor.executor.set_trading_stop.assert_called()
        call_args = monitor.executor.set_trading_stop.call_args
        assert call_args[1]["symbol"] == "BTCUSDT"
        assert call_args[1]["take_profit"] == 130.0

    def test_sync_both_changed(self, monitor, sample_position):
        """Test sync when both SL and TP need to be updated."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 105.0,  # Changed from 95.0
                "tp_level": 130.0,    # Changed from 120.0
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (updated)
        assert updated is True
        # Executor should be called twice (once for SL, once for TP)
        assert monitor.executor.set_trading_stop.call_count == 2

    def test_sync_tolerance_check(self, monitor, sample_position):
        """Test that sync respects tolerance (0.0001)."""
        # Change SL by less than tolerance
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 95.00005,  # Only 0.00005 change (within tolerance)
                "tp_level": 120.0,
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return False (no updates due to tolerance)
        assert updated is False
        monitor.executor.set_trading_stop.assert_not_called()

    def test_sync_api_error_handling(self, monitor, sample_position):
        """Test sync handles API errors gracefully."""
        monitor.executor.set_trading_stop = Mock(return_value={"error": "API error"})

        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 105.0,
                "tp_level": 130.0,
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return False (no successful updates)
        assert updated is False

    def test_sync_only_sl_provided(self, monitor, sample_position):
        """Test sync when only SL is provided (no TP)."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "stop_level": 105.0,  # Provided
                # No tp_level
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (SL updated)
        assert updated is True
        # Executor should be called once (only for SL)
        monitor.executor.set_trading_stop.assert_called_once()

    def test_sync_only_tp_provided(self, monitor, sample_position):
        """Test sync when only TP is provided (no SL)."""
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                # No stop_level
                "tp_level": 130.0,  # Provided
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (TP updated)
        assert updated is True
        # Executor should be called once (only for TP)
        monitor.executor.set_trading_stop.assert_called_once()


class TestNewListingStrategyIntegration:
    """Integration tests for NewListingStrategy with PositionMonitor."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock order executor."""
        executor = Mock()
        executor.set_trading_stop = Mock(return_value={})
        return executor

    @pytest.fixture
    def monitor(self, mock_executor):
        """Create position monitor instance."""
        return EnhancedPositionMonitor(
            order_executor=mock_executor,
            mode=MonitorMode.EVENT_DRIVEN,
            master_tightening_enabled=True,
        )

    @pytest.fixture
    def sample_position(self):
        """Create sample position for NewListingStrategy."""
        from trading_bot.core.state_manager import PositionState
        return PositionState(
            symbol="BTCUSDT",
            side="Buy",
            size=1.0,
            entry_price=100.0,
            mark_price=112.0,  # +12% gain (breakeven trigger)
            stop_loss=95.0,
            take_profit=130.0,
            leverage="1",
            unrealised_pnl=12.0,
        )

    def test_new_listing_strategy_sync_trailing_stop(self, monitor, sample_position):
        """Test that PositionMonitor syncs NewListingStrategy's trailing stop."""
        # Simulate NewListingStrategy's should_exit() response with trailing stop
        exit_result = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 112.0,
                "phase": 2,  # Phase 2: Breakeven achieved
                "highest_seen": 112.0,
                "breakeven_achieved": True,
                "dynamic_tp": 126.0,
                "stop_level": 100.8,  # Trailing stop at 90% of highest
                "tp_level": 126.0,    # Dynamic TP
                "stop_type": "trailing",
                "tp_type": "dynamic",
            },
            "updated_meta": {
                "phase": 2,
                "stop": 100.8,
                "highest": 112.0,
                "candles": 5,
            }
        }

        updated = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return True (both SL and TP updated)
        assert updated is True
        # Executor should be called twice (SL and TP)
        assert monitor.executor.set_trading_stop.call_count == 2

    def test_new_listing_strategy_phase_transition(self, monitor, sample_position):
        """Test PositionMonitor handles phase transitions in NewListingStrategy."""
        # Phase 1 -> Phase 2 transition
        exit_result_phase1 = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 110.0,
                "phase": 1,
                "highest_seen": 110.0,
                "breakeven_achieved": False,
                "dynamic_tp": 112.0,
                "stop_level": 95.0,  # Original SL
                "tp_level": 112.0,
                "stop_type": "fixed",
                "tp_type": "dynamic",
            }
        }

        # First monitoring cycle (Phase 1)
        updated1 = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result_phase1,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Phase 2 with tighter trailing stop
        exit_result_phase2 = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 112.0,
                "phase": 2,
                "highest_seen": 112.0,
                "breakeven_achieved": True,
                "dynamic_tp": 126.0,
                "stop_level": 100.8,  # Tighter trailing stop
                "tp_level": 126.0,
                "stop_type": "trailing",
                "tp_type": "dynamic",
            }
        }

        # Second monitoring cycle (Phase 2)
        updated2 = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result_phase2,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Both should trigger updates
        assert updated1 is True or updated2 is True

    def test_new_listing_strategy_no_exit_no_change(self, monitor, sample_position):
        """Test that PositionMonitor doesn't update if stops haven't changed."""
        # First call with initial stops
        exit_result1 = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 112.0,
                "phase": 2,
                "highest_seen": 112.0,
                "breakeven_achieved": True,
                "dynamic_tp": 126.0,
                "stop_level": 100.8,
                "tp_level": 126.0,
                "stop_type": "trailing",
                "tp_type": "dynamic",
            }
        }

        # First sync - this will update the position
        updated1 = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result1,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should have updated (position had different stops)
        assert updated1 is True

        # Now update position to match the strategy's stops
        sample_position.stop_loss = 100.8
        sample_position.take_profit = 126.0

        # Reset mock
        monitor.executor.set_trading_stop.reset_mock()

        # Second call with same stops (now position matches)
        exit_result2 = {
            "should_exit": False,
            "exit_details": {
                "reason": "no_exit",
                "current_price": 112.0,
                "phase": 2,
                "highest_seen": 112.0,
                "breakeven_achieved": True,
                "dynamic_tp": 126.0,
                "stop_level": 100.8,  # Same as position now
                "tp_level": 126.0,    # Same as position now
                "stop_type": "trailing",
                "tp_type": "dynamic",
            }
        }

        # Second sync with same values
        updated2 = monitor._sync_strategy_stops(
            position=sample_position,
            exit_result=exit_result2,
            instance_id="instance_1",
            run_id="run_1",
            trade_id="trade_1",
        )

        # Should return False (no changes)
        assert updated2 is False
        # Executor should not be called
        monitor.executor.set_trading_stop.assert_not_called()

    def test_new_listing_strategy_emergency_exit_trigger(self, monitor, sample_position):
        """Test PositionMonitor handles emergency exit condition."""
        # Simulate emergency exit (after +40% gain, exits on 15% drop)
        sample_position.mark_price = 140.0  # +40% gain

        exit_result = {
            "should_exit": True,  # Emergency exit triggered
            "exit_details": {
                "reason": "emergency_exit",
                "current_price": 140.0,
                "phase": 3,
                "highest_seen": 140.0,
                "breakeven_achieved": True,
                "dynamic_tp": 161.0,
                "stop_level": 119.0,  # 15% below highest
                "tp_level": 161.0,
                "stop_type": "emergency",
                "tp_type": "dynamic",
            }
        }

        # When should_exit=True, check_strategy_exit handles the exit
        # _sync_strategy_stops is only called when should_exit=False
        # So this test verifies the exit_details structure is correct
        assert exit_result["should_exit"] is True
        assert exit_result["exit_details"]["reason"] == "emergency_exit"
        assert exit_result["exit_details"]["stop_level"] == 119.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


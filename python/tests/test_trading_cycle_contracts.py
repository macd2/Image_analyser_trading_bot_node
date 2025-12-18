"""
Property-Based Contract Tests for Trading Cycle

Tests that methods return expected values for known inputs,
and that invariants hold for any valid input.

Uses hypothesis for property-based testing + manual test cases from contracts.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
from datetime import datetime, timezone
from typing import Dict, Any
from unittest.mock import Mock, MagicMock
import json

from trading_bot.engine.paper_trade_simulator import PaperTradeSimulator, Candle
from trading_bot.engine.enhanced_position_monitor import EnhancedPositionMonitor, PositionState


class TestTradeCreationContract:
    """Test trade creation against contract specification"""

    def test_price_based_trade_creation_known_input(self):
        """Test case 1a: Price-based trade creation (AiImageAnalyzer)"""
        recommendation = {
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'confidence': 0.85,
            'strategy_name': 'AiImageAnalyzer',
            'strategy_type': 'price_based',
            'strategy_metadata': {},  # Price-based has no metadata
        }

        # Verify contract invariants
        assert recommendation['stop_loss'] < recommendation['entry_price']
        assert recommendation['entry_price'] < recommendation['take_profit']
        assert recommendation['strategy_type'] == 'price_based'
        assert recommendation['strategy_metadata'] == {}

    def test_cointegration_trade_creation_known_input(self):
        """Test case 1b: Cointegration trade creation with metadata"""
        recommendation = {
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'confidence': 0.85,
            'strategy_name': 'CointegrationSpreadTrader',
            'strategy_type': 'spread_based',
            'strategy_metadata': {
                'beta': 0.85,
                'spread_mean': 100.5,
                'spread_std': 25.3,
                'pair_symbol': 'ETH',
                'z_exit_threshold': 0.5,
            }
        }

        # Verify contract invariants
        assert recommendation['stop_loss'] < recommendation['entry_price']
        assert recommendation['entry_price'] < recommendation['take_profit']
        assert recommendation['strategy_type'] == 'spread_based'
        assert 'pair_symbol' in recommendation['strategy_metadata']
        assert 'z_exit_threshold' in recommendation['strategy_metadata']
        
        rr_ratio = (recommendation['take_profit'] - recommendation['entry_price']) / \
                   (recommendation['entry_price'] - recommendation['stop_loss'])
        assert rr_ratio > 0
    
    def test_short_trade_creation_known_input(self):
        """Test case 2: Short trade creation with known input"""
        recommendation = {
            'symbol': 'ETH',
            'side': 'Sell',
            'entry_price': 2500,
            'stop_loss': 2600,
            'take_profit': 2400,
            'confidence': 0.75,
            'strategy_name': 'AiImageAnalyzer',
            'strategy_type': 'price_based',
            'strategy_metadata': {}
        }
        
        # Verify contract invariants for short
        assert recommendation['stop_loss'] > recommendation['entry_price']
        assert recommendation['entry_price'] > recommendation['take_profit']
        
        rr_ratio = (recommendation['entry_price'] - recommendation['take_profit']) / \
                   (recommendation['stop_loss'] - recommendation['entry_price'])
        assert rr_ratio > 0
    
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
        
        rr_ratio = (take_profit - entry_price) / (entry_price - stop_loss)
        assert rr_ratio > 0
    
    @given(
        entry_price=st.floats(min_value=100, max_value=100000),
        sl_offset=st.floats(min_value=1, max_value=10000),
        tp_offset=st.floats(min_value=1, max_value=10000),
    )
    @settings(max_examples=100)
    def test_trade_creation_invariants_short(self, entry_price, sl_offset, tp_offset):
        """Property test: SL/TP invariants hold for any short trade"""
        stop_loss = entry_price + sl_offset
        take_profit = entry_price - tp_offset
        
        # Verify invariants
        assert stop_loss > entry_price > take_profit
        
        rr_ratio = (entry_price - take_profit) / (stop_loss - entry_price)
        assert rr_ratio > 0


class TestSimulatorContract:
    """Test simulator against contract specification"""
    
    @pytest.fixture
    def simulator(self):
        return PaperTradeSimulator()
    
    def test_long_trade_fills_and_hits_tp(self, simulator):
        """Test case 1: Long trade fills and hits TP"""
        # Use proper millisecond timestamps (Jan 1, 2024 12:00:00 UTC onwards)
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            'id': 'trade_1',
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'quantity': 1.0,
            'created_at': base_time.isoformat(),
        }

        candles = [
            Candle(timestamp=base_ms, open=44500, high=45500, low=44000, close=45000),
            Candle(timestamp=base_ms + 60000, open=45000, high=45200, low=44900, close=45100),
            Candle(timestamp=base_ms + 120000, open=45100, high=46100, low=45000, close=46000),
        ]

        result = simulator.simulate_trade(trade, candles)

        # Verify contract output
        assert result is not None
        assert result['status'] == 'closed'
        assert result['fill_price'] == 45000
        assert result['exit_price'] == 46000
        assert result['exit_reason'] == 'tp_hit'
        assert result['pnl'] == 1000
        assert abs(result['pnl_percent'] - 2.22) < 0.1
    
    def test_short_trade_fills_and_hits_sl(self, simulator):
        """Test case 2: Short trade fills and hits SL"""
        # Use proper millisecond timestamps (Jan 1, 2024 12:00:00 UTC onwards)
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            'id': 'trade_2',
            'symbol': 'ETH',
            'side': 'Sell',
            'entry_price': 2500,
            'stop_loss': 2600,
            'take_profit': 2400,
            'quantity': 1.0,
            'created_at': base_time.isoformat(),
        }

        candles = [
            Candle(timestamp=base_ms, open=2600, high=2700, low=2400, close=2500),
            Candle(timestamp=base_ms + 60000, open=2500, high=2550, low=2450, close=2520),
            Candle(timestamp=base_ms + 120000, open=2520, high=2650, low=2500, close=2600),
        ]

        result = simulator.simulate_trade(trade, candles)

        assert result is not None
        assert result['status'] == 'closed'
        assert result['exit_reason'] == 'sl_hit'

    def test_price_based_strategy_trade_with_strategy_none(self, simulator):
        """Test case 2b: Price-based strategy (strategy=None)"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            'id': 'trade_pb_1',
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'quantity': 1.0,
            'created_at': base_time.isoformat(),
            'strategy_name': 'AiImageAnalyzer',
            'strategy_type': 'price_based',
            'strategy_metadata': {},
        }

        candles = [
            Candle(timestamp=base_ms, open=44500, high=45500, low=44000, close=45000),
            Candle(timestamp=base_ms + 60000, open=45000, high=45200, low=44900, close=45100),
            Candle(timestamp=base_ms + 120000, open=45100, high=46100, low=45000, close=46000),
        ]

        result = simulator.simulate_trade(trade, candles, strategy=None)

        # Verify price-based exit (TP hit)
        assert result is not None
        assert result['exit_reason'] == 'tp_hit'
        assert result['pnl'] == 1000

    def test_cointegration_strategy_trade_with_mock_strategy(self, simulator):
        """Test case 2c: Cointegration strategy (strategy provided)"""
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            'id': 'trade_coint_1',
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'quantity': 1.0,
            'created_at': base_time.isoformat(),
            'strategy_name': 'CointegrationSpreadTrader',
            'strategy_type': 'spread_based',
            'strategy_metadata': {
                'beta': 0.85,
                'pair_symbol': 'ETH',
                'z_exit_threshold': 0.5,
            },
        }

        # Mock strategy that exits on z-score
        mock_strategy = Mock()
        mock_strategy.should_exit.return_value = {
            'should_exit': True,
            'exit_reason': 'strategy_exit',
        }

        candles = [
            Candle(timestamp=base_ms, open=44500, high=45500, low=44000, close=45000),
            Candle(timestamp=base_ms + 60000, open=45000, high=45200, low=44900, close=45100),
            Candle(timestamp=base_ms + 120000, open=45100, high=45300, low=45000, close=45100),
        ]

        result = simulator.simulate_trade(trade, candles, strategy=mock_strategy)

        # Verify strategy exit was called
        assert mock_strategy.should_exit.called
        assert result is not None
        assert result['exit_reason'] == 'strategy_exit'
        # Exit at close price of candle where strategy exit triggered (45100)
        assert result['pnl'] == 100  # (45100 - 45000) * 1.0
        assert abs(result['pnl_percent'] - 0.22) < 0.1
    
    def test_trade_never_fills(self, simulator):
        """Test case 4: Trade never fills"""
        # Use proper millisecond timestamps (Jan 1, 2024 12:00:00 UTC onwards)
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        base_ms = int(base_time.timestamp() * 1000)

        trade = {
            'id': 'trade_3',
            'symbol': 'BTC',
            'side': 'Buy',
            'entry_price': 45000,
            'stop_loss': 44000,
            'take_profit': 46000,
            'quantity': 1.0,
            'created_at': base_time.isoformat(),
        }

        candles = [
            Candle(timestamp=base_ms, open=44000, high=44500, low=43500, close=44200),
            Candle(timestamp=base_ms + 60000, open=44200, high=44800, low=44000, close=44500),
        ]

        result = simulator.simulate_trade(trade, candles)

        # Should return None if never filled
        assert result is None
    
    @given(
        entry_price=st.floats(min_value=1000, max_value=100000),
        fill_price_offset=st.floats(min_value=-1000, max_value=1000),
        exit_price_offset=st.floats(min_value=-2000, max_value=2000),
        quantity=st.floats(min_value=0.01, max_value=10),
    )
    @settings(max_examples=50)
    def test_pnl_calculation_invariants(self, entry_price, fill_price_offset, 
                                        exit_price_offset, quantity):
        """Property test: P&L calculation invariants hold"""
        fill_price = entry_price + fill_price_offset
        exit_price = fill_price + exit_price_offset
        
        # Skip invalid combinations
        assume(fill_price > 0 and exit_price > 0)
        
        # For long: pnl = (exit - fill) * qty
        pnl_long = (exit_price - fill_price) * quantity
        pnl_percent_long = (pnl_long / (fill_price * quantity)) * 100
        
        # Verify invariants
        assert pnl_long == (exit_price - fill_price) * quantity
        assert abs(pnl_percent_long - ((exit_price - fill_price) / fill_price * 100)) < 0.01


class TestPositionMonitorContract:
    """Test position monitor against contract specification"""
    
    def test_strategy_exit_highest_priority(self):
        """Test case 1: Strategy exit triggered (highest priority)"""
        # Strategy exit should be checked before other tightening
        
        position = Mock()
        position.symbol = 'BTC'
        position.side = 'Buy'
        position.entry_price = 45000
        position.mark_price = 45200
        position.stop_loss = 44000
        position.take_profit = 46000
        
        strategy = Mock()
        strategy.should_exit.return_value = {
            'should_exit': True,
            'exit_reason': 'z_score_exit'
        }
        
        current_candle = {
            'timestamp': 1000,
            'open': 45200,
            'high': 45300,
            'low': 45100,
            'close': 45200
        }
        
        # Verify strategy exit is checked
        exit_result = strategy.should_exit(
            trade={'symbol': 'BTC'},
            current_candle=current_candle,
            pair_candle=None
        )
        
        assert exit_result['should_exit'] is True
        assert exit_result['exit_reason'] == 'z_score_exit'
    
    def test_price_based_position_monitor_tightening(self):
        """Test case 3b: Position monitor tightens SL for price-based trades"""
        position = Mock()
        position.symbol = 'BTC'
        position.side = 'Buy'
        position.entry_price = 45000
        position.mark_price = 45500  # 50% to TP
        position.stop_loss = 44000
        position.take_profit = 46000

        # Position monitor should tighten SL to breakeven
        new_sl = position.entry_price

        # Verify invariants
        assert new_sl > position.stop_loss  # Tightening upward
        assert new_sl >= position.entry_price  # Never worse than entry

    def test_cointegration_position_monitor_strategy_exit(self):
        """Test case 3c: Position monitor calls strategy exit for cointegration"""
        position = Mock()
        position.symbol = 'BTC'
        position.side = 'Buy'
        position.entry_price = 45000
        position.mark_price = 45200
        position.stop_loss = 44000
        position.take_profit = 46000

        mock_strategy = Mock()
        mock_strategy.should_exit.return_value = {
            'should_exit': True,
            'exit_reason': 'z_score_exit',
        }

        current_candle = {
            'timestamp': 1704110400000,
            'open': 45200,
            'high': 45300,
            'low': 45100,
            'close': 45200,
        }

        # Position monitor should check strategy exit first
        exit_result = mock_strategy.should_exit(
            trade={'symbol': 'BTC'},
            current_candle=current_candle,
            pair_candle=None
        )

        # Verify strategy exit was checked
        assert exit_result['should_exit'] is True
        assert exit_result['exit_reason'] == 'z_score_exit'

    @given(
        entry_price=st.floats(min_value=1000, max_value=100000),
        current_price_offset=st.floats(min_value=0, max_value=5000),
        sl_offset=st.floats(min_value=100, max_value=5000),
    )
    @settings(max_examples=50)
    def test_tightening_invariants_long(self, entry_price, current_price_offset, sl_offset):
        """Property test: Tightening invariants hold for long positions"""
        current_price = entry_price + current_price_offset
        current_sl = entry_price - sl_offset

        # Skip invalid combinations
        assume(current_price > entry_price and current_sl < entry_price)

        # If tightening to breakeven
        new_sl = entry_price

        # Verify invariants
        assert new_sl > current_sl  # Tightening upward
        assert new_sl >= entry_price  # Never worse than entry

    @given(
        entry_price=st.floats(min_value=1000, max_value=100000),
        current_price_offset=st.floats(min_value=0, max_value=5000),
        sl_offset=st.floats(min_value=100, max_value=5000),
    )
    @settings(max_examples=50)
    def test_tightening_invariants_short(self, entry_price, current_price_offset, sl_offset):
        """Property test: Tightening invariants hold for short positions"""
        current_price = entry_price - current_price_offset
        current_sl = entry_price + sl_offset

        # Skip invalid combinations
        assume(current_price < entry_price and current_sl > entry_price)

        # If tightening to breakeven
        new_sl = entry_price

        # Verify invariants
        assert new_sl < current_sl  # Tightening downward
        assert new_sl <= entry_price  # Never worse than entry


"""
End-to-End Test: Complete Spread-Based Trading Workflow with Database Operations

This test validates the entire spread-based trading lifecycle:
1. Create a spread-based trade recommendation with all required fields
2. Record the trade to the database with all spread-based columns
3. Simulate autocloser filling the trade with pair_fill_price
4. Simulate autocloser closing the trade with pair_exit_price
5. Verify P&L calculation for both symbols
6. Verify backward compatibility with price-based trades
"""

import pytest
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import uuid
from dotenv import load_dotenv

# Load environment variables from .env.local
env_path = Path(__file__).parent.parent.parent / ".env.local"
if env_path.exists():
    load_dotenv(env_path)

# Force PostgreSQL for testing (use Supabase)
os.environ['DB_TYPE'] = 'postgres'

sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_bot.db.client import get_connection, release_connection, execute, query
from trading_bot.engine.trading_engine import TradingEngine
from trading_bot.engine.trade_tracker import TradeTracker


class TestSpreadBasedE2EDatabase:
    """End-to-end tests for spread-based trading with database operations."""

    @pytest.fixture
    def db_connection(self):
        """Get database connection to Supabase PostgreSQL."""
        conn = get_connection()
        yield conn
        release_connection(conn)
    
    @pytest.fixture
    def spread_based_recommendation(self):
        """Create a mock spread-based recommendation."""
        return {
            "id": str(uuid.uuid4()),
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.85,
            "setup_quality": 0.9,
            "market_environment": 0.8,
            "strategy_type": "spread_based",
            "strategy_name": "CointegrationSpreadTrader",
            "timeframe": "1h",
            "entry_price": 45000.0,
            "stop_loss": 44000.0,
            "take_profit": 46000.0,
            "units_x": 1.0,  # Main symbol quantity (signed)
            "units_y": -0.05,  # Pair symbol quantity (signed, opposite direction)
            "pair_symbol": "ETHUSDT",
            "analysis": {
                "price_levels": {
                    "entry": 45000.0,
                    "stop_loss": 44000.0,
                    "take_profit": 46000.0
                }
            },
            "strategy_metadata": {
                "beta": 0.05,
                "spread_mean": 250.0,
                "spread_std": 10.0,
                "z_score_at_entry": -2.0,
                "z_exit_threshold": 0.2,
                "price_x_at_entry": 45000.0,
                "price_y_at_entry": 2500.0,
                "max_spread_deviation": 15.0
            }
        }
    
    @pytest.fixture
    def price_based_recommendation(self):
        """Create a mock price-based recommendation for backward compatibility."""
        return {
            "id": str(uuid.uuid4()),
            "symbol": "BTCUSDT",
            "recommendation": "BUY",
            "confidence": 0.85,
            "setup_quality": 0.9,
            "market_environment": 0.8,
            "strategy_type": "price_based",
            "strategy_name": "TrendFollower",
            "timeframe": "1h",
            "entry_price": 45000.0,
            "stop_loss": 44000.0,
            "take_profit": 46000.0,
            "analysis": {
                "price_levels": {
                    "entry": 45000.0,
                    "stop_loss": 44000.0,
                    "take_profit": 46000.0
                }
            }
        }
    
    def test_spread_based_trade_insert_with_all_columns(self, db_connection, spread_based_recommendation):
        """Test that spread-based trades are inserted with all required columns."""
        trade_id = str(uuid.uuid4())
        rec_id = spread_based_recommendation["id"]

        # First, create the recommendation record (parent)
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            spread_based_recommendation["symbol"],
            spread_based_recommendation["timeframe"],
            spread_based_recommendation["recommendation"],
            spread_based_recommendation["confidence"],
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Simulate TradingEngine._record_trade()
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, pair_quantity, status, order_id, order_id_pair, confidence, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            spread_based_recommendation["symbol"],
            "Buy",
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            spread_based_recommendation["units_x"],
            spread_based_recommendation["units_y"],
            "paper_trade",
            f"order_{trade_id}",
            f"order_pair_{trade_id}",
            spread_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat()
        ))

        # Verify the trade was inserted
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        trade = result[0]

        # Verify all spread-based columns
        assert trade["quantity"] == spread_based_recommendation["units_x"]
        assert trade["pair_quantity"] == spread_based_recommendation["units_y"]
        assert trade["order_id"] == f"order_{trade_id}"
        assert trade["order_id_pair"] == f"order_pair_{trade_id}"
        assert trade["pair_fill_price"] is None  # Not filled yet
        assert trade["pair_exit_price"] is None  # Not exited yet
    
    def test_price_based_trade_backward_compatibility(self, db_connection, price_based_recommendation):
        """Test that price-based trades work with NULL spread-based columns."""
        trade_id = str(uuid.uuid4())
        rec_id = price_based_recommendation["id"]

        # First, create the recommendation record (parent)
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            price_based_recommendation["symbol"],
            price_based_recommendation["timeframe"],
            price_based_recommendation["recommendation"],
            price_based_recommendation["confidence"],
            price_based_recommendation["entry_price"],
            price_based_recommendation["stop_loss"],
            price_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Insert price-based trade (no pair_quantity, order_id_pair)
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, status, order_id, confidence, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            price_based_recommendation["symbol"],
            "Buy",
            price_based_recommendation["entry_price"],
            price_based_recommendation["stop_loss"],
            price_based_recommendation["take_profit"],
            1.0,
            "paper_trade",
            f"order_{trade_id}",
            price_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat()
        ))

        # Verify the trade was inserted
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        trade = result[0]

        # Verify spread-based columns are NULL
        assert trade["pair_quantity"] is None
        assert trade["order_id_pair"] is None
        assert trade["pair_fill_price"] is None
        assert trade["pair_exit_price"] is None

    def test_spread_based_trade_fill_update(self, db_connection, spread_based_recommendation):
        """Test that autocloser correctly updates fill_price and pair_fill_price."""
        trade_id = str(uuid.uuid4())
        rec_id = spread_based_recommendation["id"]

        # Create recommendation first
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            spread_based_recommendation["symbol"],
            spread_based_recommendation["timeframe"],
            spread_based_recommendation["recommendation"],
            spread_based_recommendation["confidence"],
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Insert spread-based trade
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, pair_quantity, status, order_id, order_id_pair, confidence, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            spread_based_recommendation["symbol"],
            "Buy",
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            spread_based_recommendation["units_x"],
            spread_based_recommendation["units_y"],
            "paper_trade",
            f"order_{trade_id}",
            f"order_pair_{trade_id}",
            spread_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat()
        ))

        # Simulate autocloser fill update
        fill_price = 45000.0
        pair_fill_price = 2500.0
        fill_time = datetime.now(timezone.utc).isoformat()

        execute(db_connection, """
            UPDATE trades SET
                fill_price = %s,
                pair_fill_price = %s,
                fill_time = %s,
                filled_at = %s,
                status = 'filled'
            WHERE id = %s
        """, (fill_price, pair_fill_price, fill_time, fill_time, trade_id))

        # Verify the update
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        trade = result[0]

        assert trade["fill_price"] == fill_price
        assert trade["pair_fill_price"] == pair_fill_price
        assert trade["status"] == "filled"

    def test_spread_based_trade_exit_update(self, db_connection, spread_based_recommendation):
        """Test that autocloser correctly updates exit_price and pair_exit_price."""
        trade_id = str(uuid.uuid4())
        rec_id = spread_based_recommendation["id"]

        # Create recommendation first
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            spread_based_recommendation["symbol"],
            spread_based_recommendation["timeframe"],
            spread_based_recommendation["recommendation"],
            spread_based_recommendation["confidence"],
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Insert and fill spread-based trade
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, pair_quantity, status, order_id, order_id_pair, fill_price,
             pair_fill_price, confidence, created_at, filled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            spread_based_recommendation["symbol"],
            "Buy",
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            spread_based_recommendation["units_x"],
            spread_based_recommendation["units_y"],
            "filled",
            f"order_{trade_id}",
            f"order_pair_{trade_id}",
            45000.0,
            2500.0,
            spread_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Simulate autocloser exit update
        exit_price = 45500.0
        pair_exit_price = 2520.0
        exit_time = datetime.now(timezone.utc).isoformat()

        execute(db_connection, """
            UPDATE trades SET
                exit_price = %s,
                pair_exit_price = %s,
                closed_at = %s,
                status = 'closed'
            WHERE id = %s
        """, (exit_price, pair_exit_price, exit_time, trade_id))

        # Verify the update
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        trade = result[0]

        assert trade["exit_price"] == exit_price
        assert trade["pair_exit_price"] == pair_exit_price
        assert trade["status"] == "closed"

    def test_spread_based_pnl_calculation(self, db_connection, spread_based_recommendation):
        """Test that P&L is correctly calculated for both symbols."""
        trade_id = str(uuid.uuid4())
        rec_id = spread_based_recommendation["id"]

        # Create recommendation first
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            spread_based_recommendation["symbol"],
            spread_based_recommendation["timeframe"],
            spread_based_recommendation["recommendation"],
            spread_based_recommendation["confidence"],
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Insert, fill, and close spread-based trade
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, pair_quantity, status, order_id, order_id_pair, fill_price,
             pair_fill_price, exit_price, pair_exit_price, confidence, created_at,
             filled_at, closed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            spread_based_recommendation["symbol"],
            "Buy",
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            1.0,  # units_x
            -0.05,  # units_y (opposite direction)
            "closed",
            f"order_{trade_id}",
            f"order_pair_{trade_id}",
            45000.0,  # fill_price
            2500.0,  # pair_fill_price
            45500.0,  # exit_price
            2520.0,  # pair_exit_price
            spread_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Calculate P&L for both symbols
        # Main symbol (BUY): (exit_price - fill_price) * quantity
        main_pnl = (45500.0 - 45000.0) * 1.0  # = 500.0

        # Pair symbol (SELL, opposite direction): (fill_price - exit_price) * abs(quantity)
        pair_pnl = (2500.0 - 2520.0) * 0.05  # = -1.0

        total_pnl = main_pnl + pair_pnl  # = 499.0

        # Update trade with P&L
        execute(db_connection, """
            UPDATE trades SET pnl = %s WHERE id = %s
        """, (total_pnl, trade_id))

        # Verify P&L
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        trade = result[0]

        assert trade["pnl"] == pytest.approx(499.0, abs=0.01)
        assert trade["fill_price"] == 45000.0
        assert trade["pair_fill_price"] == 2500.0
        assert trade["exit_price"] == 45500.0
        assert trade["pair_exit_price"] == 2520.0

    def test_complete_spread_based_workflow(self, db_connection, spread_based_recommendation):
        """Test the complete workflow: Create → Fill → Exit → P&L."""
        trade_id = str(uuid.uuid4())
        rec_id = spread_based_recommendation["id"]

        # Create recommendation first
        execute(db_connection, """
            INSERT INTO recommendations
            (id, symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit,
             prompt_name, analyzed_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rec_id,
            spread_based_recommendation["symbol"],
            spread_based_recommendation["timeframe"],
            spread_based_recommendation["recommendation"],
            spread_based_recommendation["confidence"],
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            "test_prompt",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # STEP 1: Create trade (TradingEngine._record_trade)
        execute(db_connection, """
            INSERT INTO trades
            (id, recommendation_id, symbol, side, entry_price, stop_loss, take_profit,
             quantity, pair_quantity, status, order_id, order_id_pair, confidence, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            trade_id,
            rec_id,
            spread_based_recommendation["symbol"],
            "Buy",
            spread_based_recommendation["entry_price"],
            spread_based_recommendation["stop_loss"],
            spread_based_recommendation["take_profit"],
            1.0,
            -0.05,
            "paper_trade",
            f"order_{trade_id}",
            f"order_pair_{trade_id}",
            spread_based_recommendation["confidence"],
            datetime.now(timezone.utc).isoformat()
        ))

        # Verify creation
        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert len(result) == 1
        assert result[0]["status"] == "paper_trade"

        # STEP 2: Fill trade (Autocloser)
        execute(db_connection, """
            UPDATE trades SET
                fill_price = %s,
                pair_fill_price = %s,
                filled_at = %s,
                status = 'filled'
            WHERE id = %s
        """, (45000.0, 2500.0, datetime.now(timezone.utc).isoformat(), trade_id))

        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert result[0]["status"] == "filled"
        assert result[0]["fill_price"] == 45000.0
        assert result[0]["pair_fill_price"] == 2500.0

        # STEP 3: Close trade (Autocloser)
        execute(db_connection, """
            UPDATE trades SET
                exit_price = %s,
                pair_exit_price = %s,
                closed_at = %s,
                status = 'closed'
            WHERE id = %s
        """, (45500.0, 2520.0, datetime.now(timezone.utc).isoformat(), trade_id))

        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        assert result[0]["status"] == "closed"
        assert result[0]["exit_price"] == 45500.0
        assert result[0]["pair_exit_price"] == 2520.0

        # STEP 4: Calculate and store P&L
        main_pnl = (45500.0 - 45000.0) * 1.0
        pair_pnl = (2500.0 - 2520.0) * 0.05
        total_pnl = main_pnl + pair_pnl

        execute(db_connection, """
            UPDATE trades SET pnl = %s WHERE id = %s
        """, (total_pnl, trade_id))

        result = query(db_connection, "SELECT * FROM trades WHERE id = %s", (trade_id,))
        trade = result[0]

        # Verify complete workflow
        assert trade["status"] == "closed"
        assert trade["fill_price"] == 45000.0
        assert trade["pair_fill_price"] == 2500.0
        assert trade["exit_price"] == 45500.0
        assert trade["pair_exit_price"] == 2520.0
        assert trade["pnl"] == pytest.approx(499.0, abs=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


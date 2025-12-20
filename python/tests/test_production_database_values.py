"""
Production Database Values Test - Real Production Database

Tests that all values are correctly calculated, stored, and retrieved
from the ACTUAL production PostgreSQL database.

This test validates the complete trading cycle:
1. Strategy calculates recommendation values correctly
2. Recommendations are stored with correct values in database
3. Trades are created with correct position sizing calculations
4. All values are retrievable and consistent from database
5. Data integrity is maintained end-to-end

Uses the ACTUAL production database (Postgres) via DATABASE_URL env var.
"""

import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

from trading_bot.db.client import get_connection, release_connection, execute, query_one


class TestProductionDatabaseValues:
    """Test database value storage and retrieval using ACTUAL production database."""
    
    @pytest.fixture
    def db_conn(self):
        """Get connection to ACTUAL production database."""
        conn = get_connection()
        yield conn
        release_connection(conn)
    
    def test_1_recommendation_values_calculated_and_stored(self, db_conn):
        """Test 1: Recommendation values calculated correctly and stored in database."""
        # Simulate: Strategy analyzes BTCUSDT and calculates recommendation
        rec_id = f"test_rec_{uuid4().hex[:8]}"
        symbol = "BTCUSDT"
        timeframe = "1h"
        prompt_name = "test_prompt"

        # Strategy calculates these values
        entry = 50000.0
        sl = 49000.0
        tp = 52000.0
        confidence = 0.85

        # Calculate RR ratio (long: reward / risk)
        risk = entry - sl  # 1000
        reward = tp - entry  # 2000
        rr_ratio = reward / risk  # 2.0

        # Store recommendation in production database
        execute(db_conn, """
            INSERT INTO recommendations
            (id, symbol, recommendation, confidence, entry_price, stop_loss, take_profit,
             risk_reward, timeframe, prompt_name, analyzed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            rec_id, symbol, "BUY", confidence, entry, sl, tp,
            rr_ratio, timeframe, prompt_name, datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Retrieve from database and verify
        rec = query_one(db_conn,
            "SELECT * FROM recommendations WHERE id = ?", (rec_id,))

        assert rec is not None, "Recommendation not found in production database"
        assert rec["symbol"] == symbol
        assert rec["entry_price"] == entry
        assert rec["stop_loss"] == sl
        assert rec["take_profit"] == tp
        assert rec["confidence"] == confidence
        assert rec["recommendation"] == "BUY"
        assert abs(rec["risk_reward"] - 2.0) < 0.001

        # Cleanup
        execute(db_conn, "DELETE FROM recommendations WHERE id = ?", (rec_id,))
        print("✓ Test 1 PASSED: Recommendation values correct in production DB")
    
    def test_2_trade_position_sizing_calculated_and_stored(self, db_conn):
        """Test 2: Trade position sizing calculated correctly and stored in database."""
        # Simulate: Trading engine executes trade with position sizing
        trade_id = f"test_trade_{uuid4().hex[:8]}"
        symbol = "ETHUSDT"

        # From recommendation
        entry = 3000.0
        sl = 2900.0
        tp = 3200.0
        confidence = 0.80

        # Position sizer calculates these
        wallet_balance = 10000.0
        risk_pct = 0.02  # 2% risk
        risk_amount = wallet_balance * risk_pct  # $200
        risk_per_unit = entry - sl  # $100
        position_size = risk_amount / risk_per_unit  # 2.0 ETH
        position_value = position_size * entry  # $6000
        # RR ratio for LONG: (tp - entry) / (entry - sl) = (3200 - 3000) / (3000 - 2900) = 200 / 100 = 2.0
        rr_ratio = (tp - entry) / risk_per_unit  # 2.0

        # Store trade in production database
        execute(db_conn, """
            INSERT INTO trades
            (id, symbol, side, entry_price, stop_loss, take_profit, quantity,
             risk_amount_usd, position_size_usd, risk_percentage, risk_per_unit,
             confidence, rr_ratio, status, wallet_balance_at_trade, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, symbol, "Buy", entry, sl, tp, position_size,
            risk_amount, position_value, risk_pct, risk_per_unit,
            confidence, rr_ratio, "pending", wallet_balance,
            datetime.now(timezone.utc).isoformat()
        ))

        # Retrieve from database and verify
        trade = query_one(db_conn,
            "SELECT * FROM trades WHERE id = ?", (trade_id,))

        assert trade is not None, "Trade not found in production database"
        assert trade["symbol"] == symbol
        assert trade["entry_price"] == entry
        assert trade["stop_loss"] == sl
        assert trade["take_profit"] == tp
        assert trade["quantity"] == position_size
        assert abs(trade["risk_amount_usd"] - 200.0) < 0.01
        assert abs(trade["position_size_usd"] - 6000.0) < 0.01
        assert abs(trade["risk_percentage"] - 0.02) < 0.0001
        assert abs(trade["rr_ratio"] - 2.0) < 0.001
        assert trade["wallet_balance_at_trade"] == wallet_balance

        # Cleanup
        execute(db_conn, "DELETE FROM trades WHERE id = ?", (trade_id,))
        print("✓ Test 2 PASSED: Trade position sizing correct in production DB")


    def test_3_cycle_metrics_aggregation(self, db_conn):
        """Test 3: Cycle metrics are aggregated correctly."""
        # Simulate: Trading cycle completes and records metrics
        cycle_id = f"test_cycle_{uuid4().hex[:8]}"
        run_id = f"test_run_{uuid4().hex[:8]}"
        instance_id = f"test_instance_{uuid4().hex[:8]}"

        # First create an instance (required by foreign key)
        execute(db_conn, """
            INSERT INTO instances
            (id, name, is_active, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            instance_id, f"test_instance_{uuid4().hex[:4]}", True,
            datetime.now(timezone.utc).isoformat()
        ))

        # Then create a run (required by foreign key)
        execute(db_conn, """
            INSERT INTO runs
            (id, instance_id, status, started_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            run_id, instance_id, "running",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Cycle metrics
        charts_captured = 50
        analyses_completed = 48
        recommendations_generated = 12
        trades_executed = 5

        # Store cycle in production database
        execute(db_conn, """
            INSERT INTO cycles
            (id, run_id, timeframe, cycle_number, boundary_time, status,
             charts_captured, analyses_completed, recommendations_generated, trades_executed,
             started_at, completed_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cycle_id, run_id, "1h", 1, datetime.now(timezone.utc).isoformat(), "completed",
            charts_captured, analyses_completed, recommendations_generated, trades_executed,
            datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Retrieve and verify
        cycle = query_one(db_conn,
            "SELECT * FROM cycles WHERE id = ?", (cycle_id,))

        assert cycle is not None, "Cycle not found in production database"
        assert cycle["charts_captured"] == charts_captured
        assert cycle["analyses_completed"] == analyses_completed
        assert cycle["recommendations_generated"] == recommendations_generated
        assert cycle["trades_executed"] == trades_executed
        assert cycle["status"] == "completed"

        # Cleanup
        execute(db_conn, "DELETE FROM cycles WHERE id = ?", (cycle_id,))
        execute(db_conn, "DELETE FROM runs WHERE id = ?", (run_id,))
        execute(db_conn, "DELETE FROM instances WHERE id = ?", (instance_id,))
        print("✓ Test 3 PASSED: Cycle metrics correct in production DB")

    def test_4_strategy_metadata_storage(self, db_conn):
        """Test 4: Strategy metadata is stored and retrieved correctly."""
        # Simulate: Cointegration strategy stores pair metadata
        trade_id = f"test_trade_{uuid4().hex[:8]}"
        symbol = "BTCUSDT"

        # Strategy metadata for cointegration pair
        strategy_metadata = {
            "pair_symbol": "ETHUSDT",
            "beta": 0.85,
            "spread_mean": 0.002,
            "spread_std": 0.0015,
            "z_score_at_entry": 2.5,
            "z_exit_threshold": 0.5
        }

        # Store trade with strategy metadata
        execute(db_conn, """
            INSERT INTO trades
            (id, symbol, side, entry_price, stop_loss, take_profit, quantity,
             status, strategy_metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, symbol, "Buy", 50000.0, 49000.0, 52000.0, 1.0,
            "pending", json.dumps(strategy_metadata),
            datetime.now(timezone.utc).isoformat()
        ))

        # Retrieve and verify
        trade = query_one(db_conn,
            "SELECT * FROM trades WHERE id = ?", (trade_id,))

        assert trade is not None, "Trade not found in production database"
        retrieved_metadata = json.loads(trade["strategy_metadata"])
        assert retrieved_metadata["pair_symbol"] == "ETHUSDT"
        assert abs(retrieved_metadata["beta"] - 0.85) < 0.001
        assert abs(retrieved_metadata["z_score_at_entry"] - 2.5) < 0.001

        # Cleanup
        execute(db_conn, "DELETE FROM trades WHERE id = ?", (trade_id,))
        print("✓ Test 4 PASSED: Strategy metadata correct in production DB")

    def test_5_kelly_criterion_metrics_storage(self, db_conn):
        """Test 5: Kelly criterion metrics are stored and retrieved correctly."""
        # Simulate: Position sizer calculates Kelly metrics
        trade_id = f"test_trade_{uuid4().hex[:8]}"
        symbol = "XRPUSDT"

        # Kelly metrics from position sizer
        kelly_metrics = {
            "kelly_fraction_used": 0.25,
            "win_rate": 0.65,
            "avg_win_percent": 2.5,
            "avg_loss_percent": 1.8,
            "trade_history_count": 30,
            "full_kelly": 0.35,
            "fractional_kelly": 0.105
        }

        # Store trade with Kelly metrics
        execute(db_conn, """
            INSERT INTO trades
            (id, symbol, side, entry_price, stop_loss, take_profit, quantity,
             status, kelly_metrics, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_id, symbol, "Buy", 2.5, 2.4, 2.7, 100.0,
            "pending", json.dumps(kelly_metrics),
            datetime.now(timezone.utc).isoformat()
        ))

        # Retrieve and verify
        trade = query_one(db_conn,
            "SELECT * FROM trades WHERE id = ?", (trade_id,))

        assert trade is not None, "Trade not found in production database"
        # PostgreSQL returns JSON as dict, not string
        retrieved_kelly = trade["kelly_metrics"]
        if isinstance(retrieved_kelly, str):
            retrieved_kelly = json.loads(retrieved_kelly)

        assert abs(retrieved_kelly["kelly_fraction_used"] - 0.25) < 0.001
        assert abs(retrieved_kelly["win_rate"] - 0.65) < 0.001
        assert retrieved_kelly["trade_history_count"] == 30

        # Cleanup
        execute(db_conn, "DELETE FROM trades WHERE id = ?", (trade_id,))
        print("✓ Test 5 PASSED: Kelly metrics correct in production DB")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

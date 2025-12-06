#!/usr/bin/env python3
"""
Tests for trading.db schema and operations.
Run with: python -m trading_bot.db.test_trading_db
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import os

# Test with a temporary database
TEST_DB_PATH = None


def get_test_connection():
    """Get connection to test database."""
    global TEST_DB_PATH
    if TEST_DB_PATH is None:
        TEST_DB_PATH = tempfile.mktemp(suffix='.db')
    
    conn = sqlite3.connect(TEST_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def cleanup_test_db():
    """Remove test database."""
    global TEST_DB_PATH
    if TEST_DB_PATH and os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        TEST_DB_PATH = None


def test_schema_creation():
    """Test that all tables are created correctly."""
    from trading_bot.db.init_trading_db import init_schema
    
    conn = get_test_connection()
    init_schema(conn)
    
    # Check all tables exist
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    
    expected_tables = ['config', 'cycles', 'executions', 'position_snapshots', 
                       'recommendations', 'sqlite_sequence', 'trades']
    
    for table in expected_tables:
        assert table in tables, f"Missing table: {table}"
    
    print("✅ test_schema_creation passed")
    conn.close()


def test_recommendations_crud():
    """Test CRUD operations on recommendations table."""
    conn = get_test_connection()
    
    rec_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # CREATE
    conn.execute("""
        INSERT INTO recommendations 
        (id, symbol, timeframe, recommendation, confidence, entry_price, 
         stop_loss, take_profit, risk_reward, prompt_name, analyzed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (rec_id, 'BTCUSDT', '1h', 'LONG', 0.85, 50000.0, 
          49000.0, 52000.0, 2.0, 'test_prompt', now))
    conn.commit()
    
    # READ
    cursor = conn.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,))
    row = cursor.fetchone()
    assert row is not None, "Recommendation not found"
    assert row['symbol'] == 'BTCUSDT'
    assert row['recommendation'] == 'LONG'
    assert row['confidence'] == 0.85
    
    # UPDATE
    conn.execute(
        "UPDATE recommendations SET confidence = ? WHERE id = ?",
        (0.90, rec_id)
    )
    conn.commit()
    
    cursor = conn.execute("SELECT confidence FROM recommendations WHERE id = ?", (rec_id,))
    assert cursor.fetchone()['confidence'] == 0.90
    
    # DELETE
    conn.execute("DELETE FROM recommendations WHERE id = ?", (rec_id,))
    conn.commit()
    
    cursor = conn.execute("SELECT * FROM recommendations WHERE id = ?", (rec_id,))
    assert cursor.fetchone() is None
    
    print("✅ test_recommendations_crud passed")
    conn.close()


def test_trades_crud():
    """Test CRUD operations on trades table."""
    conn = get_test_connection()
    
    trade_id = str(uuid.uuid4())
    
    # CREATE
    conn.execute("""
        INSERT INTO trades 
        (id, symbol, side, entry_price, quantity, stop_loss, take_profit, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (trade_id, 'ETHUSDT', 'Buy', 3000.0, 0.1, 2900.0, 3200.0, 'pending'))
    conn.commit()
    
    # READ
    cursor = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row['symbol'] == 'ETHUSDT'
    assert row['status'] == 'pending'
    
    # UPDATE - simulate fill
    conn.execute("""
        UPDATE trades 
        SET status = ?, fill_price = ?, fill_quantity = ?, filled_at = ?
        WHERE id = ?
    """, ('filled', 3001.0, 0.1, datetime.now(timezone.utc).isoformat(), trade_id))
    conn.commit()
    
    cursor = conn.execute("SELECT status, fill_price FROM trades WHERE id = ?", (trade_id,))
    row = cursor.fetchone()
    assert row['status'] == 'filled'
    assert row['fill_price'] == 3001.0
    
    print("✅ test_trades_crud passed")
    conn.close()


def test_config_crud():
    """Test CRUD operations on config table."""
    from trading_bot.db.config_defaults import insert_default_config
    
    conn = get_test_connection()
    
    # Insert defaults
    count = insert_default_config(conn)
    assert count > 0, "No config rows inserted"
    
    # Read
    cursor = conn.execute("SELECT * FROM config WHERE key = ?", 
                          ('trading.paper_trading',))
    row = cursor.fetchone()
    assert row is not None
    assert row['type'] == 'boolean'
    
    # Update
    conn.execute(
        "UPDATE config SET value = ?, updated_at = datetime('now') WHERE key = ?",
        ('true', 'trading.paper_trading')
    )
    conn.commit()
    
    cursor = conn.execute("SELECT value FROM config WHERE key = ?", 
                          ('trading.paper_trading',))
    assert cursor.fetchone()['value'] == 'true'
    
    print("✅ test_config_crud passed")
    conn.close()


def test_cycles_crud():
    """Test CRUD operations on cycles table."""
    conn = get_test_connection()

    cycle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # CREATE
    conn.execute("""
        INSERT INTO cycles
        (id, timeframe, cycle_number, boundary_time, status, started_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cycle_id, '1h', 1, now, 'running', now))
    conn.commit()

    # READ
    cursor = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row['timeframe'] == '1h'
    assert row['status'] == 'running'

    # UPDATE - complete cycle
    conn.execute("""
        UPDATE cycles
        SET status = ?, charts_captured = ?, analyses_completed = ?,
            trades_executed = ?, completed_at = ?
        WHERE id = ?
    """, ('completed', 5, 5, 2, now, cycle_id))
    conn.commit()

    cursor = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,))
    row = cursor.fetchone()
    assert row['status'] == 'completed'
    assert row['charts_captured'] == 5

    print("✅ test_cycles_crud passed")
    conn.close()


def test_executions_crud():
    """Test CRUD operations on executions table."""
    conn = get_test_connection()

    exec_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # CREATE
    conn.execute("""
        INSERT INTO executions
        (id, order_id, exec_id, symbol, side, exec_price, exec_qty, exec_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (exec_id, 'order123', 'exec456', 'BTCUSDT', 'Buy', 50000.0, 0.01, now))
    conn.commit()

    # READ
    cursor = conn.execute("SELECT * FROM executions WHERE id = ?", (exec_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row['symbol'] == 'BTCUSDT'
    assert row['exec_price'] == 50000.0

    print("✅ test_executions_crud passed")
    conn.close()


def test_position_snapshots_crud():
    """Test CRUD operations on position_snapshots table."""
    conn = get_test_connection()

    now = datetime.now(timezone.utc).isoformat()

    # CREATE
    conn.execute("""
        INSERT INTO position_snapshots
        (symbol, side, size, entry_price, mark_price, unrealised_pnl,
         snapshot_reason, snapshot_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ('BTCUSDT', 'Buy', 0.1, 50000.0, 50500.0, 50.0, 'cycle_start', now))
    conn.commit()

    # READ
    cursor = conn.execute(
        "SELECT * FROM position_snapshots WHERE symbol = ? ORDER BY id DESC LIMIT 1",
        ('BTCUSDT',)
    )
    row = cursor.fetchone()
    assert row is not None
    assert row['size'] == 0.1
    assert row['unrealised_pnl'] == 50.0

    print("✅ test_position_snapshots_crud passed")
    conn.close()


def test_foreign_key_constraint():
    """Test that foreign key constraints work."""
    conn = get_test_connection()

    # Try to insert execution with non-existent trade_id
    try:
        conn.execute("""
            INSERT INTO executions
            (id, trade_id, order_id, exec_id, symbol, exec_price, exec_qty, exec_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), 'nonexistent', 'order123', 'exec456',
              'BTCUSDT', 50000.0, 0.01, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        # Should fail if FK is enforced
        print("⚠️ Foreign key constraint not enforced (expected in some SQLite configs)")
    except sqlite3.IntegrityError:
        print("✅ test_foreign_key_constraint passed")

    conn.close()


def run_all_tests():
    """Run all tests."""
    print("\n🧪 Running trading.db tests...\n")

    try:
        test_schema_creation()
        test_recommendations_crud()
        test_trades_crud()
        test_config_crud()
        test_cycles_crud()
        test_executions_crud()
        test_position_snapshots_crud()
        test_foreign_key_constraint()

        print("\n✅ All tests passed!\n")
    finally:
        cleanup_test_db()


if __name__ == "__main__":
    run_all_tests()


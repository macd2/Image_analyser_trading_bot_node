#!/usr/bin/env python3
"""
Default configuration values for the trading bot dashboard.
These are inserted into the config table and can be modified via the dashboard.
"""

import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

# Default RR tightening steps
DEFAULT_RR_TIGHTENING_STEPS = {
    "2R": {"threshold": 2.0, "sl_position": 1.2},
    "2.5R": {"threshold": 2.5, "sl_position": 2.0},
    "3R": {"threshold": 3.0, "sl_position": 2.5}
}

# All dashboard-configurable settings
# Format: (key, value, type, category, description)
DEFAULT_CONFIG: List[Tuple[str, Any, str, str, str]] = [
    # Trading Core (8 settings)
    ("trading.paper_trading", False, "boolean", "trading",
     "Enable paper trading mode (no real trades)"),
    ("trading.auto_approve_trades", True, "boolean", "trading",
     "Skip Telegram confirmation for trades"),
    ("trading.min_confidence_threshold", 0.75, "number", "trading",
     "Minimum confidence score required for trades (0.0-1.0)"),
    ("trading.min_rr", 1.7, "number", "trading",
     "Minimum risk-reward ratio required for trades"),
    ("trading.risk_percentage", 0.01, "number", "trading",
     "Risk per trade as decimal (0.01 = 1% of account)"),
    ("trading.max_loss_usd", 10.0, "number", "trading",
     "Maximum USD risk per trade"),
    ("trading.leverage", 2, "number", "trading",
     "Trading leverage multiplier"),
    ("trading.max_concurrent_trades", 3, "number", "trading",
     "Maximum number of concurrent positions/orders"),
    ("trading.sl_adjustment_enabled", False, "boolean", "trading",
     "Enable pre-execution stop-loss adjustment"),
    ("trading.sl_adjustment_long_pct", 1.5, "number", "trading",
     "SL widening percentage for LONG trades (e.g., 1.5 = 1.5% wider)"),
    ("trading.sl_adjustment_short_pct", 1.5, "number", "trading",
     "SL widening percentage for SHORT trades (e.g., 1.5 = 1.5% wider)"),

    # Tightening (3 settings)
    ("trading.enable_position_tightening", True, "boolean", "tightening",
     "Enable stop-loss tightening based on profit"),
    ("trading.enable_sl_tightening", False, "boolean", "tightening",
     "Enable RR-based stop-loss tightening"),
    ("trading.rr_tightening_steps", DEFAULT_RR_TIGHTENING_STEPS, "json", "tightening",
     "RR levels and SL positions for tightening"),

    # Position Sizing (5 settings)
    ("trading.use_enhanced_position_sizing", True, "boolean", "sizing",
     "Use confidence/volatility weighting for position sizing"),
    ("trading.min_position_value_usd", 50.0, "number", "sizing",
     "Minimum position size in USD"),
    ("trading.use_kelly_criterion", False, "boolean", "sizing",
     "Use Kelly Criterion for dynamic position sizing based on trade history"),
    ("trading.kelly_fraction", 0.3, "number", "sizing",
     "Fractional Kelly multiplier (0.3 = 30% of full Kelly, safer than 1.0)"),
    ("trading.kelly_window", 30, "number", "sizing",
     "Number of recent trades to analyze for Kelly Criterion calculation"),

    # Order Replacement (2 settings)
    ("trading.enable_intelligent_replacement", True, "boolean", "replacement",
     "Enable intelligent order replacement based on score"),
    ("trading.min_score_improvement_threshold", 0.15, "number", "replacement",
     "Minimum score improvement required to replace an order"),

    # Exchange (3 settings)
    ("bybit.use_testnet", False, "boolean", "exchange",
     "Use Bybit testnet instead of mainnet"),
    ("bybit.recv_window", 30000, "number", "exchange",
     "API receive window in milliseconds"),
    ("bybit.max_retries", 5, "number", "exchange",
     "Maximum API retry attempts"),

    # AI (2 settings)
    ("openai.model", "gpt-4.1-mini", "string", "ai",
     "OpenAI model for chart analysis"),
    ("openai.assistant_id", "asst_m11ds7XhdYfN7voO0pRvgbul", "string", "ai",
     "OpenAI Assistant ID for analysis (empty = use direct API)"),

    # TradingView (2 settings)
    ("tradingview.enabled", True, "boolean", "tradingview",
     "Enable TradingView chart capture"),
    ("tradingview.target_chart", "https://www.tradingview.com/chart/iXrxoaRu/", "string", "tradingview",
     "Target chart URL for TradingView navigation"),
]


def get_default_config_rows() -> List[Tuple[str, str, str, str, str]]:
    """
    Get default config as rows ready for database insertion.
    Converts values to strings and JSON as appropriate.
    """
    rows = []
    for key, value, type_, category, description in DEFAULT_CONFIG:
        if type_ == "json":
            str_value = json.dumps(value)
        elif type_ == "boolean":
            str_value = "true" if value else "false"
        else:
            str_value = str(value)
        rows.append((key, str_value, type_, category, description))
    return rows


def insert_default_config(conn) -> int:
    """
    Insert default config values into the database.
    Uses INSERT OR IGNORE to avoid overwriting existing values.

    Returns the number of rows inserted.
    """
    from trading_bot.db.client import execute as db_execute

    rows = get_default_config_rows()
    total_inserted = 0

    # Execute each insert individually since executemany doesn't work with placeholder conversion
    for row in rows:
        count = db_execute(
            conn,
            """
            INSERT OR IGNORE INTO config (key, value, type, category, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            row
        )
        total_inserted += count

    conn.commit()
    return total_inserted


def reset_config_to_defaults(conn) -> int:
    """
    Reset all config values to defaults.
    This REPLACES existing values.
    """
    from trading_bot.db.client import execute as db_execute

    rows = get_default_config_rows()
    total_replaced = 0

    # Execute each insert individually since executemany doesn't work with placeholder conversion
    for row in rows:
        count = db_execute(
            conn,
            """
            INSERT OR REPLACE INTO config (key, value, type, category, description, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            row
        )
        total_replaced += count

    conn.commit()
    return total_replaced


if __name__ == "__main__":
    from trading_bot.db import get_connection, release_connection, query

    print("Inserting default config values...")
    conn = get_connection()
    count = insert_default_config(conn)
    print(f"✅ Inserted {count} config rows")

    # Show all config using centralized query function
    rows = query(conn, "SELECT key, value, category FROM config ORDER BY category, key", ())
    print("\n📊 Current config:")
    for row in rows:
        print(f"  [{row['category']}] {row['key']} = {row['value']}")

    release_connection(conn)

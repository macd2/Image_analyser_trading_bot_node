"""Database module for trading bot."""

# Import from centralized client (handles SQLite/PostgreSQL switching)
from trading_bot.db.client import (
    get_connection,
    get_db_path,
    execute,
    query,
    query_one,
    convert_placeholders,
    DB_TYPE,
)

from trading_bot.db.init_trading_db import (
    init_database,
    init_schema,
)
from trading_bot.db.config_defaults import (
    insert_default_config,
    reset_config_to_defaults,
    get_default_config_rows,
    DEFAULT_CONFIG,
)

__all__ = [
    # Centralized database client
    "get_connection",
    "get_db_path",
    "execute",
    "query",
    "query_one",
    "convert_placeholders",
    "DB_TYPE",
    # Schema initialization
    "init_database",
    "init_schema",
    # Config management
    "insert_default_config",
    "reset_config_to_defaults",
    "get_default_config_rows",
    "DEFAULT_CONFIG",
]


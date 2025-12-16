"""Data agent for storing and retrieving analysis results (SQLite/PostgreSQL)."""
import gc
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from trading_bot.db.client import (
    get_connection as get_db_connection,
    release_connection,
    get_table_columns,
    add_column_if_missing,
    get_timestamp_type,
    normalize_sql,
    query_one,
    query,
    execute as db_execute,
    convert_placeholders
)


class DataAgent:
    """Manages persistent storage of analysis results."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Use default database path - consolidated to data/ folder
            # The standard path is: data/trading.db (from prototype root)
            module_dir = Path(__file__).parent.parent.parent.parent  # prototype directory
            db_path = str(module_dir / "data" / "trading.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection pooling
        self._connection_pool = []
        self._pool_lock = threading.Lock()
        self._max_pool_size = 5
        self._connection_timeout = 10.0
        
        self.init_database()
    
    def _get_pooled_connection(self):
        """Get a connection using centralized database client."""
        return get_db_connection()

    def _return_connection(self, conn: Union[sqlite3.Connection, Any]):
        """Return a connection to the pool (supports both SQLite and PostgreSQL)."""
        with self._pool_lock:
            if len(self._connection_pool) < self._max_pool_size:
                self._connection_pool.append(conn)
            else:
                release_connection(conn)
    
    def cleanup_connection_pool(self):
        """Clean up all connections in the pool."""
        with self._pool_lock:
            for conn in self._connection_pool:
                try:
                    release_connection(conn)
                except:
                    pass
            self._connection_pool.clear()
    
    def _to_float_or_none(self, value: Any) -> Optional[float]:
        """Safely convert a value to a float or return None."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def get_connection(self):
        """Get database connection using centralized client."""
        return get_db_connection()

    def _ensure_trades_columns_exist(self, conn, cursor):
        """
        Ensure all required columns exist in trades table.
        This handles schema migrations for existing databases.
        Called during database initialization to auto-migrate schema.
        """
        # Get current columns using centralized helper (works with SQLite and PostgreSQL)
        existing_columns = get_table_columns(conn, "trades")

        # Define all required columns with their types and defaults
        # Use centralized timestamp type (TIMESTAMP for PostgreSQL, DATETIME for SQLite)
        timestamp_type = get_timestamp_type()

        required_columns = [
            ('id', 'TEXT', None),
            ('recommendation_id', 'TEXT', None),
            ('symbol', 'TEXT', None),
            ('side', 'TEXT', None),
            ('quantity', 'REAL', None),
            ('entry_price', 'REAL', None),
            ('take_profit', 'REAL', None),
            ('stop_loss', 'REAL', None),
            ('order_id', 'TEXT', None),
            ('orderLinkId', 'TEXT', None),
            ('pnl', 'REAL', '0'),
            ('status', 'TEXT', "'open'"),
            ('state', 'TEXT', "'trade'"),
            ('avg_exit_price', 'REAL', None),
            ('closed_size', 'REAL', None),
            ('created_at', timestamp_type, 'CURRENT_TIMESTAMP'),
            ('updated_at', timestamp_type, 'CURRENT_TIMESTAMP'),
            ('placed_by', 'TEXT', "'BOT'"),
            ('alteration_details', 'TEXT', None),
            ('prompt_name', 'TEXT', None),
            ('timeframe', 'TEXT', None),
            ('confidence', 'REAL', None),
            ('risk_reward_ratio', 'REAL', None),
            ('order_type', 'TEXT', "'Limit'"),
            ('last_tightened_milestone', 'REAL', None),  # For ADX stop tightening
        ]

        # Add missing columns
        columns_added = []
        for col_name, col_type, default_value in required_columns:
            if col_name not in existing_columns:
                try:
                    if default_value:
                        sql = f"ALTER TABLE trades ADD COLUMN {col_name} {col_type} DEFAULT {default_value}"
                    else:
                        sql = f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}"
                    cursor.execute(sql)
                    columns_added.append(col_name)
                except Exception as e:
                    print(f"⚠️  Warning: Could not add column {col_name}: {e}")
                    # Rollback handled by add_column_if_missing() in centralized layer
                    conn.rollback()

        if columns_added:
            print(f"✅ Auto-migration: Added {len(columns_added)} missing columns to trades table: {', '.join(columns_added)}")

        return columns_added
    
    def init_database(self):
        """Initialize database with required tables and optimized indexes (SQLite/PostgreSQL)."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Create analysis results table with UUID
            # Use normalize_sql() to handle DATETIME -> TIMESTAMP conversion
            cursor.execute(normalize_sql('''
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    summary TEXT,
                    evidence TEXT,
                    support_level REAL,
                    resistance_level REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    direction TEXT,
                    rr REAL,
                    risk_factors TEXT,  -- JSON string
                    analysis_data TEXT,  -- Full JSON analysis
                    analysis_prompt TEXT,  -- Raw prompt sent to AI
                    timestamp DATETIME,
                    image_path TEXT,
                    market_condition TEXT,
                    market_direction TEXT
                )
            '''))
            
            # Migration: Add new columns if they don't exist using centralized helper
            existing_columns = get_table_columns(conn, "analysis_results")

            # Add prompt_id column if missing
            if 'prompt_id' not in existing_columns:
                cursor.execute('ALTER TABLE analysis_results ADD COLUMN prompt_id TEXT')
                print("✅ Added 'prompt_id' column to analysis_results table")

            # Add market_data column if missing
            if 'market_data' not in existing_columns:
                cursor.execute('ALTER TABLE analysis_results ADD COLUMN market_data TEXT')
                print("✅ Added 'market_data' column to analysis_results table")

            # Create optimized indexes for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_symbol_timeframe
                ON analysis_results(symbol, timeframe)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON analysis_results(timestamp)
            ''')

            # Additional optimized indexes for frequently queried columns
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_symbol_timeframe_timestamp
                ON analysis_results(symbol, timeframe, timestamp)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_recommendation_confidence
                ON analysis_results(recommendation, confidence)
            ''')

            # Index for prompt_id for performance analysis queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_prompt_id
                ON analysis_results(prompt_id)
            ''')

            # Create latest recommendations table
            cursor.execute(normalize_sql('''
                CREATE TABLE IF NOT EXISTS latest_recommendations (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    summary TEXT,
                    support_level REAL,
                    resistance_level REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    direction TEXT,
                    rr REAL,
                    risk_factors TEXT,  -- JSON string
                    analysis_data TEXT,  -- Full JSON analysis
                    timestamp DATETIME,
                    image_path TEXT,
                    market_condition TEXT,
                    market_direction TEXT
                )
            '''))

            # Migration: Add new columns to latest_recommendations if they don't exist
            existing_lr_columns = get_table_columns(conn, "latest_recommendations")

            # Add prompt_id column if missing
            if 'prompt_id' not in existing_lr_columns:
                cursor.execute('ALTER TABLE latest_recommendations ADD COLUMN prompt_id TEXT')
                print("✅ Added 'prompt_id' column to latest_recommendations table")

            # Add market_data column if missing
            if 'market_data' not in existing_lr_columns:
                cursor.execute('ALTER TABLE latest_recommendations ADD COLUMN market_data TEXT')
                print("✅ Added 'market_data' column to latest_recommendations table")

            # Create trades table for position management with comprehensive metadata
            cursor.execute(normalize_sql('''
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    recommendation_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    order_id TEXT UNIQUE,  -- Add unique constraint
                    orderLinkId TEXT, -- New column for Bybit's orderLinkId
                    pnl REAL DEFAULT 0,
                    status TEXT DEFAULT 'open',
                    state TEXT DEFAULT 'trade',
                    avg_exit_price REAL,
                    closed_size REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    placed_by TEXT DEFAULT 'BOT',
                    alteration_details TEXT, -- New column for alteration details
                    -- Additional comprehensive metadata fields
                    prompt_name TEXT,
                    timeframe TEXT,
                    confidence REAL,
                    risk_reward_ratio REAL,
                    order_type TEXT DEFAULT 'Limit'
                )
            '''))

            # Ensure all columns exist (for existing databases)
            self._ensure_trades_columns_exist(conn, cursor)

            # Add unique constraint on order_id if it doesn't exist
            try:
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_order_id_unique ON trades(order_id)")
            except Exception as e:
                # If constraint already exists or transaction is aborted, rollback and continue
                conn.rollback()
                pass
            
            # Create optimized indexes for trades table
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_order_id
                ON trades(order_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_recommendation_id
                ON trades(recommendation_id)
            ''')
            
            # Additional optimized indexes for frequently queried columns
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_status_symbol
                ON trades(status, symbol)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_created_at
                ON trades(created_at)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_status_created
                ON trades(status, created_at)
            ''')
            
            conn.commit()
            release_connection(conn)
            
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")
            raise
    
    def migrate_database(self):
        """Apply database migrations for schema updates."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Check existing columns in trades table using centralized helper
            columns = get_table_columns(conn, "trades")

            # Migration 1: Add placed_by column
            if 'placed_by' not in columns:
                print("Adding 'placed_by' column to trades table...")
                cursor.execute("ALTER TABLE trades ADD COLUMN placed_by TEXT DEFAULT 'BOT'")
                print("Migration completed: 'placed_by' column added successfully")
            else:
                print("Migration skipped: 'placed_by' column already exists")

            # Migration 2: Add comprehensive metadata columns
            metadata_columns = {
                'prompt_name': "ALTER TABLE trades ADD COLUMN prompt_name TEXT",
                'timeframe': "ALTER TABLE trades ADD COLUMN timeframe TEXT",
                'confidence': "ALTER TABLE trades ADD COLUMN confidence REAL",
                'risk_reward_ratio': "ALTER TABLE trades ADD COLUMN risk_reward_ratio REAL",
                'order_type': "ALTER TABLE trades ADD COLUMN order_type TEXT DEFAULT 'Limit'"
            }

            for column_name, alter_sql in metadata_columns.items():
                if column_name not in columns:
                    print(f"Adding '{column_name}' column to trades table...")
                    cursor.execute(alter_sql)
                    print(f"Migration completed: '{column_name}' column added successfully")
                else:
                    print(f"Migration skipped: '{column_name}' column already exists")
            
            # Check and add market_condition and market_direction columns to analysis_results table
            analysis_columns = get_table_columns(conn, "analysis_results")

            if 'market_condition' not in analysis_columns:
                print("Adding 'market_condition' column to analysis_results table...")
                cursor.execute("ALTER TABLE analysis_results ADD COLUMN market_condition TEXT")
                print("Migration completed: 'market_condition' column added successfully")
            else:
                print("Migration skipped: 'market_condition' column already exists")
                
            if 'market_direction' not in analysis_columns:
                print("Adding 'market_direction' column to analysis_results table...")
                cursor.execute("ALTER TABLE analysis_results ADD COLUMN market_direction TEXT")
                print("Migration completed: 'market_direction' column added successfully")
            else:
                print("Migration skipped: 'market_direction' column already exists")
            
            # Check and add analysis_prompt column to analysis_results table
            if 'analysis_prompt' not in analysis_columns:
                print("Adding 'analysis_prompt' column to analysis_results table...")
                cursor.execute("ALTER TABLE analysis_results ADD COLUMN analysis_prompt TEXT")
                print("Migration completed: 'analysis_prompt' column added successfully")
            else:
                print("Migration skipped: 'analysis_prompt' column already exists")
            
            # Check and add market_condition and market_direction columns to latest_recommendations table
            latest_columns = get_table_columns(conn, "latest_recommendations")

            if 'market_condition' not in latest_columns:
                print("Adding 'market_condition' column to latest_recommendations table...")
                cursor.execute("ALTER TABLE latest_recommendations ADD COLUMN market_condition TEXT")
                print("Migration completed: 'market_condition' column added to latest_recommendations successfully")
            else:
                print("Migration skipped: 'market_condition' column already exists in latest_recommendations")
                
            if 'market_direction' not in latest_columns:
                print("Adding 'market_direction' column to latest_recommendations table...")
                cursor.execute("ALTER TABLE latest_recommendations ADD COLUMN market_direction TEXT")
                print("Migration completed: 'market_direction' column added to latest_recommendations successfully")
            else:
                print("Migration skipped: 'market_direction' column already exists in latest_recommendations")
            
            # Check and add last_tightened_milestone column to trades table
            trades_columns = get_table_columns(conn, "trades")

            if 'last_tightened_milestone' not in trades_columns:
                print("Adding 'last_tightened_milestone' column to trades table...")
                cursor.execute("ALTER TABLE trades ADD COLUMN last_tightened_milestone TEXT")
                print("Migration completed: 'last_tightened_milestone' column added successfully")
            else:
                print("Migration skipped: 'last_tightened_milestone' column already exists")
            
            # Check and add alteration_details column to trades table
            # Reuse trades_columns from above - already has the columns
            if 'alteration_details' not in trades_columns:
                print("Adding 'alteration_details' column to trades table...")
                cursor.execute("ALTER TABLE trades ADD COLUMN alteration_details TEXT")
                print("Migration completed: 'alteration_details' column added successfully")
            else:
                print("Migration skipped: 'alteration_details' column already exists")

            if 'orderLinkId' not in trades_columns:
                print("Adding 'orderLinkId' column to trades table...")
                cursor.execute("ALTER TABLE trades ADD COLUMN orderLinkId TEXT")
                print("Migration completed: 'orderLinkId' column added successfully")
            else:
                print("Migration skipped: 'orderLinkId' column already exists")

            # Create analytics tables
            self._create_analytics_tables(cursor)
            
            conn.commit()
            release_connection(conn)
            
        except sqlite3.Error as e:
            print(f"Database migration error: {e}")
            raise
    
    def _create_analytics_tables(self, cursor):
        """Create analytics tables for trading statistics."""

        # Trading stats table for EV and profit factor calculations
        cursor.execute(normalize_sql('''
            CREATE TABLE IF NOT EXISTS trading_stats (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                total_win_pnl REAL DEFAULT 0.0,
                total_loss_pnl REAL DEFAULT 0.0,
                total_risk_amount REAL DEFAULT 0.0,
                expected_value REAL DEFAULT 0.0,
                profit_factor REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                avg_win REAL DEFAULT 0.0,
                avg_loss REAL DEFAULT 0.0,
                max_win REAL DEFAULT 0.0,
                max_loss REAL DEFAULT 0.0,
                avg_holding_period_hours REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe)
            )
        '''))
        
        # Migration: Add missing columns to existing trading_stats table (silent)
        try:
            stats_columns = get_table_columns(conn, "trading_stats")

            if 'total_win_pnl' not in stats_columns:
                cursor.execute("ALTER TABLE trading_stats ADD COLUMN total_win_pnl REAL DEFAULT 0.0")

            if 'total_loss_pnl' not in stats_columns:
                cursor.execute("ALTER TABLE trading_stats ADD COLUMN total_loss_pnl REAL DEFAULT 0.0")

        except Exception as e:
            print(f"Migration warning for trading_stats: {e}")
        
        # Position tracking table for live R/R monitoring
        cursor.execute(normalize_sql('''
            CREATE TABLE IF NOT EXISTS position_tracking (
                id TEXT PRIMARY KEY,
                recommendation_id TEXT,
                trade_id TEXT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                current_price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                live_rr REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                risk_amount REAL NOT NULL,
                position_size REAL NOT NULL,
                checked_at DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (recommendation_id) REFERENCES analysis_results(id),
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        '''))
        
        # Holding period analysis table
        cursor.execute(normalize_sql('''
            CREATE TABLE IF NOT EXISTS holding_period_stats (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                holding_period_bucket TEXT NOT NULL,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0.0,
                total_win_pnl REAL DEFAULT 0.0,
                total_loss_pnl REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                profit_factor REAL DEFAULT 0.0,
                avg_pnl REAL DEFAULT 0.0,
                avg_win_pnl REAL DEFAULT 0.0,
                avg_loss_pnl REAL DEFAULT 0.0,
                max_win REAL DEFAULT 0.0,
                max_loss REAL DEFAULT 0.0,
                avg_holding_hours REAL DEFAULT 0.0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe, holding_period_bucket)
            )
        '''))
        
        # Create indexes for analytics tables
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trading_stats_symbol_timeframe
            ON trading_stats(symbol, timeframe)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_tracking_symbol
            ON position_tracking(symbol)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_position_tracking_checked_at
            ON position_tracking(checked_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_holding_period_stats_symbol_timeframe
            ON holding_period_stats(symbol, timeframe)
        ''')
        
        print("Analytics tables created/verified successfully")
    
    def store_result(self, symbol: str, timeframe: str, result: Dict[str, Any], image_path: Optional[str] = None, analysis_prompt: Optional[str] = None) -> Optional[str]:
        """Store analysis result in database with UUID."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            analysis_id = str(uuid.uuid4())
            
            analysis = result.get('analysis', {})
            key_levels = analysis.get('key_levels', {})

            recommendation = analysis.get('recommendation', 'hold')
            # Prioritize confidence field from analysis result and round to 3 decimals
            confidence = self._to_float_or_none(analysis.get('confidence')) or self._to_float_or_none(analysis.get('trade_confidence')) or 0.0
            confidence = round(confidence, 3) if confidence is not None else 0.0
            summary = str(analysis.get('summary', ''))
            evidence = str(analysis.get('evidence', ''))
            support_level = self._to_float_or_none(key_levels.get('support'))
            resistance_level = self._to_float_or_none(key_levels.get('resistance'))
            entry_price = self._to_float_or_none(analysis.get('entry_price'))
            stop_loss = self._to_float_or_none(analysis.get('stop_loss'))
            take_profit = self._to_float_or_none(analysis.get('take_profit'))

            # Extract prompt_id and market_data from result
            prompt_id = result.get('prompt_id') or analysis.get('prompt_id')
            market_data_snapshot = result.get('market_data_snapshot', {})
            market_data_json = json.dumps(market_data_snapshot) if market_data_snapshot else None
            
            # Use direction from model response or calculate from recommendation
            direction = str(analysis.get('direction', '')).upper()
            
            # Calculate RR based on actual results
            rr = None
            if entry_price is not None and stop_loss is not None and take_profit is not None:
                if direction == "LONG":
                    risk = abs(entry_price - stop_loss)
                    reward = abs(take_profit - entry_price)
                elif direction == "SHORT":
                    risk = abs(stop_loss - entry_price)
                    reward = abs(entry_price - take_profit)
                else:
                    risk = abs(entry_price - stop_loss)
                    reward = abs(take_profit - entry_price)
                
                if risk > 0:
                    rr = round(reward / risk, 2)
            
            risk_factors = json.dumps(analysis.get('risk_factors', []))
            analysis_data = json.dumps(result)
            timestamp = analysis.get('timestamp')
            
            # Normalize the image_path to handle different formats (with/without ./ prefix)
            normalized_image_path = image_path
            if normalized_image_path and normalized_image_path.startswith('./'):
                normalized_image_path = normalized_image_path[2:]  # Remove './' prefix
            
            # Extract market condition and direction from analysis
            market_condition = str(analysis.get('market_condition', '')).upper()
            market_direction = str(analysis.get('market_direction', '')).upper()

            # Use centralized execute for proper SQLite/PostgreSQL placeholder conversion
            db_execute(conn, '''
                INSERT INTO analysis_results
                (id, symbol, timeframe, recommendation, confidence, summary, evidence,
                 support_level, resistance_level, entry_price, stop_loss, take_profit, direction, rr, risk_factors, analysis_data, analysis_prompt, timestamp, image_path, market_condition, market_direction, prompt_id, market_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                analysis_id,
                symbol or 'UNKNOWN',
                timeframe or '1h',
                recommendation,
                confidence,
                summary,
                evidence,
                support_level,
                resistance_level,
                entry_price,
                stop_loss,
                take_profit,
                direction,
                rr,
                risk_factors,
                analysis_data,
                analysis_prompt,
                timestamp,
                str(normalized_image_path or ''),
                market_condition,
                market_direction,
                prompt_id,
                market_data_json
            ))

            conn.commit()
            return analysis_id
        except Exception as e:
            print(f"Database error in store_result: {e}")
            raise
        finally:
            release_connection(conn)

    def clear_latest_recommendations(self):
        """Clear all data from the latest_recommendations table."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM latest_recommendations")
            conn.commit()
        except sqlite3.Error as e:
            print(f"Database error in clear_latest_recommendations: {e}")
        finally:
            release_connection(conn)

    def store_latest_recommendations(self, recommendations: List[Dict[str, Any]]):
        """Store a list of recommendations in the latest_recommendations table."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            for result in recommendations:
                analysis_id = result.get('id')
                symbol = result.get('symbol')
                timeframe = result.get('timeframe')
                recommendation = result.get('recommendation')
                confidence = self._to_float_or_none(result.get('confidence'))
                confidence = round(confidence, 3) if confidence is not None else 0.0
                summary = result.get('summary')
                support_level = self._to_float_or_none(result.get('support_level'))
                resistance_level = self._to_float_or_none(result.get('resistance_level'))
                entry_price = self._to_float_or_none(result.get('entry_price'))
                stop_loss = self._to_float_or_none(result.get('stop_loss'))
                take_profit = self._to_float_or_none(result.get('take_profit'))

                # Calculate direction based on recommendation
                direction = "LONG" if str(recommendation).lower() == "buy" else "SHORT" if str(recommendation).lower() == "sell" else "NEUTRAL"

                # Calculate risk/reward ratio
                rr = None
                if entry_price is not None and stop_loss is not None and take_profit is not None:
                    if direction == "LONG":
                        risk = abs(entry_price - stop_loss)
                        reward = abs(take_profit - entry_price)
                    else:  # SHORT
                        risk = abs(stop_loss - entry_price)
                        reward = abs(entry_price - take_profit)

                    if risk > 0:
                        rr = round(reward / risk, 2)

                risk_factors = json.dumps(result.get('risk_factors', []))
                analysis_data = json.dumps(result.get('analysis_data'))
                timestamp = result.get('timestamp')
                image_path = result.get('image_path')

                # Extract market condition and direction
                market_condition = str(result.get('market_condition', '')).upper()
                market_direction = str(result.get('market_direction', '')).upper()

                # Extract prompt_id and market_data
                prompt_id = result.get('prompt_id')
                market_data = result.get('market_data')

                # Use centralized execute for proper SQLite/PostgreSQL placeholder conversion
                db_execute(conn, '''
                    INSERT INTO latest_recommendations
                    (id, symbol, timeframe, recommendation, confidence, summary,
                     support_level, resistance_level, entry_price, stop_loss, take_profit, direction, rr, risk_factors, analysis_data, timestamp, image_path, market_condition, market_direction, prompt_id, market_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    analysis_id, symbol, timeframe, recommendation, confidence, summary,
                    support_level, resistance_level, entry_price, stop_loss, take_profit, direction, rr, risk_factors, analysis_data, timestamp, image_path, market_condition, market_direction, prompt_id, market_data
                ))

            conn.commit()
        except Exception as e:
            print(f"Database error in store_latest_recommendations: {e}")
            raise
        finally:
            release_connection(conn)
    
    def get_distinct_symbol_timeframes(self) -> List[Dict[str, str]]:
        """Get all distinct symbol/timeframe pairs from the database."""
        conn = self.get_connection()
        try:
            # Use centralized query for consistency
            rows = query(conn, 'SELECT DISTINCT symbol, timeframe FROM analysis_results', ())
            return [{"symbol": row[0], "timeframe": row[1]} for row in rows]
        except Exception as e:
            print(f"Database error in get_distinct_symbol_timeframes: {e}")
            return []
        finally:
            release_connection(conn)

    def get_latest_analysis(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Get the most recent analysis for a symbol/timeframe."""
        conn = self._get_pooled_connection()
        try:
            # Use centralized query_one to handle SQLite/PostgreSQL placeholder conversion
            row = query_one(conn, '''
                SELECT * FROM analysis_results
                WHERE symbol = ? AND timeframe = ?
                ORDER BY timestamp DESC LIMIT 1
            ''', (symbol, timeframe))

            if row:
                return dict(row.items())
            return None

        except Exception as e:
            print(f"Database error in get_latest_analysis: {e}")
            return None
        finally:
            self._return_connection(conn)
    
    def analysis_exists(self, image_path: str) -> bool:
        """Check if an analysis for a given image_path already exists.

        Checks the 'recommendations' table (used by trading_cycle.py) which stores
        analysis results with chart_path column.

        Includes retry logic for transient SSL connection errors in parallel execution.
        """
        import time
        max_retries = 3
        retry_delay = 0.5  # seconds

        # Normalize the path to handle different formats (with/without ./ prefix)
        normalized_path = image_path
        if normalized_path.startswith('./'):
            normalized_path = normalized_path[2:]  # Remove './' prefix

        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()

                # Check recommendations table (used by trading_cycle.py for storing analysis)
                row = query_one(conn, '''
                    SELECT 1 FROM recommendations
                    WHERE chart_path = ?
                    LIMIT 1
                ''', (normalized_path,))

                return row is not None

            except Exception as e:
                error_str = str(e).lower()
                is_ssl_error = 'ssl' in error_str or 'connection' in error_str

                if is_ssl_error and attempt < max_retries - 1:
                    # Retry on SSL/connection errors
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    print(f"Database error in analysis_exists: {e}")
                    return False
            finally:
                if conn:
                    try:
                        release_connection(conn)
                    except Exception:
                        pass

        return False

    def get_analysis_by_image_path(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Get the stored analysis for a specific image path.

        Fetches from 'recommendations' table (used by trading_cycle.py) which stores
        analysis results with chart_path column.

        Includes retry logic for transient SSL connection errors in parallel execution.
        """
        import time
        max_retries = 3
        retry_delay = 0.5  # seconds

        # Normalize the path to handle different formats (with/without ./ prefix)
        normalized_path = image_path
        if normalized_path.startswith('./'):
            normalized_path = normalized_path[2:]  # Remove './' prefix

        for attempt in range(max_retries):
            conn = None
            try:
                conn = self.get_connection()

                # Query recommendations table (used by trading_cycle.py)
                row = query_one(conn, '''
                    SELECT id, symbol, timeframe, recommendation, confidence,
                           entry_price, stop_loss, take_profit, risk_reward,
                           reasoning as summary, chart_path as image_path,
                           raw_response as analysis_data, analyzed_at as timestamp
                    FROM recommendations
                    WHERE chart_path = ?
                    ORDER BY analyzed_at DESC LIMIT 1
                ''', (normalized_path,))

                if row:
                    return dict(row.items())
                return None

            except Exception as e:
                error_str = str(e).lower()
                is_ssl_error = 'ssl' in error_str or 'connection' in error_str

                if is_ssl_error and attempt < max_retries - 1:
                    # Retry on SSL/connection errors
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    print(f"Database error in get_analysis_by_image_path: {e}")
                    return None
            finally:
                if conn:
                    try:
                        release_connection(conn)
                    except Exception:
                        pass

        return None
    
    def get_all_latest_analysis(self) -> List[Dict[str, Any]]:
        """Get the most recent analysis for each symbol/timeframe pair."""
        pairs = self.get_distinct_symbol_timeframes()
        latest_analyses = []
        for pair in pairs:
            analysis = self.get_latest_analysis(pair["symbol"], pair["timeframe"])
            if analysis:
                latest_analyses.append(analysis)
            # Periodic garbage collection to prevent memory buildup
            if len(latest_analyses) % 50 == 0:
                gc.collect()
        # Final garbage collection
        if latest_analyses:
            gc.collect()
        return latest_analyses

    def get_analysis_history(self, symbol: Optional[str] = None, timeframe: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get analysis history with optional filtering."""
        conn = self.get_connection()
        try:
            query_str = "SELECT * FROM analysis_results WHERE 1=1"
            params = []

            if symbol:
                query_str += " AND symbol = ?"
                params.append(symbol)

            if timeframe:
                query_str += " AND timeframe = ?"
                params.append(timeframe)

            query_str += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            rows = query(conn, query_str, tuple(params))

            return [dict(row.items()) for row in rows]

        except Exception as e:
            print(f"Database error in get_analysis_history: {e}")
            return []
        finally:
            release_connection(conn)
    
    def get_performance_stats(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Get performance statistics for stored analyses."""
        conn = self.get_connection()
        try:
            query_str = "SELECT COUNT(*), AVG(confidence), recommendation FROM analysis_results"
            params = []

            if symbol:
                query_str += " WHERE symbol = ?"
                params.append(symbol)

            query_str += " GROUP BY recommendation"

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            results = query(conn, query_str, tuple(params))

            stats = {
                'total_analyses': 0,
                'average_confidence': 0.0,
                'recommendations': {'buy': 0, 'sell': 0, 'hold': 0}
            }

            for row in results:
                count = row[0]
                avg_conf = row[1]
                rec = row[2]
                stats['total_analyses'] += count
                if rec in ['buy', 'sell', 'hold']:
                    stats['recommendations'][rec] = count

            if results:
                stats['average_confidence'] = sum(r[1] * r[0] for r in results) / sum(r[0] for r in results)

            return stats

        except Exception as e:
            print(f"Database error in get_performance_stats: {e}")
            return {
                'total_analyses': 0,
                'average_confidence': 0.0,
                'recommendations': {'buy': 0, 'sell': 0, 'hold': 0}
            }
        finally:
            release_connection(conn)

    def reset_database(self):
        """Clear all data and reapply the schema."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Drop existing tables
            cursor.execute("DROP TABLE IF EXISTS analysis_results")
            
            conn.commit()
            
            # Re-initialize
            self.init_database()
            
        except sqlite3.Error as e:
            print(f"Database error in reset_database: {e}")
            raise
        finally:
            release_connection(conn)
    
    def clear_all_data(self):
        """Clear all data from the database but keep the schema."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM analysis_results")
            conn.commit()
            
        except sqlite3.Error as e:
            print(f"Database error in clear_all_data: {e}")
        finally:
            release_connection(conn)
    
    def _row_to_dict(self, cursor, row) -> Dict[str, Any]:
        """Convert SQLite row to dictionary."""
        columns = [description[0] for description in cursor.description]
        result = dict(zip(columns, row))
        
        # Parse JSON fields
        if 'risk_factors' in result and result['risk_factors']:
            try:
                result['risk_factors'] = json.loads(result['risk_factors'])
            except (json.JSONDecodeError, TypeError):
                result['risk_factors'] = {} # or some other default
        if 'analysis_data' in result and result['analysis_data']:
            try:
                result['analysis_data'] = json.loads(result['analysis_data'])
            except (json.JSONDecodeError, TypeError):
                result['analysis_data'] = {} # or some other default
        
        # Ensure orderLinkId is present, even if None in DB
        if 'orderLinkId' not in result:
            result['orderLinkId'] = None
        
        return result

    def store_trade(self, trade_id: str, recommendation_id: str, symbol: str, side: str,
                   quantity: float, entry_price: float, take_profit: float, stop_loss: float,
                   order_id: Optional[str], orderLinkId: Optional[str] = None, pnl: float = 0.0, status: str = 'open', state: str = 'trade',
                   avg_exit_price: Optional[float] = None, closed_size: Optional[float] = None,
                   created_at: Optional[str] = None, placed_by: str = 'BOT',
                   alteration_details: Optional[str] = None,
                   # Additional comprehensive metadata fields
                   prompt_name: Optional[str] = None,
                   timeframe: Optional[str] = None, confidence: Optional[float] = None,
                   risk_reward_ratio: Optional[float] = None, order_type: Optional[str] = 'Limit') -> bool:
        """Store a trade record in the database."""
        # Check if trade with this order_id already exists (only for non-empty order_ids)
        if order_id and order_id.strip():  # Only check for duplicates if order_id is not empty/whitespace
            existing_trade = self.get_trade_by_order_id(order_id)
            if existing_trade:
                # print(f"Trade with order_id {order_id} already exists, skipping insertion")
                return True  # Return True since the trade effectively exists

        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Use CURRENT_TIMESTAMP if created_at is not provided
            created_at_val = created_at if created_at else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute('''
                INSERT INTO trades
                (id, recommendation_id, symbol, side, quantity, entry_price, take_profit, stop_loss, order_id, orderLinkId,
                 pnl, status, state, avg_exit_price, closed_size, created_at, placed_by, alteration_details,
                 prompt_name, timeframe, confidence, risk_reward_ratio, order_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (trade_id, recommendation_id, symbol, side, quantity, entry_price, take_profit, stop_loss, order_id, orderLinkId,
                  pnl, status, state, avg_exit_price, closed_size, created_at_val, placed_by, alteration_details,
                  prompt_name, timeframe, confidence, risk_reward_ratio, order_type))

            conn.commit()
            return True

        except sqlite3.Error as e:
            print(f"Database error in store_trade: {e}")
            return False
        finally:
            if conn:
                release_connection(conn)

    def update_trade(self, trade_id: str, **kwargs) -> bool:
        """Update a trade record with new data."""
        conn = None
        try:
            conn = self.get_connection()

            # DEBUG: Log the update attempt
            # print(f"DEBUG: Attempting to update trade {trade_id} with data: {kwargs}")

            # Build dynamic update query
            set_clauses = []
            values = []

            for key, value in kwargs.items():
                if key in ['pnl', 'status', 'state', 'avg_exit_price', 'closed_size', 'placed_by', 'last_tightened_milestone', 'alteration_details', 'entry_price', 'quantity', 'order_id', 'orderLinkId', 'updated_at']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
                else:
                    # print(f"DEBUG: Ignoring invalid field '{key}' with value '{value}'")
                    pass

            if not set_clauses:
                # print(f"DEBUG: No valid fields to update for trade {trade_id}")
                return False

            # Always update the updated_at timestamp
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            values.append(trade_id)

            query_str = f"UPDATE trades SET {', '.join(set_clauses)} WHERE id = ?"
            # print(f"DEBUG: Executing query: {query_str}")
            # print(f"DEBUG: Query values: {values}")

            # Use centralized db_execute to handle SQLite/PostgreSQL placeholder conversion
            rows_affected = db_execute(conn, query_str, tuple(values))

            conn.commit()
            # print(f"DEBUG: Rows affected: {rows_affected}")

            if rows_affected == 0:
                # print(f"DEBUG: No rows updated for trade_id {trade_id} - trade may not exist")
                pass

            return rows_affected > 0

        except Exception as e:
            print(f"Database error in update_trade: {e}")
            return False
        finally:
            if conn:
                release_connection(conn)

    def update_trade_by_order_id(self, order_id: str, **kwargs) -> bool:
        """Update a trade record by order_id with new data."""
        conn = None
        try:
            conn = self.get_connection()

            # Build dynamic update query
            set_clauses = []
            values = []

            for key, value in kwargs.items():
                if key in ['pnl', 'status', 'state', 'avg_exit_price', 'closed_size', 'placed_by', 'last_tightened_milestone', 'alteration_details']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
                else:
                    pass

            if not set_clauses:
                return False

            # Always update the updated_at timestamp
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            values.append(order_id)

            query_str = f"UPDATE trades SET {', '.join(set_clauses)} WHERE order_id = ?"

            # Use centralized db_execute to handle SQLite/PostgreSQL placeholder conversion
            rows_affected = db_execute(conn, query_str, tuple(values))

            conn.commit()

            return rows_affected > 0

        except Exception as e:
            print(f"Database error in update_trade_by_order_id: {e}")
            return False
        finally:
            if conn:
                release_connection(conn)

    def mark_trade_as_cancelled(self, order_id: str) -> bool:
        """Mark a trade as cancelled when its order is cancelled."""
        return self.update_trade_by_order_id(order_id, status='cancelled')

    def get_trades_needing_pnl(self) -> List[Dict[str, Any]]:
        """Get trades that need PnL data (state=position with missing/zero PnL)."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Query for trades with state=position and missing/zero PnL, excluding cancelled trades
            query = """
                SELECT * FROM trades
                WHERE state = 'position'
                AND status != 'cancelled'
                AND (pnl IS NULL OR pnl = '' OR pnl = 0 OR pnl = 0.0)
                ORDER BY created_at DESC
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            trades = []
            for row in rows:
                trade = self._row_to_dict(cursor, row)
                trades.append(trade)
            
            return trades
            
        except Exception as e:
            print(f"Error getting trades needing PnL: {e}")
            return []
        finally:
            release_connection(conn)

    def get_trades(self, symbol: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get trades from database with optional filtering."""
        conn = None
        try:
            conn = self.get_connection()

            query_str = "SELECT * FROM trades"
            params = []
            conditions = []

            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)

            if status:
                conditions.append("status = ?")
                params.append(status)

            if conditions:
                query_str += " WHERE " + " AND ".join(conditions)

            query_str += " ORDER BY created_at DESC"

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            rows = query(conn, query_str, tuple(params))

            trades = [dict(row.items()) for row in rows]

            return trades

        except Exception as e:
            print(f"Database error in get_trades: {e}")
            return []
        finally:
            if conn:
                release_connection(conn)

    def get_trade_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get a trade by its order ID."""
        conn = None
        try:
            conn = self.get_connection()

            # Use centralized query_one to handle SQLite/PostgreSQL placeholder conversion
            row = query_one(conn, "SELECT * FROM trades WHERE order_id = ?", (order_id,))

            if row:
                # Convert UnifiedRow to dict
                trade = dict(row.items())
                return trade

            return None

        except Exception as e:
            print(f"Database error in get_trade_by_order_id: {e}")
            return None
        finally:
            if conn:
                release_connection(conn)

    def store_position_tracking(self, tracking_data: Dict[str, Any]) -> bool:
        """Store position tracking data for live R/R monitoring."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            tracking_id = str(uuid.uuid4())

            cursor.execute('''
                INSERT INTO position_tracking (
                    id, recommendation_id, trade_id, symbol, timeframe, direction,
                    entry_price, current_price, stop_loss, take_profit, live_rr,
                    unrealized_pnl, risk_amount, position_size, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                tracking_id,
                tracking_data.get('recommendation_id'),
                tracking_data.get('trade_id'),
                tracking_data['symbol'],
                tracking_data['timeframe'],
                tracking_data['direction'],
                tracking_data['entry_price'],
                tracking_data['current_price'],
                tracking_data.get('stop_loss'),
                tracking_data.get('take_profit'),
                tracking_data['live_rr'],
                tracking_data['unrealized_pnl'],
                tracking_data['risk_amount'],
                tracking_data['position_size'],
                tracking_data['checked_at']
            ))

            conn.commit()
            return True

        except sqlite3.Error as e:
            print(f"Error storing position tracking data: {e}")
            return False
        finally:
            if conn:
                release_connection(conn)
    
    def update_trading_stats_for_closed_trade(self, trade_data: Dict[str, Any]) -> bool:
        """Update trading statistics when a trade closes."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            symbol = trade_data['symbol']
            timeframe = trade_data.get('timeframe', 'unknown')
            pnl = float(trade_data.get('pnl', 0))
            is_win = pnl > 0

            # Get or create stats record
            cursor.execute('''
                SELECT * FROM trading_stats WHERE symbol = ? AND timeframe = ?
            ''', (symbol, timeframe))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                stats = self._row_to_dict(cursor, existing)
                stats['total_trades'] += 1
                if is_win:
                    stats['winning_trades'] += 1
                    stats['total_win_pnl'] = stats.get('total_win_pnl', 0) + pnl
                    stats['max_win'] = max(stats.get('max_win', 0), pnl)
                else:
                    stats['losing_trades'] += 1
                    stats['total_loss_pnl'] = stats.get('total_loss_pnl', 0) + abs(pnl)
                    stats['max_loss'] = max(stats.get('max_loss', 0), abs(pnl))

                stats['total_pnl'] += pnl

                # Calculate derived metrics
                stats['win_rate'] = stats['winning_trades'] / stats['total_trades']
                stats['avg_win'] = stats['total_win_pnl'] / max(stats['winning_trades'], 1)
                stats['avg_loss'] = stats['total_loss_pnl'] / max(stats['losing_trades'], 1)

                # Expected Value = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
                loss_rate = stats['losing_trades'] / stats['total_trades']
                stats['expected_value'] = (stats['win_rate'] * stats['avg_win']) - (loss_rate * stats['avg_loss'])

                # Profit Factor = Total Gross Profit / Total Gross Loss
                stats['profit_factor'] = stats['total_win_pnl'] / max(stats['total_loss_pnl'], 0.01)

                stats['last_updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

                cursor.execute('''
                    UPDATE trading_stats SET
                        total_trades = ?, winning_trades = ?, losing_trades = ?,
                        total_pnl = ?, total_win_pnl = ?, total_loss_pnl = ?,
                        win_rate = ?, profit_factor = ?, expected_value = ?,
                        avg_win = ?, avg_loss = ?, max_win = ?, max_loss = ?,
                        last_updated = ?
                    WHERE symbol = ? AND timeframe = ?
                ''', (
                    stats['total_trades'], stats['winning_trades'], stats['losing_trades'],
                    stats['total_pnl'], stats['total_win_pnl'], stats['total_loss_pnl'],
                    stats['win_rate'], stats['profit_factor'], stats['expected_value'],
                    stats['avg_win'], stats['avg_loss'], stats['max_win'], stats['max_loss'],
                    stats['last_updated'], symbol, timeframe
                ))
            else:
                # Create new record
                stats_id = str(uuid.uuid4())
                win_rate = 1.0 if is_win else 0.0
                total_win_pnl = pnl if is_win else 0.0
                total_loss_pnl = abs(pnl) if not is_win else 0.0

                cursor.execute('''
                    INSERT INTO trading_stats (
                        id, symbol, timeframe, total_trades, winning_trades, losing_trades,
                        total_pnl, total_win_pnl, total_loss_pnl, win_rate, profit_factor,
                        expected_value, avg_win, avg_loss, max_win, max_loss, last_updated
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats_id, symbol, timeframe, 1,
                    1 if is_win else 0, 0 if is_win else 1,
                    pnl, total_win_pnl, total_loss_pnl, win_rate,
                    total_win_pnl / max(total_loss_pnl, 0.01),  # profit_factor
                    pnl,  # expected_value (first trade)
                    total_win_pnl if is_win else 0,  # avg_win
                    total_loss_pnl if not is_win else 0,  # avg_loss
                    pnl if is_win else 0,  # max_win
                    abs(pnl) if not is_win else 0,  # max_loss
                    datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                ))

            conn.commit()
            return True

        except Exception as e:
            print(f"Error updating trading stats: {e}")
            return False
        finally:
            if conn:
                release_connection(conn)
   
    def get_trading_stats(self, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get trading statistics with optional filtering."""
        conn = None
        try:
            conn = self.get_connection()

            query_str = "SELECT * FROM trading_stats"
            params = []

            if symbol or timeframe:
                conditions = []
                if symbol:
                    conditions.append("symbol = ?")
                    params.append(symbol)
                if timeframe:
                    conditions.append("timeframe = ?")
                    params.append(timeframe)
                query_str += " WHERE " + " AND ".join(conditions)

            query_str += " ORDER BY symbol, timeframe"

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            results = query(conn, query_str, tuple(params))

            return [dict(row.items()) for row in results]

        except Exception as e:
            print(f"Error getting trading stats: {e}")
            return []
        finally:
            if conn:
                release_connection(conn)
    
    def get_portfolio_ev_summary(self) -> Dict[str, Any]:
        """Get portfolio-wide Expected Value summary."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    SUM(total_trades) as total_trades,
                    SUM(winning_trades) as total_wins,
                    SUM(losing_trades) as total_losses,
                    SUM(total_pnl) as total_pnl,
                    SUM(total_win_pnl) as total_win_pnl,
                    SUM(total_loss_pnl) as total_loss_pnl,
                    AVG(expected_value) as avg_expected_value,
                    AVG(profit_factor) as avg_profit_factor,
                    AVG(win_rate) as avg_win_rate
                FROM trading_stats
                WHERE total_trades > 0
            ''')

            result = cursor.fetchone()

            if result and result[0]:  # Check if we have data
                total_trades = result[0]
                portfolio_win_rate = result[1] / total_trades if total_trades > 0 else 0
                portfolio_pf = result[4] / max(result[5], 0.01) if result[5] > 0 else 0

                return {
                    'total_trades': total_trades,
                    'portfolio_win_rate': portfolio_win_rate,
                    'portfolio_profit_factor': portfolio_pf,
                    'total_pnl': result[3] or 0,
                    'avg_expected_value': result[6] or 0,
                    'avg_profit_factor': result[7] or 0,
                    'avg_win_rate': result[8] or 0
                }
            else:
                return {
                    'total_trades': 0,
                    'portfolio_win_rate': 0,
                    'portfolio_profit_factor': 0,
                    'total_pnl': 0,
                    'avg_expected_value': 0,
                    'avg_profit_factor': 0,
                    'avg_win_rate': 0
                }

        except sqlite3.Error as e:
            print(f"Error getting portfolio EV summary: {e}")
            return {'error': str(e)}
        finally:
            if conn:
                release_connection(conn)

    def get_recommendations_for_current_boundary(self, symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        """
        Get recommendations for the current timeframe boundary using standardized TimestampValidator.

        For example, if it's 1:33pm UTC and timeframe is 1h,
        fetch only recommendations between 1:00pm and 2:00pm.

        This method uses the same boundary calculation logic as TimestampValidator
        to ensure consistency across the entire system.

        Args:
            symbol: Symbol to filter for, or "all" for all symbols
            timeframe: Timeframe string (e.g., "1h", "15m", "4h")

        Returns:
            List of recommendations within the current boundary period
        """
        conn = None
        try:
            from datetime import datetime, timezone
            from trading_bot.core.timestamp_validator import TimestampValidator

            # Use standardized TimestampValidator for consistent boundary calculation
            validator = TimestampValidator()
            current_time = datetime.now(timezone.utc)

            # Calculate current boundary period using the same logic as recommender
            timeframe_info = validator.normalize_timeframe(timeframe)
            next_boundary = validator.calculate_next_boundary(current_time, timeframe_info.normalized)
            current_boundary = next_boundary - timeframe_info.timedelta

            # Format timestamps for database query (both formats)
            current_boundary_str = current_boundary.strftime('%Y-%m-%d %H:%M:%S')
            next_boundary_str = next_boundary.strftime('%Y-%m-%d %H:%M:%S')
            current_boundary_iso = current_boundary.isoformat()
            next_boundary_iso = next_boundary.isoformat()

            conn = self.get_connection()

            # Query for recommendations within the current boundary period
            # Use >= current_boundary and < next_boundary to ensure exact period matching
            if symbol == "all":
                query_str = '''
                    SELECT * FROM analysis_results
                    WHERE timeframe = ?
                    AND (
                        (timestamp >= ? AND timestamp < ?) OR
                        (timestamp >= ? AND timestamp < ?)
                    )
                    ORDER BY timestamp DESC
                '''
                params = (timeframe, current_boundary_str, next_boundary_str, current_boundary_iso, next_boundary_iso)
            else:
                query_str = '''
                    SELECT * FROM analysis_results
                    WHERE symbol = ?
                    AND timeframe = ?
                    AND (
                        (timestamp >= ? AND timestamp < ?) OR
                        (timestamp >= ? AND timestamp < ?)
                    )
                    ORDER BY timestamp DESC
                '''
                params = (symbol, timeframe, current_boundary_str, next_boundary_str, current_boundary_iso, next_boundary_iso)

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            rows = query(conn, query_str, params)

            results = [dict(row.items()) for row in rows]

            # Filter results to ensure they are actually within the current boundary period
            # This provides an additional safety check
            filtered_results = []
            for result in results:
                timestamp_str = result.get('timestamp')
                if timestamp_str:
                    try:
                        # Use TimestampValidator to check if timestamp is within current period
                        validation_result = validator.is_recommendation_valid(
                            timestamp_str, timeframe, current_time, allow_current_period=True, grace_period_minutes=0
                        )
                        # Only include if it's actually within the current boundary (no grace period)
                        if validation_result.is_valid:
                            # Additional check: timestamp should be >= current_boundary and < next_boundary
                            parsed_timestamp = validator.parse_timestamp(timestamp_str)
                            if current_boundary <= parsed_timestamp < next_boundary:
                                filtered_results.append(result)
                    except Exception:
                        # If validation fails, exclude the result
                        pass

            # Log debug information
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Boundary calculation for {timeframe}: {current_boundary_str} to {next_boundary_str}")
            logger.debug(f"Found {len(results)} raw results, {len(filtered_results)} filtered results")

            return filtered_results

        except Exception as e:
            print(f"Error getting recommendations for current boundary: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return []
        finally:
            if conn:
                release_connection(conn)

    def get_trades_for_current_cycle(self, timeframe: str, current_time: datetime) -> List[Dict[str, Any]]:
        """
        Get trades that were placed within the current cycle boundary.

        This method uses the same boundary calculation logic as TimestampValidator
        to ensure consistency across the entire system.

        Args:
            timeframe: Timeframe string (e.g., "1h", "15m", "4h")
            current_time: Current UTC time

        Returns:
            List of trades placed within the current cycle period
        """
        conn = None
        try:
            from trading_bot.core.timestamp_validator import TimestampValidator

            validator = TimestampValidator()

            # Calculate current cycle boundary period
            timeframe_info = validator.normalize_timeframe(timeframe)
            next_boundary = validator.calculate_next_boundary(current_time, timeframe_info.normalized)
            current_boundary = next_boundary - timeframe_info.timedelta

            # Format timestamps for database query
            current_boundary_str = current_boundary.strftime('%Y-%m-%d %H:%M:%S')
            next_boundary_str = next_boundary.strftime('%Y-%m-%d %H:%M:%S')

            conn = self.get_connection()

            # Query for trades within the current cycle period
            # Use >= current_boundary and < next_boundary to ensure exact period matching
            query_str = '''
                SELECT * FROM trades
                WHERE created_at >= ? AND created_at < ?
                ORDER BY created_at DESC
            '''
            params = (current_boundary_str, next_boundary_str)

            # Use centralized query to handle SQLite/PostgreSQL placeholder conversion
            rows = query(conn, query_str, params)

            results = [dict(row.items()) for row in rows]

            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Trades boundary calculation for {timeframe}: {current_boundary_str} to {next_boundary_str}")
            logger.debug(f"Found {len(results)} trades within current cycle")

            return results

        except Exception as e:
            print(f"Error getting trades for current cycle: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return []
        finally:
            if conn:
                release_connection(conn)

    def close_connection(self):
        """Close any open database connection if necessary."""
        # This is more of a placeholder. Due to connection-per-method,
        # we don't have a persistent connection to close.
        # If we were to switch to a single persistent connection, this would be crucial.
        print("DataAgent connection management is per-method; no persistent connection to close.")
    
    def bulk_update_trades_from_exchange(self, exchange_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk update trades from exchange data for efficient synchronization.

        Args:
            exchange_data: List of trade data from exchange sync

        Returns:
            Dict with update statistics
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            updated_count = 0
            created_count = 0
            error_count = 0

            for trade_data in exchange_data:
                try:
                    order_id = trade_data.get('order_id')
                    if not order_id:
                        error_count += 1
                        continue

                    # Check if trade exists
                    existing_trade = self.get_trade_by_order_id(order_id)

                    if existing_trade:
                        # Update existing trade
                        update_data = {
                            'status': trade_data.get('status'),
                            'state': trade_data.get('state'),
                            'pnl': trade_data.get('pnl'),
                            'avg_exit_price': trade_data.get('avg_exit_price'),
                            'closed_size': trade_data.get('closed_size'),
                            'updated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                        }

                        if self.update_trade(existing_trade['id'], **update_data):
                            updated_count += 1
                    else:
                        # Create new trade record
                        trade_id = str(uuid.uuid4())[:8]
                        success = self.store_trade(
                            trade_id=trade_id,
                            recommendation_id=trade_data.get('recommendation_id', ''),
                            symbol=trade_data.get('symbol', ''),
                            side=trade_data.get('side', 'Buy'),
                            quantity=trade_data.get('quantity', 0),
                            entry_price=trade_data.get('entry_price', 0),
                            take_profit=trade_data.get('take_profit', 0),
                            stop_loss=trade_data.get('stop_loss', 0),
                            order_id=order_id,
                            orderLinkId=trade_data.get('orderLinkId'), # Pass orderLinkId here
                            placed_by=trade_data.get('placed_by', 'EXCHANGE_SYNC')
                        )
                        if success:
                            created_count += 1
                        else:
                            error_count += 1

                except Exception as e:
                    print(f"Error processing trade data: {e}")
                    error_count += 1

            return {
                'status': 'success',
                'updated_count': updated_count,
                'created_count': created_count,
                'error_count': error_count,
                'total_processed': len(exchange_data)
            }

        except Exception as e:
            print(f"Error in bulk_update_trades_from_exchange: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
        finally:
            if conn:
                release_connection(conn)

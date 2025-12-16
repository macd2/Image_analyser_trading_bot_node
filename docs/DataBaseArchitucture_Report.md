I'll conduct a comprehensive audit of the database architecture to ensure it's sound, centralized, and respects DB_TYPE in all cases. This is research only - no coding.

Let me continue viewing the client.py file:

Let me continue viewing:

Let me continue viewing:

Let me continue viewing the rest:

Now let me search for all database imports and usage patterns across the codebase:

Now let me check each of these files for direct database imports:

Now let me check how these files are using sqlite3:

Let me search for where sqlite3 is actually used in this file:

Let me check data_loader.py:

Let me check trade_tracker.py:

Let me check the trading_bot/core/data_agent.py for sqlite3 usage:

Now let me check for any direct database connections being created outside the centralized layer:

Now let me check if there are any places where DB_TYPE is not being respected:

Now let me check for any hardcoded database paths or connections:

Now let me check for any places where connections are not being released properly:

Let me check some of these files more carefully:

Let me check if this connection is released:

Good! Now let me check the cleaner.py file:

Let me check if this connection is released:

I see an issue - the connection is not released in the cleaner.py. Let me check analytics_utils.py:

Good, that one has release. Now let me check database_utils.py:

Let me check if this connection is released:

I see issues here - it's using `conn.close()` instead of `release_connection()`. Let me check the rest of the file:

Now let me create a comprehensive audit report. Let me check a few more critical files:

Now let me check config/settings_v2.py:

Good! Now let me create a comprehensive audit summary. Let me check one more critical area - the prompt_performance files:

Let me check if ab_testing uses context managers:

Good - ab_testing uses context managers. Now let me create a comprehensive audit report:

Now let me create a comprehensive audit report:

## 🔍 COMPREHENSIVE DATABASE ARCHITECTURE AUDIT - RESEARCH FINDINGS

I've completed an exhaustive audit of the entire Python application's database architecture. Here are my findings:

### **ARCHITECTURE OVERVIEW** ✅

The centralized database layer (`python/trading_bot/db/client.py`) is well-designed with:

✅ **Single Source of Truth**: All database operations should go through `trading_bot.db.client`
✅ **DB_TYPE Abstraction**: Properly handles both SQLite and PostgreSQL via `DB_TYPE` environment variable
✅ **Connection Pooling**: PostgreSQL uses ThreadedConnectionPool (minconn=5, maxconn=100) for multi-instance support
✅ **Placeholder Conversion**: Automatically converts SQLite `?` to PostgreSQL `%s`
✅ **Boolean Handling**: Proper conversion between SQLite (0/1) and PostgreSQL (true/false)
✅ **Table Name Mapping**: Handles different table names between SQLite and PostgreSQL
✅ **Unified Row Wrapper**: Supports both index and key access for consistency

---

### **CRITICAL ISSUES FOUND** ⚠️

#### **1. `python/prompt_performance/core/database_utils.py` - 15 Locations Using `conn.close()` Instead of `release_connection()`** 🔴

**Severity**: HIGH - Connection pool management broken for PostgreSQL

**Locations**:
- Line 101: `conn.close()` in `_initialize_database()`
- Line 136: `conn.close()` in `get_latest_candle_timestamp()`
- Line 155: `conn.close()` in `get_candle_by_timestamp()`
- Line 211: `conn.close()` in `store_candles()`
- Line 226: `conn.close()` in `store_candles()`
- Line 245: `conn.close()` in `store_candles()`
- Line 275: `conn.close()` in `get_candles()`
- Line 299: `conn.close()` in `get_candles()`
- Line 324: `conn.close()` in `get_candles()`
- Line 337: `conn.close()` in `get_candles()`
- Line 355: `conn.close()` in `get_candles_for_analysis()`
- Line 369: `conn.close()` in `get_candles_for_analysis()`
- Line 394: `conn.close()` in `get_candles_for_analysis()`
- Line 412: `conn.close()` in `get_candles_for_analysis()`
- Line 435: `conn.close()` in `get_candles_for_analysis()`

**Problem**: When DB_TYPE='postgres', these calls don't return connections to the pool - they just close them, causing pool exhaustion.

**Also**: The `get_connection()` method in this file (line 103-117) uses direct `sqlite3.connect()` instead of the centralized layer for SQLite, and calls `get_db_connection()` (undefined) for PostgreSQL.

---

#### **2. `python/trading_bot/core/cleaner.py` - Missing Connection Release** 🔴

**Severity**: HIGH - Connection leak in `_log_cleanup_action()`

**Location**: Line 268
```python
db = self._db or get_connection()
# ... database operations ...
# NO release_connection() call!
```

**Problem**: If `self._db` is None, a fresh connection is obtained but never released. This causes connection pool exhaustion in PostgreSQL.

---

#### **3. Direct SQLite Imports in Non-Core Files** 🟡

**Severity**: MEDIUM - Violates centralized layer principle

**Files with direct `import sqlite3`**:
- `python/prompt_performance/core/ab_testing.py` - Uses context managers ✅ (safe)
- `python/prompt_performance/core/data_loader.py` - Direct connection creation ❌
- `python/prompt_performance/core/prompt_recommender_service.py` - Direct connection creation ❌
- `python/prompt_performance/tournament.py` - Direct connection creation ❌
- `python/trading_bot/core/data_agent.py` - Only for type hints ✅ (safe)
- `python/trading_bot/db/init_trading_db.py` - Initialization code ✅ (acceptable)
- `python/trading_bot/db/test_trading_db.py` - Test code ✅ (acceptable)
- `python/trading_bot/engine/trade_tracker.py` - Only for type hints ✅ (safe)
- `python/trading_bot/utils/get_trade_candles_bot_control.py` - Direct connection ❌

**Problem**: These files bypass the centralized layer, making them:
- Incompatible with PostgreSQL
- Unable to respect DB_TYPE environment variable
- Prone to connection management issues

---

#### **4. Hardcoded Database Paths** 🟡

**Severity**: MEDIUM - Reduces flexibility

**Locations**:
- `python/run_bot.py:89` - Hardcoded `"trading_bot/data/trading.db"`
- `python/prompt_performance/core/data_loader.py:22` - Hardcoded `"data/trading.db"`
- `python/prompt_performance/core/prompt_recommender_service.py:235` - Hardcoded `"data/trading.db"`

**Problem**: These should use centralized `DB_PATH` from `trading_bot.db.client`

---

#### **5. Inconsistent Connection Management Patterns** 🟡

**Severity**: MEDIUM - Inconsistent error handling

**Issues**:
- Some files use try/finally with `release_connection()` ✅
- Some files use context managers with `sqlite3.connect()` ✅
- Some files get connections but never release them ❌
- Some files use `conn.close()` instead of `release_connection()` ❌

**Pattern Inconsistency**:
```python
# Pattern 1: Correct (try/finally with release_connection)
conn = None
try:
    conn = get_connection()
    # operations
finally:
    if conn:
        release_connection(conn)

# Pattern 2: Correct (context manager for SQLite)
with sqlite3.connect(path) as conn:
    # operations

# Pattern 3: WRONG (direct close on PostgreSQL connection)
conn = get_connection()
# operations
conn.close()  # ❌ Doesn't return to pool!

# Pattern 4: WRONG (no release at all)
conn = get_connection()
# operations
# ❌ Connection leaked!
```

---

### **DB_TYPE RESPECT ANALYSIS** 📊

**Files Properly Respecting DB_TYPE**:
- ✅ `python/trading_bot/db/client.py` - Centralized layer
- ✅ `python/trading_bot/core/error_logger.py` - Uses centralized layer
- ✅ `python/trading_bot/core/slot_manager.py` - Uses centralized layer
- ✅ `python/trading_bot/core/sourcer.py` - Uses centralized layer + explicit DB_TYPE checks
- ✅ `python/trading_bot/core/state_manager.py` - Uses centralized layer
- ✅ `python/trading_bot/config/settings_v2.py` - Uses centralized layer
- ✅ `python/trading_bot/engine/trading_engine.py` - Uses centralized layer
- ✅ `python/trading_bot/engine/trading_cycle.py` - Uses centralized layer
- ✅ `python/trading_bot/engine/paper_trade_simulator.py` - Uses centralized layer

**Files NOT Respecting DB_TYPE**:
- ❌ `python/prompt_performance/core/database_utils.py` - Hardcoded SQLite, broken PostgreSQL support
- ❌ `python/prompt_performance/core/data_loader.py` - Hardcoded SQLite
- ❌ `python/prompt_performance/core/prompt_recommender_service.py` - Hardcoded SQLite
- ❌ `python/prompt_performance/core/ab_testing.py` - Hardcoded SQLite (but uses context managers)
- ❌ `python/prompt_performance/tournament.py` - Hardcoded SQLite
- ❌ `python/trading_bot/utils/get_trade_candles_bot_control.py` - Hardcoded SQLite

---

### **CONNECTION POOL EXHAUSTION RISK** 🚨

**High Risk Scenarios**:

1. **PostgreSQL with database_utils.py**: 15 `conn.close()` calls don't return connections to pool
2. **PostgreSQL with cleaner.py**: `_log_cleanup_action()` leaks connections
3. **Multiple instances running**: Each instance creates connections that aren't properly released
4. **Error conditions**: If exceptions occur before `release_connection()`, connections leak

**Impact**: 
- Pool exhaustion after ~100 operations (maxconn=100)
- "Connection pool exhausted" errors
- System becomes unresponsive
- Cascading failures across instances

---

### **SEPARATE DATABASE HANDLING** 📁

**Current Architecture**:
- **SQLite**: 
  - `data/trading.db` - Main trading data
  - `data/backtests.db` - Backtest data (separate file)
  - `data/candle_store.db` - Candle data (in database_utils.py)
  - `data/analysis.db` - Analysis data (in data_loader.py)

- **PostgreSQL**: 
  - Single database with table prefixes (bt_*, klines, etc.)
  - Handled by `get_table_name()` function

**Issue**: Multiple separate SQLite databases make it hard to maintain consistency and backups.

---

### **SUMMARY TABLE**

| Component | Status | Issues | Priority |
|-----------|--------|--------|----------|
| Centralized Layer (client.py) | ✅ Sound | None | - |
| Trading Bot Core | ✅ Good | None | - |
| Error Logger | ✅ Good | None | - |
| State Manager | ✅ Fixed | None | - |
| Data Agent | ✅ Fixed | None | - |
| Backtest Store | ✅ Fixed | None | - |
| Cleaner | ❌ Broken | Missing release_connection | HIGH |
| Database Utils | ❌ Broken | 15x conn.close(), broken PostgreSQL | HIGH |
| Data Loader | ❌ Broken | Direct SQLite, no DB_TYPE support | MEDIUM |
| Prompt Recommender | ❌ Broken | Direct SQLite, no DB_TYPE support | MEDIUM |
| Tournament | ❌ Broken | Direct SQLite, no DB_TYPE support | MEDIUM |
| AB Testing | ⚠️ Partial | Direct SQLite, but uses context managers | MEDIUM |

---

### **RECOMMENDATIONS**

**Immediate Fixes (CRITICAL)**:
1. Fix `database_utils.py` - Replace all 15 `conn.close()` with `release_connection()`
2. Fix `cleaner.py` - Add try/finally with `release_connection()` in `_log_cleanup_action()`

**Short-term Fixes (HIGH)**:
3. Refactor `data_loader.py` to use centralized layer
4. Refactor `prompt_recommender_service.py` to use centralized layer
5. Refactor `tournament.py` to use centralized layer
6. Refactor `get_trade_candles_bot_control.py` to use centralized layer

**Medium-term Improvements (MEDIUM)**:
7. Consolidate separate SQLite databases into single `trading.db`
8. Add comprehensive connection leak detection tests
9. Document connection management patterns for all developers


# Dashboard API - Reuse Strategy

## Existing Endpoints We Can Leverage

### 1. `/api/bot/stats` ✅ REUSE
- **Scope**: global, instance, run, cycle
- **Returns**: cycles, recommendations, trades, executions, win_rate, total_pnl
- **Use for Dashboard**: Overview section (global stats)
- **DB Functions**: `getGlobalStats()`, `getStatsByInstanceId()`, `getStatsByRunId()`, `getStatsByCycleId()`

### 2. `/api/bot/instances` ✅ REUSE
- **Scope**: all instances or single instance with summary
- **Returns**: instance list with status, config, summary data
- **Use for Dashboard**: System Health (active instances count, status)
- **DB Functions**: `getInstancesWithStatus()`, `getInstancesWithSummary()`

### 3. `/api/bot/positions` ✅ REUSE
- **Scope**: open positions, closed today, stats
- **Returns**: open_positions, closed_today, stats (live/dry run separated)
- **Use for Dashboard**: Position Management section
- **DB Functions**: `getRecentTrades()` with filtering

### 4. `/api/bot/trades` ✅ REUSE
- **Scope**: recent trades, by status, by instance, grouped by run
- **Returns**: trades array with stats (total, winning, losing, win_rate, total_pnl)
- **Use for Dashboard**: Symbol Performance, base data for calculations
- **DB Functions**: `getRecentTrades()`, `getTradesByStatus()`, `getTradesGroupedByRun()`

### 5. `/api/bot/cycles` ✅ REUSE
- **Scope**: cycle history, recommendations, current cycle analysis
- **Returns**: cycles, recommendations, analysis results, stats
- **Use for Dashboard**: Strategy performance (via recommendations)
- **DB Functions**: `getRecentCycles()`, `getRecentRecommendations()`

---

## New Dashboard Endpoints (Phase 1)

### 1. `/api/dashboard/overview` 
**Reuses**: `/api/bot/stats`, `/api/bot/instances`, `/api/bot/positions`
- Aggregate global stats
- Active instances count
- Total P&L, Win Rate
- Active positions count

### 2. `/api/dashboard/strategy-performance` ⭐ NEW
**DB Functions**: `dbQuery()` with GROUP BY strategy_type, timeframe
- Per strategy-timeframe metrics
- Advanced metrics: Sharpe, Expectancy, Profit Factor, Max Drawdown, Recovery Factor, Sortino
- Ranking and comparison

### 3. `/api/dashboard/symbol-performance`
**Reuses**: `/api/bot/trades` logic
- Per symbol metrics
- Win rate, P&L, trade count
- Best/worst performers

### 4. `/api/dashboard/position-sizing`
**Reuses**: `/api/bot/positions` logic
- Position size distribution
- Risk metrics
- Correlation with outcomes

### 5. `/api/dashboard/correlation-analysis` ⭐ NEW
**DB Functions**: `dbQuery()` with multiple aggregations
- Confidence vs Win Rate
- Position Size vs P&L
- Strategy consistency metrics

### 6. `/api/dashboard/ai-insights` ⭐ NEW
**Mock Data Initially**
- Top performers
- Risk alerts
- Recommendations
- Pattern insights

---

## Database Functions Available

### Query Functions
- `dbQuery<T>(sql, params)` - Execute SELECT, returns all rows
- `dbQueryOne<T>(sql, params)` - Execute SELECT, returns single row
- `dbExecute(sql, params)` - Execute INSERT/UPDATE/DELETE

### High-Level Functions
- `getRecentTrades(limit)` - Last N trades with timeframe
- `getTradesByStatus(status)` - Filter by status
- `getTradesGroupedByRun(instanceId?, limit)` - Hierarchical structure
- `getRecentCycles(limit, instanceId?)` - Recent cycles
- `getRecentRecommendations(limit, instanceId?)` - Recent recommendations
- `getGlobalStats()` - Global statistics
- `getStatsByInstanceId(instanceId)` - Instance statistics
- `getInstancesWithStatus()` - All instances with status
- `getInstancesWithSummary()` - Instances with stats + config

### Key Interfaces
- `TradeRow` - Complete trade data with strategy_type, strategy_name, timeframe, confidence, pnl
- `CycleRow` - Cycle data with metrics
- `RecommendationRow` - Recommendation data with strategy info
- `InstanceRow` - Instance configuration and status

---

## Implementation Priority

**Phase 1 (Core - Start Here)**
1. ✅ 1.1 - `/api/dashboard/overview` (reuse existing)
2. ⭐ 1.2 - `/api/dashboard/strategy-performance` (new, critical)
3. 1.3 - `/api/dashboard/symbol-performance` (reuse logic)
4. 1.4 - `/api/dashboard/position-sizing` (reuse logic)

**Phase 2 (Advanced)**
5. ⭐ 2.2 - `/api/dashboard/correlation-analysis` (new)

**Phase 3 (AI)**
6. ⭐ 3.1 - `/api/dashboard/ai-insights` (mock data)

---

## Key Metrics to Calculate

### Per Strategy-Timeframe
- Trade count, Win rate, Total P&L, Avg P&L
- Sharpe Ratio, Sortino Ratio, Expectancy
- Profit Factor, Max Drawdown, Recovery Factor
- Coefficient of Variation (consistency)
- Win/Loss Ratio

### Per Symbol
- Trade count, Win rate, Total P&L, Avg P&L
- Avg confidence, Best trade, Worst trade

### Position Sizing
- Avg position size, Min/Max, Distribution
- Avg risk amount, Avg risk percentage
- Correlation with P&L

### Correlation Analysis
- Confidence vs Win Rate (heatmap)
- Position Size vs P&L (scatter)
- Strategy consistency (radar)
- P&L distribution (box plot)


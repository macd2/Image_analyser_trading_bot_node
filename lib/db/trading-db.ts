/**
 * Trading Database Client - Supports SQLite and PostgreSQL
 *
 * Uses DB_TYPE env var to switch between:
 * - 'sqlite': Local SQLite file (development)
 * - 'postgres': Supabase PostgreSQL (production)
 */

import Database from 'better-sqlite3';
import { Pool, QueryResult } from 'pg';
import path from 'path';

export type DbType = 'sqlite' | 'postgres';

const DB_TYPE: DbType = (process.env.DB_TYPE as DbType) || 'sqlite';
// Unified data folder at project root: ./data/
const TRADING_DB_PATH = process.env.TRADING_DB_PATH || path.join(process.cwd(), 'data', 'trading.db');
const DATABASE_URL = process.env.DATABASE_URL || '';

// Database instances
let sqliteDb: Database.Database | null = null;
let pgPool: Pool | null = null;

/**
 * Get SQLite connection
 */
function getSqliteDb(): Database.Database {
  if (!sqliteDb) {
    sqliteDb = new Database(TRADING_DB_PATH, { readonly: false });
    sqliteDb.pragma('journal_mode = WAL');
  }
  return sqliteDb;
}

/**
 * Reset the PostgreSQL pool (called after fatal errors)
 */
function resetPgPool(): void {
  if (pgPool) {
    pgPool.end().catch(() => {}); // Ignore errors during cleanup
    pgPool = null;
  }
}

/**
 * Get PostgreSQL pool
 */
function getPgPool(): Pool {
  if (!pgPool) {
    pgPool = new Pool({
      connectionString: DATABASE_URL,
      ssl: { rejectUnauthorized: false },  // Required for Supabase connections
      // Connection pool settings for Supabase pooler stability
      max: 10,                    // Maximum connections in pool
      idleTimeoutMillis: 30000,   // Close idle connections after 30s
      connectionTimeoutMillis: 10000,  // Wait max 10s for connection
      allowExitOnIdle: true       // Allow process to exit when pool is idle
    });

    // Handle connection errors gracefully - reset pool on fatal errors
    pgPool.on('error', (err: Error & { code?: string }) => {
      console.error('[TradingDB] PostgreSQL pool error:', err.message);
      // Reset pool on fatal errors so next query creates a fresh pool
      // Include "DbHandler exited" and other connection termination errors
      const isFatalError =
        err.code === 'XX000' ||  // Internal error
        err.code === '57P01' ||  // admin_shutdown
        err.code === '57P02' ||  // crash_shutdown
        err.message?.includes('DbHandler exited') ||
        err.message?.includes('Connection terminated') ||
        err.message?.includes('ECONNREFUSED') ||
        err.message?.includes('ENOTFOUND');

      if (isFatalError) {
        console.warn('[TradingDB] Resetting pool due to fatal error');
        resetPgPool();
      }
    });
  }
  return pgPool;
}

/**
 * Convert ? placeholders to $1, $2, etc for PostgreSQL
 */
function convertPlaceholders(sql: string): string {
  let idx = 0;
  return sql.replace(/\?/g, () => `$${++idx}`);
}

/**
 * Get SQL expression for dry_run comparison
 * SQLite: dry_run = 0 or dry_run = 1
 * PostgreSQL: dry_run = false or dry_run = true
 */
function getDryRunComparison(isLive: boolean): string {
  if (DB_TYPE === 'postgres') {
    return isLive ? 't.dry_run = false' : 't.dry_run = true';
  } else {
    return isLive ? 't.dry_run = 0' : 't.dry_run = 1';
  }
}

// ============================================================
// UNIFIED DATABASE INTERFACE
// These async functions work with both SQLite and PostgreSQL
// ============================================================

/**
 * Execute PostgreSQL query with retry logic for pooler connection issues
 */
async function pgQueryWithRetry<T>(
  pool: Pool,
  sql: string,
  params: unknown[],
  maxRetries: number = 3
): Promise<T[]> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const result: QueryResult = await pool.query(sql, params);
      return result.rows as T[];
    } catch (err) {
      lastError = err as Error;
      const errorCode = (err as { code?: string }).code;
      const errorMsg = (err as Error).message || '';

      // Retryable errors:
      // XX000 = Internal error
      // 57P01 = admin_shutdown
      // 57P02 = crash_shutdown
      // 08006 = connection_failure
      // DbHandler exited = Supabase pooler issue
      // Connection terminated = Pool connection lost
      const isRetryable =
        ['XX000', '57P01', '57P02', '08006'].includes(errorCode || '') ||
        errorMsg.includes('DbHandler exited') ||
        errorMsg.includes('Connection terminated') ||
        errorMsg.includes('ECONNREFUSED') ||
        errorMsg.includes('ENOTFOUND');

      if (isRetryable && attempt < maxRetries) {
        console.warn(`[TradingDB] Connection error (${errorCode}): ${errorMsg}, retrying... (${attempt + 1}/${maxRetries})`);
        // Reset pool on connection errors to force fresh connection
        resetPgPool();
        // Wait before retry with exponential backoff
        await new Promise(resolve => setTimeout(resolve, 100 * Math.pow(2, attempt)));
        continue;
      }

      // Non-retryable error or max retries reached
      console.error(`[TradingDB] Query failed after ${maxRetries} retries:`, lastError?.message);
      throw err;
    }
  }

  throw lastError;
}

/**
 * Normalize database row - converts PostgreSQL types to match SQLite types
 * Handles:
 * - dry_run: boolean -> number conversion
 * - Date objects -> ISO string conversion
 */
function normalizeRow<T>(row: T): T {
  if (!row || typeof row !== 'object') {
    return row;
  }

  const normalized = { ...row } as any;

  // Convert PostgreSQL boolean to number (true -> 1, false -> 0)
  if (typeof normalized.dry_run === 'boolean') {
    normalized.dry_run = normalized.dry_run ? 1 : 0;
  }

  // Convert Date objects to ISO strings for all date fields
  const dateFields = [
    'created_at', 'updated_at', 'started_at', 'ended_at', 'completed_at',
    'submitted_at', 'filled_at', 'closed_at', 'fill_time', 'analyzed_at',
    'exec_time', 'timestamp', 'boundary_time'
  ];

  for (const field of dateFields) {
    if (field in normalized && normalized[field] instanceof Date) {
      normalized[field] = normalized[field].toISOString();
    }
  }

  return normalized;
}

/**
 * Execute a SELECT query - returns all rows
 */
export async function dbQuery<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T[]> {
  if (DB_TYPE === 'sqlite') {
    const db = getSqliteDb();
    return db.prepare(sql).all(...params) as T[];
  } else {
    const pool = getPgPool();
    const pgSql = convertPlaceholders(sql);
    const rows = await pgQueryWithRetry<T>(pool, pgSql, params);
    // Normalize PostgreSQL rows to match SQLite format
    return rows.map(row => normalizeRow(row));
  }
}

/**
 * Execute a SELECT query - returns single row or null
 */
export async function dbQueryOne<T = Record<string, unknown>>(sql: string, params: unknown[] = []): Promise<T | null> {
  const results = await dbQuery<T>(sql, params);
  return results[0] || null;
}

/**
 * Execute PostgreSQL command with retry logic (for INSERT/UPDATE/DELETE)
 */
async function pgExecuteWithRetry(
  pool: Pool,
  sql: string,
  params: unknown[],
  maxRetries: number = 3
): Promise<{ changes: number }> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const result: QueryResult = await pool.query(sql, params);
      return { changes: result.rowCount || 0 };
    } catch (err) {
      lastError = err as Error;
      const errorCode = (err as { code?: string }).code;
      const errorMsg = (err as Error).message || '';

      const isRetryable =
        ['XX000', '57P01', '57P02', '08006'].includes(errorCode || '') ||
        errorMsg.includes('DbHandler exited') ||
        errorMsg.includes('Connection terminated') ||
        errorMsg.includes('ECONNREFUSED') ||
        errorMsg.includes('ENOTFOUND');

      if (isRetryable && attempt < maxRetries) {
        console.warn(`[TradingDB] Connection error (${errorCode}), retrying execute... (${attempt + 1}/${maxRetries})`);
        // Reset pool on connection errors to force fresh connection
        resetPgPool();
        await new Promise(resolve => setTimeout(resolve, 100 * Math.pow(2, attempt)));
        continue;
      }

      throw err;
    }
  }

  throw lastError;
}

/**
 * Execute INSERT/UPDATE/DELETE - returns affected row count
 */
export async function dbExecute(sql: string, params: unknown[] = []): Promise<{ changes: number }> {
  if (DB_TYPE === 'sqlite') {
    const db = getSqliteDb();
    const result = db.prepare(sql).run(...params);
    return { changes: result.changes };
  } else {
    const pool = getPgPool();
    const pgSql = convertPlaceholders(sql);
    return pgExecuteWithRetry(pool, pgSql, params);
  }
}

// ============================================================
// LEGACY SYNC INTERFACE (SQLite only)
// Used by existing code - will throw in postgres mode
// ============================================================

/**
 * Get raw SQLite database - throws in PostgreSQL mode
 * @deprecated Use dbQuery/dbQueryOne/dbExecute instead
 */
export function getTradingDb(): Database.Database {
  if (DB_TYPE !== 'sqlite') {
    throw new Error('getTradingDb() only works in SQLite mode. Use dbQuery/dbQueryOne/dbExecute instead.');
  }
  return getSqliteDb();
}

/**
 * Check if trading database is available
 */
export async function isTradingDbAvailable(): Promise<boolean> {
  try {
    await dbQuery('SELECT 1');
    return true;
  } catch {
    return false;
  }
}

/**
 * Get current database type
 */
export function getDbType(): DbType {
  return DB_TYPE;
}

// ============================================================
// INSTANCES OPERATIONS (Bot configurations)
// ============================================================

export interface InstanceRow {
  id: string;
  name: string;
  prompt_name: string | null;
  prompt_version: string | null;
  min_confidence: number | null;
  max_leverage: number | null;
  symbols: string | null;  // JSON array
  timeframe: string | null;
  settings: string | null;  // JSON blob
  is_active: number;
  created_at: string;
  updated_at: string | null;
}

/**
 * Get all instances
 */
export async function getInstances(activeOnly: boolean = false): Promise<InstanceRow[]> {
  const sql = activeOnly
    ? 'SELECT * FROM instances WHERE is_active = true ORDER BY name'
    : 'SELECT * FROM instances ORDER BY name';
  return dbQuery<InstanceRow>(sql);
}

export interface InstanceWithStatus extends InstanceRow {
  is_running: boolean;
  current_run_id: string | null;
}

/**
 * Get all instances with their running status
 * Uses persistent process state to determine actual running status
 */
export async function getInstancesWithStatus(activeOnly: boolean = false): Promise<InstanceWithStatus[]> {
  // Import process state functions (dynamic import to avoid circular dependencies)
  const { getAllProcessStates, isProcessAlive } = await import('@/lib/process-state');

  // Get all running processes from persistent state
  const runningProcesses = getAllProcessStates();
  const runningInstanceIds = new Set(
    runningProcesses
      .filter(p => isProcessAlive(p.pid))
      .map(p => p.instanceId)
  );

  const sql = activeOnly
    ? `SELECT i.*,
         (SELECT r.id FROM runs r WHERE r.instance_id = i.id AND r.status = 'running' LIMIT 1) as current_run_id
       FROM instances i WHERE i.is_active = true ORDER BY i.name`
    : `SELECT i.*,
         (SELECT r.id FROM runs r WHERE r.instance_id = i.id AND r.status = 'running' LIMIT 1) as current_run_id
       FROM instances i ORDER BY i.name`;

  const instances = await dbQuery<Omit<InstanceWithStatus, 'is_running'>>(sql);

  // Add is_running based on actual process state
  return instances.map(instance => ({
    ...instance,
    is_running: runningInstanceIds.has(instance.id)
  }));
}

/**
 * Instance summary for card display - includes stats and config
 */
export interface InstanceSummary extends InstanceWithStatus {
  total_trades: number;
  live_trades: number;
  dry_run_trades: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  expected_value: number; // EV = (win_rate × avg_win) - (loss_rate × avg_loss)
  avg_win: number;
  avg_loss: number;
  config: {
    use_testnet: boolean;
    paper_trading: boolean;
  };
  running_duration_hours?: number;
  latest_cycle?: {
    charts_captured: number;
    recommendations_generated: number;
    trades_executed: number;
  };
  // NEW: Detailed breakdown for live vs dry
  live_closed: number;
  live_open: number;
  live_wins: number;
  live_losses: number;
  live_pnl: number;
  live_ev: number;
  dry_closed: number;
  dry_open: number;
  dry_wins: number;
  dry_losses: number;
  dry_pnl: number;
  dry_ev: number;
  // Signal quality metrics
  last_cycle_symbols: string[];
  actionable_percent: number;
  actionable_count: number;
  total_recs: number;
  avg_confidence: number;
  avg_risk_reward: number;
  // Recent logs (last 3)
  recent_logs: { timestamp: string; level: string; message: string }[];
}

/**
 * Get all instances with summary data (stats + config) for card display
 */
export async function getInstancesWithSummary(): Promise<InstanceSummary[]> {
  // Get instances with status
  const instances = await getInstancesWithStatus();

  const results: InstanceSummary[] = [];
  for (const instance of instances) {
    // Use DB-specific dry_run comparison (boolean for PostgreSQL, integer for SQLite)
    const liveComparison = getDryRunComparison(true);
    const dryComparison = getDryRunComparison(false);

    // Get detailed stats for both live and dry trades
    const stats = await dbQueryOne<{
      live_closed: number; live_open: number;
      live_wins: number; live_losses: number;
      live_pnl: number; live_avg_win: number; live_avg_loss: number;
      dry_closed: number; dry_open: number;
      dry_wins: number; dry_losses: number;
      dry_pnl: number; dry_avg_win: number; dry_avg_loss: number;
    }>(`
      SELECT
        COUNT(CASE WHEN ${liveComparison} AND t.status IN ('closed', 'filled') THEN 1 END) as live_closed,
        COUNT(CASE WHEN ${liveComparison} AND t.status IN ('pending', 'submitted', 'pending_fill') THEN 1 END) as live_open,
        COUNT(CASE WHEN ${liveComparison} AND t.status IN ('closed', 'filled') AND t.pnl > 0 THEN 1 END) as live_wins,
        COUNT(CASE WHEN ${liveComparison} AND t.status IN ('closed', 'filled') AND t.pnl < 0 THEN 1 END) as live_losses,
        COALESCE(SUM(CASE WHEN ${liveComparison} AND t.pnl IS NOT NULL THEN t.pnl ELSE 0 END), 0) as live_pnl,
        COALESCE(AVG(CASE WHEN ${liveComparison} AND t.pnl > 0 THEN t.pnl END), 0) as live_avg_win,
        COALESCE(AVG(CASE WHEN ${liveComparison} AND t.pnl < 0 THEN ABS(t.pnl) END), 0) as live_avg_loss,
        COUNT(CASE WHEN ${dryComparison} AND t.status IN ('closed', 'filled') THEN 1 END) as dry_closed,
        COUNT(CASE WHEN ${dryComparison} AND t.status IN ('pending', 'submitted', 'pending_fill', 'paper_trade') THEN 1 END) as dry_open,
        COUNT(CASE WHEN ${dryComparison} AND t.status IN ('closed', 'filled') AND t.pnl > 0 THEN 1 END) as dry_wins,
        COUNT(CASE WHEN ${dryComparison} AND t.status IN ('closed', 'filled') AND t.pnl < 0 THEN 1 END) as dry_losses,
        COALESCE(SUM(CASE WHEN ${dryComparison} AND t.pnl IS NOT NULL THEN t.pnl ELSE 0 END), 0) as dry_pnl,
        COALESCE(AVG(CASE WHEN ${dryComparison} AND t.pnl > 0 THEN t.pnl END), 0) as dry_avg_win,
        COALESCE(AVG(CASE WHEN ${dryComparison} AND t.pnl < 0 THEN ABS(t.pnl) END), 0) as dry_avg_loss
      FROM trades t
      JOIN cycles c ON t.cycle_id = c.id
      JOIN runs r ON c.run_id = r.id
      WHERE r.instance_id = ?
    `, [instance.id]) || {
      live_closed: 0, live_open: 0, live_wins: 0, live_losses: 0, live_pnl: 0, live_avg_win: 0, live_avg_loss: 0,
      dry_closed: 0, dry_open: 0, dry_wins: 0, dry_losses: 0, dry_pnl: 0, dry_avg_win: 0, dry_avg_loss: 0
    };

    // Parse instance settings (PostgreSQL returns JSONB as object, SQLite returns string)
    let instanceSettings: Record<string, unknown> = {};
    if (instance.settings) {
      if (typeof instance.settings === 'string') {
        try { instanceSettings = JSON.parse(instance.settings); } catch { /* ignore */ }
      } else if (typeof instance.settings === 'object') {
        instanceSettings = instance.settings as Record<string, unknown>;
      }
    }

    // Ensure numeric types (PostgreSQL returns strings)
    const liveClosed = Number(stats.live_closed) || 0;
    const liveOpen = Number(stats.live_open) || 0;
    const liveWins = Number(stats.live_wins) || 0;
    const liveLosses = Number(stats.live_losses) || 0;
    const livePnl = Number(stats.live_pnl) || 0;
    const liveAvgWin = Number(stats.live_avg_win) || 0;
    const liveAvgLoss = Number(stats.live_avg_loss) || 0;
    const dryClosed = Number(stats.dry_closed) || 0;
    const dryOpen = Number(stats.dry_open) || 0;
    const dryWins = Number(stats.dry_wins) || 0;
    const dryLosses = Number(stats.dry_losses) || 0;
    const dryPnl = Number(stats.dry_pnl) || 0;
    const dryAvgWin = Number(stats.dry_avg_win) || 0;
    const dryAvgLoss = Number(stats.dry_avg_loss) || 0;

    // Calculate EV for live trades
    const liveTotal = liveWins + liveLosses;
    const liveWinDec = liveTotal > 0 ? liveWins / liveTotal : 0;
    const liveLossDec = liveTotal > 0 ? liveLosses / liveTotal : 0;
    const liveEv = (liveWinDec * liveAvgWin) - (liveLossDec * liveAvgLoss);

    // Calculate EV for dry trades
    const dryTotal = dryWins + dryLosses;
    const dryWinDec = dryTotal > 0 ? dryWins / dryTotal : 0;
    const dryLossDec = dryTotal > 0 ? dryLosses / dryTotal : 0;
    const dryEv = (dryWinDec * dryAvgWin) - (dryLossDec * dryAvgLoss);

    // Overall stats (live + dry)
    const totalWins = liveWins + dryWins;
    const totalLosses = liveLosses + dryLosses;
    const totalClosed = totalWins + totalLosses;
    const winRate = totalClosed > 0 ? (totalWins / totalClosed) * 100 : 0;
    const totalPnl = livePnl + dryPnl;
    const avgWin = (liveAvgWin + dryAvgWin) / 2 || liveAvgWin || dryAvgWin;
    const avgLoss = (liveAvgLoss + dryAvgLoss) / 2 || liveAvgLoss || dryAvgLoss;
    const winDec = totalClosed > 0 ? totalWins / totalClosed : 0;
    const lossDec = totalClosed > 0 ? totalLosses / totalClosed : 0;
    const expectedValue = (winDec * avgWin) - (lossDec * avgLoss);

    // Config
    const useTestnet = instanceSettings['bybit.use_testnet'] === 'true' || instanceSettings['bybit.use_testnet'] === true;
    const paperTrading = instanceSettings['trading.paper_trading'] === 'true' || instanceSettings['trading.paper_trading'] === true;

    // Running duration
    let runningDurationHours: number | undefined;
    if (instance.is_running && instance.current_run_id) {
      const runInfo = await dbQueryOne<{ started_at: string }>(`SELECT started_at FROM runs WHERE id = ?`, [instance.current_run_id]);
      if (runInfo) runningDurationHours = (Date.now() - new Date(runInfo.started_at).getTime()) / (1000 * 60 * 60);
    }

    // Latest cycle metrics + symbols
    let latestCycle: { charts_captured: number; recommendations_generated: number; trades_executed: number } | undefined;
    let lastCycleSymbols: string[] = [];
    if (instance.current_run_id) {
      const cycleInfo = await dbQueryOne<{ id: string; charts_captured: number; recommendations_generated: number; trades_executed: number }>(`
        SELECT id, charts_captured, recommendations_generated, trades_executed FROM cycles WHERE run_id = ? ORDER BY started_at DESC LIMIT 1
      `, [instance.current_run_id]);
      if (cycleInfo) {
        latestCycle = { charts_captured: Number(cycleInfo.charts_captured) || 0, recommendations_generated: Number(cycleInfo.recommendations_generated) || 0, trades_executed: Number(cycleInfo.trades_executed) || 0 };
        // Get unique symbols from last cycle's recommendations
        const symbols = await dbQuery<{ symbol: string }>(`SELECT DISTINCT symbol FROM recommendations WHERE cycle_id = ?`, [cycleInfo.id]);
        lastCycleSymbols = symbols.map(s => s.symbol);
      }
    }

    // Signal quality metrics (from recommendations in current run)
    // Actionable = recs that meet min_confidence and min_rr thresholds from settings
    let actionablePercent = 0, actionableCount = 0, totalRecs = 0, avgConfidence = 0, avgRiskReward = 0;
    const minConfidence = Number(instanceSettings['trading.min_confidence']) || 0.6;
    const minRR = Number(instanceSettings['trading.min_rr']) || 1.5;
    if (instance.current_run_id) {
      const recStats = await dbQueryOne<{ total: number; actionable: number; avg_conf: number; avg_rr: number }>(`
        SELECT
          COUNT(*) as total,
          COUNT(CASE WHEN recommendation != 'hold' AND confidence >= ? AND risk_reward >= ? THEN 1 END) as actionable,
          AVG(confidence) as avg_conf,
          AVG(risk_reward) as avg_rr
        FROM recommendations r JOIN cycles c ON r.cycle_id = c.id WHERE c.run_id = ?
      `, [minConfidence, minRR, instance.current_run_id]);
      if (recStats) {
        totalRecs = Number(recStats.total) || 0;
        actionableCount = Number(recStats.actionable) || 0;
        avgConfidence = Number(recStats.avg_conf) || 0;
        avgRiskReward = Number(recStats.avg_rr) || 0;
        actionablePercent = totalRecs > 0 ? (actionableCount / totalRecs) * 100 : 0;
      }
    }

    // Recent logs (last 3)
    const recentLogs = await dbQuery<{ timestamp: string; level: string; message: string }>(`
      SELECT timestamp, level, message FROM error_logs el
      LEFT JOIN runs r ON el.run_id = r.id
      WHERE r.instance_id = ?
      ORDER BY el.timestamp DESC LIMIT 3
    `, [instance.id]);

    results.push({
      ...instance,
      total_trades: liveClosed + liveOpen + dryClosed + dryOpen,
      live_trades: liveClosed + liveOpen,
      dry_run_trades: dryClosed + dryOpen,
      total_pnl: totalPnl,
      win_count: totalWins,
      loss_count: totalLosses,
      win_rate: winRate,
      expected_value: expectedValue,
      avg_win: avgWin,
      avg_loss: avgLoss,
      config: { use_testnet: useTestnet, paper_trading: paperTrading },
      running_duration_hours: runningDurationHours,
      latest_cycle: latestCycle,
      // NEW fields
      live_closed: liveClosed, live_open: liveOpen, live_wins: liveWins, live_losses: liveLosses, live_pnl: livePnl, live_ev: liveEv,
      dry_closed: dryClosed, dry_open: dryOpen, dry_wins: dryWins, dry_losses: dryLosses, dry_pnl: dryPnl, dry_ev: dryEv,
      last_cycle_symbols: lastCycleSymbols,
      actionable_percent: actionablePercent, actionable_count: actionableCount, total_recs: totalRecs, avg_confidence: avgConfidence, avg_risk_reward: avgRiskReward,
      recent_logs: recentLogs,
    });
  }
  return results;
}

/**
 * Get instance by ID
 */
export async function getInstanceById(id: string): Promise<InstanceRow | null> {
  return dbQueryOne<InstanceRow>('SELECT * FROM instances WHERE id = ?', [id]);
}

/**
 * Create a new instance
 */
export async function createInstance(instance: Omit<InstanceRow, 'created_at' | 'updated_at'>): Promise<string> {
  await dbExecute(`
    INSERT INTO instances (id, name, prompt_name, prompt_version, min_confidence, max_leverage, symbols, timeframe, settings, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `, [
    instance.id,
    instance.name,
    instance.prompt_name,
    instance.prompt_version,
    instance.min_confidence,
    instance.max_leverage,
    instance.symbols,
    instance.timeframe,
    instance.settings,
    instance.is_active
  ]);
  return instance.id;
}

/**
 * Update an instance
 */
export async function updateInstance(id: string, updates: Partial<InstanceRow>): Promise<boolean> {
  const fields: string[] = [];
  const values: unknown[] = [];

  if (updates.name !== undefined) { fields.push('name = ?'); values.push(updates.name); }
  if (updates.prompt_name !== undefined) { fields.push('prompt_name = ?'); values.push(updates.prompt_name); }
  if (updates.prompt_version !== undefined) { fields.push('prompt_version = ?'); values.push(updates.prompt_version); }
  if (updates.min_confidence !== undefined) { fields.push('min_confidence = ?'); values.push(updates.min_confidence); }
  if (updates.max_leverage !== undefined) { fields.push('max_leverage = ?'); values.push(updates.max_leverage); }
  if (updates.symbols !== undefined) { fields.push('symbols = ?'); values.push(updates.symbols); }
  if (updates.timeframe !== undefined) { fields.push('timeframe = ?'); values.push(updates.timeframe); }
  if (updates.settings !== undefined) { fields.push('settings = ?'); values.push(updates.settings); }
  if (updates.is_active !== undefined) { fields.push('is_active = ?'); values.push(updates.is_active); }

  if (fields.length === 0) return false;

  // Use NOW() for PostgreSQL, datetime('now') for SQLite
  const nowExpr = DB_TYPE === 'postgres' ? 'NOW()' : "datetime('now')";
  fields.push(`updated_at = ${nowExpr}`);
  values.push(id);

  const result = await dbExecute(`UPDATE instances SET ${fields.join(', ')} WHERE id = ?`, values);
  return result.changes > 0;
}

/**
 * Get instance settings as parsed config object
 */
export async function getInstanceSettings(instanceId: string): Promise<Record<string, unknown> | null> {
  const instance = await getInstanceById(instanceId);
  if (!instance) return null;

  try {
    const settings = instance.settings ? JSON.parse(instance.settings) : {};
    // Also include top-level instance fields as config
    return {
      ...settings,
      'trading.timeframe': instance.timeframe,
      'trading.min_confidence_threshold': instance.min_confidence,
      'trading.leverage': instance.max_leverage,
    };
  } catch {
    return null;
  }
}

/**
 * Update instance settings (merge with existing)
 */
export async function updateInstanceSettings(instanceId: string, updates: Array<{ key: string; value: string }>): Promise<boolean> {
  const instance = await getInstanceById(instanceId);
  if (!instance) return false;

  // Parse existing settings - handle both string (SQLite) and object (PostgreSQL JSONB) formats
  let settings: Record<string, string> = {};
  try {
    if (instance.settings) {
      if (typeof instance.settings === 'string') {
        settings = JSON.parse(instance.settings);
      } else if (typeof instance.settings === 'object') {
        settings = instance.settings as Record<string, string>;
      }
    }
  } catch {
    settings = {};
  }

  // Track top-level field updates
  let timeframe = instance.timeframe;
  let min_confidence = instance.min_confidence;
  let max_leverage = instance.max_leverage;

  // Apply updates
  for (const { key, value } of updates) {
    // Some keys map to top-level instance fields
    if (key === 'trading.timeframe') {
      timeframe = value;
    } else if (key === 'trading.min_confidence_threshold') {
      min_confidence = parseFloat(value);
    } else if (key === 'trading.leverage') {
      max_leverage = parseInt(value, 10);
    }
    // Always store in settings JSON too
    settings[key] = value;
  }

  // Use NOW() for PostgreSQL, datetime('now') for SQLite
  const nowExpr = DB_TYPE === 'postgres' ? 'NOW()' : "datetime('now')";
  const result = await dbExecute(`
    UPDATE instances
    SET settings = ?, timeframe = ?, min_confidence = ?, max_leverage = ?, updated_at = ${nowExpr}
    WHERE id = ?
  `, [JSON.stringify(settings), timeframe, min_confidence, max_leverage, instanceId]);

  return result.changes > 0;
}

// Static config metadata (type, category, description, tooltip, group) for known settings
// group is used to visually group related settings together in the UI
// Groups starting with "1.", "2.", etc. are sorted in that order
// Groups with "├─" or "└─" are displayed as child groups (indented)
type ConfigMeta = { type: 'string' | 'number' | 'boolean' | 'json'; category: string; description: string; tooltip?: string; group?: string; order?: number };
const CONFIG_METADATA: Record<string, ConfigMeta> = {
  // AI Settings
  'openai.assistant_id': { type: 'string', category: 'ai', group: '1. Model Configuration', description: 'OpenAI Assistant ID', tooltip: 'The unique identifier for your OpenAI Assistant', order: 1 },
  'openai.model': { type: 'string', category: 'ai', group: '1. Model Configuration', description: 'OpenAI Model', tooltip: 'AI model to use for analysis (e.g., gpt-4, gpt-3.5-turbo)', order: 2 },

  // Exchange Settings
  'bybit.use_testnet': { type: 'boolean', category: 'exchange', group: '1. Connection', description: 'Use Bybit testnet', tooltip: 'Connect to Bybit testnet instead of mainnet', order: 1 },
  'bybit.max_retries': { type: 'number', category: 'exchange', group: '2. API Settings', description: 'Max retries for API calls', tooltip: 'Number of times to retry failed API requests', order: 10 },
  'bybit.recv_window': { type: 'number', category: 'exchange', group: '2. API Settings', description: 'Receive window in ms', tooltip: 'Time window for API request validity (milliseconds)', order: 11 },

  // Trading - Core
  'trading.paper_trading': { type: 'boolean', category: 'trading', group: '1. Core', description: 'Paper trading mode', tooltip: 'Simulate trades without real money (dry run mode for testing strategies)', order: 1 },
  'trading.auto_approve_trades': { type: 'boolean', category: 'trading', group: '1. Core', description: 'Auto-approve trades', tooltip: 'Automatically execute trades without manual approval (use with caution in live trading)', order: 2 },
  'trading.max_concurrent_trades': { type: 'number', category: 'trading', group: '1. Core', description: 'Max concurrent trades', tooltip: 'Maximum number of positions/orders that can be open at the same time', order: 4 },

  // Trading - Risk Management
  'trading.leverage': { type: 'number', category: 'trading', group: '2. Risk Management', description: 'Trading leverage', tooltip: 'Leverage multiplier for positions (e.g., 2 = 2x leverage). Higher leverage = higher risk', order: 10 },
  'trading.risk_percentage': { type: 'number', category: 'trading', group: '2. Risk Management', description: 'Risk percentage per trade', tooltip: 'Percentage of account balance to risk per trade (e.g., 0.01 = 1% of balance)', order: 11 },
  'trading.max_loss_usd': { type: 'number', category: 'trading', group: '2. Risk Management', description: 'Max loss per trade in USD', tooltip: 'Maximum dollar amount to risk on a single trade (hard cap on position size)', order: 12 },
  'trading.min_rr': { type: 'number', category: 'trading', group: '2. Risk Management', description: 'Minimum risk:reward ratio', tooltip: 'Minimum Risk:Reward ratio required for a trade (e.g., 1.7 = must have at least 1.7R potential profit)', order: 13 },
  'trading.min_confidence_threshold': { type: 'number', category: 'trading', group: '2. Risk Management', description: 'Min confidence threshold', tooltip: 'Minimum AI confidence score required to take a trade (0.0-1.0, e.g., 0.75 = 75% confidence)', order: 14 },

  // Trading - Position Sizing
  'trading.use_enhanced_position_sizing': { type: 'boolean', category: 'trading', group: '3. Position Sizing', description: 'Use enhanced position sizing', tooltip: 'Use confidence-weighted position sizing instead of fixed risk percentage', order: 20 },
  'trading.min_position_value_usd': { type: 'number', category: 'trading', group: '3. Position Sizing', description: 'Minimum position value in USD', tooltip: 'Minimum USD value for any position to prevent dust trades', order: 21 },

  // Trading - Order Replacement
  'trading.enable_intelligent_replacement': { type: 'boolean', category: 'trading', group: '4. Order Replacement', description: 'Enable intelligent order replacement', tooltip: 'Replace existing orders with better opportunities based on AI score improvement', order: 30 },
  'trading.min_score_improvement_threshold': { type: 'number', category: 'trading', group: '4. Order Replacement', description: 'Min score improvement for replacement', tooltip: 'Minimum AI confidence score improvement required to replace an existing order (0.0-1.0)', order: 31 },

  // Trade Monitor - Master Control (Level 1)
  'trading.enable_position_tightening': { type: 'boolean', category: 'trade monitor', group: '1. Master Control', description: 'Master tightening switch', tooltip: '🔴 MASTER SWITCH: Disables ALL tightening mechanisms below when OFF (RR, TP proximity, age-based, ADX)', order: 1 },

  // Trade Monitor - RR-based Tightening (Level 2 - controlled by master)
  'trading.enable_sl_tightening': { type: 'boolean', category: 'trade monitor', group: '2. ├─ RR Tightening', description: 'RR-based tightening', tooltip: 'Tighten stop loss as profit increases based on Risk:Reward ratio thresholds (e.g., at 2R move SL to 1.2R)', order: 10 },
  'trading.rr_tightening_steps': { type: 'json', category: 'trade monitor', group: '2. ├─ RR Tightening', description: 'RR tightening steps', tooltip: 'Define profit thresholds and new SL positions. Example: {"2R": {"threshold": 2.0, "sl_position": 1.2}}', order: 11 },

  // Trade Monitor - TP Proximity Trailing (Level 2 - controlled by master)
  'trading.enable_tp_proximity_trailing': { type: 'boolean', category: 'trade monitor', group: '2. ├─ TP Proximity', description: 'TP proximity trailing', tooltip: 'Convert SL to trailing stop when price gets close to take profit target', order: 20 },
  'trading.tp_proximity_threshold_pct': { type: 'number', category: 'trade monitor', group: '2. ├─ TP Proximity', description: 'TP proximity threshold %', tooltip: 'Activate trailing stop when within X% of take profit (e.g., 1.0 = activate when 1% away from TP)', order: 21 },
  'trading.tp_proximity_trailing_pct': { type: 'number', category: 'trade monitor', group: '2. ├─ TP Proximity', description: 'TP proximity trailing %', tooltip: 'Trail stop loss X% behind current price once activated (e.g., 1.0 = trail 1% behind price)', order: 22 },

  // Trade Monitor - Age-based Tightening (Level 2 - controlled by master)
  'trading.age_tightening_enabled': { type: 'boolean', category: 'trade monitor', group: '2. ├─ Age Tightening', description: 'Age-based tightening', tooltip: 'Tighten stop loss for unprofitable positions that have been open too long (time-based risk reduction)', order: 30 },
  'trading.age_tightening_max_pct': { type: 'number', category: 'trade monitor', group: '2. ├─ Age Tightening', description: 'Max age tightening %', tooltip: 'Maximum percentage to tighten SL (e.g., 30 = tighten up to 30% of original risk distance)', order: 31 },
  'trading.age_tightening_min_profit_threshold': { type: 'number', category: 'trade monitor', group: '2. ├─ Age Tightening', description: 'Min profit threshold (R)', tooltip: 'Only apply age-based tightening if profit is below this level in R (e.g., 1.0 = only tighten if below 1R profit)', order: 32 },
  'trading.age_tightening_bars': { type: 'json', category: 'trade monitor', group: '2. ├─ Age Tightening', description: 'Age tightening bars', tooltip: 'Number of bars before tightening per timeframe. Example: {"1h": 48, "4h": 18, "1d": 4}', order: 33 },

  // Trade Monitor - ADX Tightening (Level 2 - controlled by master, not implemented)
  'trading.enable_adx_tightening': { type: 'boolean', category: 'trade monitor', group: '2. └─ ADX Tightening', description: 'ADX-based tightening', tooltip: '⚠️ NOT YET IMPLEMENTED - Will tighten stops based on ADX trend strength and ATR volatility', order: 40 },

  // Trade Monitor - Age-based Cancellation (Independent - NOT controlled by master)
  'trading.age_cancellation_enabled': { type: 'boolean', category: 'trade monitor', group: '3. Order Cancellation', description: 'Age-based cancellation', tooltip: '⚡ INDEPENDENT: Cancel unfilled orders that have been pending too long (not affected by master switch)', order: 50 },
  'trading.age_cancellation_max_bars': { type: 'json', category: 'trade monitor', group: '3. Order Cancellation', description: 'Max age bars for cancellation', tooltip: 'Maximum bars before cancelling unfilled orders per timeframe. Example: {"1h": 48, "4h": 18}', order: 51 },

  // TradingView - Chart Capture (under Trading category)
  'tradingview.enabled': { type: 'boolean', category: 'Tradingview', group: '5. Chart Capture', description: 'Enable TradingView chart capture', tooltip: 'Capture charts from TradingView for analysis', order: 40 },
  'tradingview.target_chart': { type: 'string', category: 'Tradingview', group: '5. Chart Capture', description: 'Target chart URL or identifier', tooltip: 'The TradingView chart URL or identifier to capture (e.g., "BTCUSDT" or full URL)', order: 41 },
  'trading.timeframe': { type: 'string', category: 'Tradingview', group: '5. Chart Capture', description: 'Trading timeframe', tooltip: 'Chart timeframe for analysis (e.g., 1h, 4h, 1d). Affects candle data and age-based calculations', order: 42 },

};

/**
 * Get instance config as ConfigRow array (for API compatibility)
 * Returns ALL keys from CONFIG_METADATA, with values only if present in instance settings
 */
export async function getInstanceConfigAsRows(instanceId: string): Promise<ConfigRow[]> {
  const instance = await getInstanceById(instanceId);
  if (!instance) return [];

  try {
    // Handle both string (SQLite) and object (PostgreSQL JSONB) formats
    let settings: Record<string, unknown> = {};
    if (instance.settings) {
      if (typeof instance.settings === 'string') {
        settings = JSON.parse(instance.settings);
      } else if (typeof instance.settings === 'object') {
        settings = instance.settings as Record<string, unknown>;
      }
    }
    const rows: ConfigRow[] = [];

    // Iterate over ALL keys in CONFIG_METADATA to show all possible settings
    for (const [key, meta] of Object.entries(CONFIG_METADATA)) {
      const instanceValue = settings[key];
      const hasValue = instanceValue !== undefined;

      rows.push({
        key,
        value: hasValue
          ? (typeof instanceValue === 'string' ? instanceValue : JSON.stringify(instanceValue))
          : '',  // Empty string if not set
        hasValue,
        type: meta.type,
        category: meta.category,
        group: meta.group || null,
        order: meta.order || 999,
        description: meta.description || null,
        tooltip: meta.tooltip || null,
        updated_at: instance.updated_at || new Date().toISOString(),
      });
    }

    // Sort by category, then group, then order
    return rows.sort((a, b) => {
      const catCompare = a.category.localeCompare(b.category);
      if (catCompare !== 0) return catCompare;
      const groupA = a.group || '';
      const groupB = b.group || '';
      const groupCompare = groupA.localeCompare(groupB);
      if (groupCompare !== 0) return groupCompare;
      return (a.order || 999) - (b.order || 999);
    });
  } catch {
    return [];
  }
}

// ============================================================
// RUNS OPERATIONS (Bot session tracking)
// ============================================================

export interface RunRow {
  id: string;
  instance_id: string | null;  // Links to parent instance
  started_at: string;
  ended_at: string | null;
  status: 'running' | 'stopped' | 'crashed' | 'completed';
  stop_reason: string | null;
  timeframe: string | null;
  paper_trading: number;
  min_confidence: number | null;
  max_leverage: number | null;
  symbols_watched: string | null;
  config_snapshot: string | null;
  total_cycles: number;
  total_recommendations: number;
  total_trades: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
  created_at: string;
}

/**
 * Get runs by instance ID
 */
export async function getRunsByInstanceId(instanceId: string, limit: number = 20): Promise<RunRow[]> {
  return dbQuery<RunRow>(`
    SELECT * FROM runs
    WHERE instance_id = ?
    ORDER BY started_at DESC
    LIMIT ?
  `, [instanceId, limit]);
}

/**
 * Get all runs
 */
export async function getRuns(limit: number = 20): Promise<RunRow[]> {
  return dbQuery<RunRow>(`
    SELECT * FROM runs
    ORDER BY started_at DESC
    LIMIT ?
  `, [limit]);
}

/**
 * Get run by ID
 */
export async function getRunById(id: string): Promise<RunRow | null> {
  return dbQueryOne<RunRow>('SELECT * FROM runs WHERE id = ?', [id]);
}

/**
 * Update run status and optionally set end time
 */
export async function updateRunStatus(
  runId: string,
  status: 'running' | 'stopped' | 'crashed' | 'completed',
  stopReason?: string
): Promise<void> {
  const endedAt = status !== 'running' ? new Date().toISOString() : null;

  await dbExecute(`
    UPDATE runs
    SET status = ?, ended_at = COALESCE(?, ended_at), stop_reason = COALESCE(?, stop_reason)
    WHERE id = ?
  `, [status, endedAt, stopReason, runId]);
}

/**
 * Get currently running runs (to sync with actual processes)
 */
export async function getRunningRuns(): Promise<RunRow[]> {
  return dbQuery<RunRow>(`SELECT * FROM runs WHERE status = 'running'`);
}

/**
 * Get the running run for a specific instance (if any)
 */
export async function getRunningRunByInstanceId(instanceId: string): Promise<RunRow | null> {
  return dbQueryOne<RunRow>(`SELECT * FROM runs WHERE instance_id = ? AND status = 'running' LIMIT 1`, [instanceId]);
}

/**
 * Update all running runs for an instance to a new status
 */
export async function updateRunStatusByInstanceId(
  instanceId: string,
  status: 'running' | 'stopped' | 'crashed' | 'completed',
  stopReason?: string
): Promise<number> {
  const endedAt = status !== 'running' ? new Date().toISOString() : null;

  const result = await dbExecute(`
    UPDATE runs
    SET status = ?, ended_at = COALESCE(?, ended_at), stop_reason = COALESCE(?, stop_reason)
    WHERE instance_id = ? AND status = 'running'
  `, [status, endedAt, stopReason, instanceId]);

  return result.changes;
}

/**
 * Get cycles for a specific run
 */
export async function getCyclesByRunId(runId: string): Promise<CycleRow[]> {
  return dbQuery<CycleRow>(`
    SELECT * FROM cycles
    WHERE run_id = ?
    ORDER BY started_at DESC
  `, [runId]);
}

// ============================================================
// CONFIG OPERATIONS
// ============================================================

export interface ConfigRow {
  key: string;
  value: string;
  hasValue: boolean;  // true if value is from instance settings, false if placeholder
  type: 'string' | 'number' | 'boolean' | 'json';
  category: string;
  group?: string | null;  // For grouping related settings in UI
  order?: number;  // For ordering within group
  description: string | null;
  tooltip?: string | null;
  updated_at: string;
}

// ============================================================
// TRADES OPERATIONS
// ============================================================

export interface TradeRow {
  id: string;
  recommendation_id: string | null;
  run_id: string | null;      // Direct link to run for fast queries
  cycle_id: string | null;    // Direct link to cycle for fast queries
  symbol: string;
  side: string;
  entry_price: number;
  quantity: number;
  stop_loss: number;
  take_profit: number;
  leverage: number;
  order_id: string | null;
  order_link_id: string | null;
  status: string;
  fill_price: number | null;
  fill_quantity: number | null;
  fill_time: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  pnl: number | null;
  pnl_percent: number | null;
  timeframe: string | null;
  prompt_name: string | null;
  confidence: number | null;
  rr_ratio: number | null;
  dry_run: number;
  rejection_reason: string | null;  // Why trade was rejected (if status='rejected')
  submitted_at: string | null;
  filled_at: string | null;
  closed_at: string | null;
  created_at: string;
}

/**
 * Get recent trades with timeframe from recommendations if not set on trade
 */
export async function getRecentTrades(limit: number = 50): Promise<TradeRow[]> {
  return dbQuery<TradeRow>(`
    SELECT
      t.*,
      COALESCE(t.timeframe, r.timeframe) as timeframe,
      COALESCE(t.entry_price, r.entry_price) as entry_price,
      COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
      COALESCE(t.take_profit, r.take_profit) as take_profit
    FROM trades t
    LEFT JOIN recommendations r ON t.recommendation_id = r.id
    ORDER BY t.created_at DESC
    LIMIT ?
  `, [limit]);
}

/**
 * Get trades by status with timeframe from recommendations if not set on trade
 */
export async function getTradesByStatus(status: string): Promise<TradeRow[]> {
  return dbQuery<TradeRow>(`
    SELECT
      t.*,
      COALESCE(t.timeframe, r.timeframe) as timeframe,
      COALESCE(t.entry_price, r.entry_price) as entry_price,
      COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
      COALESCE(t.take_profit, r.take_profit) as take_profit
    FROM trades t
    LEFT JOIN recommendations r ON t.recommendation_id = r.id
    WHERE t.status = ?
    ORDER BY t.created_at DESC
  `, [status]);
}

/**
 * Get trades by run ID
 */
export async function getTradesByRunId(runId: string): Promise<TradeRow[]> {
  return dbQuery<TradeRow>(`
    SELECT
      t.*,
      COALESCE(t.timeframe, r.timeframe) as timeframe,
      COALESCE(t.entry_price, r.entry_price) as entry_price,
      COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
      COALESCE(t.take_profit, r.take_profit) as take_profit
    FROM trades t
    LEFT JOIN recommendations r ON t.recommendation_id = r.id
    WHERE t.run_id = ?
    ORDER BY t.created_at DESC
  `, [runId]);
}

/**
 * Get trades by cycle ID
 */
export async function getTradesByCycleId(cycleId: string): Promise<TradeRow[]> {
  return dbQuery<TradeRow>(`
    SELECT
      t.*,
      COALESCE(t.timeframe, r.timeframe) as timeframe,
      COALESCE(t.entry_price, r.entry_price) as entry_price,
      COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
      COALESCE(t.take_profit, r.take_profit) as take_profit
    FROM trades t
    LEFT JOIN recommendations r ON t.recommendation_id = r.id
    WHERE t.cycle_id = ?
    ORDER BY t.created_at DESC
  `, [cycleId]);
}

interface CycleWithTrades {
  cycle_id: string;
  started_at: string | null;
  ended_at: string | null;
  symbols_count: number;
  analyzed_count: number;
  trade_count: number;
  trades: TradeRow[];
}

interface RunWithCycles {
  run_id: string;
  started_at: string | null;
  ended_at: string | null;
  cycle_count: number;
  trade_count: number;
  cycles: CycleWithTrades[];
}

/**
 * Get trades grouped by run and cycle
 */
export async function getTradesGroupedByRun(instanceId?: string, limit: number = 10): Promise<RunWithCycles[]> {
  // Get runs with trade counts
  const runsQuery = instanceId
    ? `
      SELECT
        r.id as run_id,
        r.started_at,
        r.ended_at,
        COUNT(DISTINCT t.cycle_id) as cycle_count,
        COUNT(t.id) as trade_count
      FROM runs r
      LEFT JOIN trades t ON t.run_id = r.id
      WHERE r.instance_id = ?
      GROUP BY r.id
      HAVING COUNT(t.id) > 0
      ORDER BY r.started_at DESC
      LIMIT ?
    `
    : `
      SELECT
        r.id as run_id,
        r.started_at,
        r.ended_at,
        COUNT(DISTINCT t.cycle_id) as cycle_count,
        COUNT(t.id) as trade_count
      FROM runs r
      LEFT JOIN trades t ON t.run_id = r.id
      GROUP BY r.id
      HAVING COUNT(t.id) > 0
      ORDER BY r.started_at DESC
      LIMIT ?
    `;

  const runs = instanceId
    ? await dbQuery<{ run_id: string; started_at: string | null; ended_at: string | null; cycle_count: number; trade_count: number }>(runsQuery, [instanceId, limit])
    : await dbQuery<{ run_id: string; started_at: string | null; ended_at: string | null; cycle_count: number; trade_count: number }>(runsQuery, [limit]);

  const result: RunWithCycles[] = [];

  for (const run of runs) {
    // Get cycles for this run
    const cycles = await dbQuery<{ cycle_id: string; started_at: string | null; ended_at: string | null; symbols_count: number; analyzed_count: number; trade_count: number }>(`
      SELECT
        c.id as cycle_id,
        c.started_at,
        c.completed_at as ended_at,
        c.charts_captured as symbols_count,
        c.analyses_completed as analyzed_count,
        COUNT(t.id) as trade_count
      FROM cycles c
      LEFT JOIN trades t ON t.cycle_id = c.id
      WHERE c.run_id = ?
      GROUP BY c.id
      HAVING COUNT(t.id) > 0
      ORDER BY c.started_at DESC
    `, [run.run_id]);

    const cyclesWithTrades: CycleWithTrades[] = [];
    for (const cycle of cycles) {
      const trades = await dbQuery<TradeRow>(`
        SELECT
          t.*,
          COALESCE(t.timeframe, r.timeframe) as timeframe,
          COALESCE(t.entry_price, r.entry_price) as entry_price,
          COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
          COALESCE(t.take_profit, r.take_profit) as take_profit
        FROM trades t
        LEFT JOIN recommendations r ON t.recommendation_id = r.id
        WHERE t.cycle_id = ?
        ORDER BY t.created_at DESC
      `, [cycle.cycle_id]);
      cyclesWithTrades.push({ ...cycle, trades });
    }

    result.push({
      run_id: run.run_id,
      started_at: run.started_at,
      ended_at: run.ended_at,
      cycle_count: run.cycle_count,
      trade_count: run.trade_count,
      cycles: cyclesWithTrades
    });
  }

  return result;
}

/**
 * Get trades by instance ID (via run)
 */
export async function getTradesByInstanceId(instanceId: string, limit: number = 100): Promise<TradeRow[]> {
  return dbQuery<TradeRow>(`
    SELECT
      t.*,
      COALESCE(t.timeframe, r.timeframe) as timeframe,
      COALESCE(t.entry_price, r.entry_price) as entry_price,
      COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
      COALESCE(t.take_profit, r.take_profit) as take_profit
    FROM trades t
    LEFT JOIN recommendations r ON t.recommendation_id = r.id
    LEFT JOIN runs ru ON t.run_id = ru.id
    WHERE ru.instance_id = ?
    ORDER BY t.created_at DESC
    LIMIT ?
  `, [instanceId, limit]);
}

// ============================================================
// CYCLES OPERATIONS
// ============================================================

export interface CycleRow {
  id: string;
  run_id: string | null;  // Links to parent run
  timeframe: string;
  cycle_number: number;
  boundary_time: string;
  status: string;
  skip_reason: string | null;
  charts_captured: number;
  analyses_completed: number;
  recommendations_generated: number;
  trades_executed: number;
  available_slots: number | null;
  open_positions: number | null;
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

/**
 * Get recent cycles
 */
export async function getRecentCycles(limit: number = 20): Promise<CycleRow[]> {
  return dbQuery<CycleRow>(`
    SELECT * FROM cycles
    ORDER BY started_at DESC
    LIMIT ?
  `, [limit]);
}

// ============================================================
// RECOMMENDATIONS OPERATIONS
// ============================================================

export interface RecommendationRow {
  id: string;
  symbol: string;
  timeframe: string;
  recommendation: string;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  reasoning: string | null;
  chart_path: string | null;
  prompt_name: string;
  prompt_version: string | null;
  model_name: string;
  raw_response: string | null;
  analyzed_at: string;
  cycle_boundary: string | null;
  created_at: string;
}

/**
 * Get recent recommendations
 */
export async function getRecentRecommendations(limit: number = 50): Promise<RecommendationRow[]> {
  return dbQuery<RecommendationRow>(`
    SELECT * FROM recommendations
    ORDER BY created_at DESC
    LIMIT ?
  `, [limit]);
}

// ============================================================
// EXECUTIONS OPERATIONS
// ============================================================

export interface ExecutionRow {
  id: string;
  trade_id: string;
  order_id: string;
  exec_id: string;
  symbol: string;
  side: string | null;
  exec_price: number;
  exec_qty: number;
  exec_value: number | null;
  exec_fee: number | null;
  exec_pnl: number | null;
  exec_type: string | null;
  is_maker: number | null;
  exec_time: string;
  created_at: string;
}

/**
 * Get recent executions
 */
export async function getRecentExecutions(limit: number = 100): Promise<ExecutionRow[]> {
  return dbQuery<ExecutionRow>(`
    SELECT * FROM executions
    ORDER BY created_at DESC
    LIMIT ?
  `, [limit]);
}

// ============================================================
// LOG TRAIL - COMBINED VIEW
// ============================================================

export interface LogEntry {
  id: string;
  type: 'cycle' | 'recommendation' | 'trade' | 'execution';
  timestamp: string;
  symbol?: string;
  data: Record<string, unknown>;
}

/**
 * Get unified log trail (all events sorted by time)
 */
export async function getLogTrail(limit: number = 100): Promise<LogEntry[]> {
  const logs: LogEntry[] = [];
  const subLimit = Math.floor(limit / 4);

  // Get cycles
  const cycles = await dbQuery<CycleRow>(`SELECT * FROM cycles ORDER BY started_at DESC LIMIT ?`, [subLimit]);
  for (const c of cycles) {
    logs.push({
      id: c.id,
      type: 'cycle',
      timestamp: c.started_at,
      data: c as unknown as Record<string, unknown>,
    });
  }

  // Get recommendations
  const recs = await dbQuery<RecommendationRow>(`SELECT * FROM recommendations ORDER BY created_at DESC LIMIT ?`, [subLimit]);
  for (const r of recs) {
    logs.push({
      id: r.id,
      type: 'recommendation',
      timestamp: r.created_at,
      symbol: r.symbol,
      data: r as unknown as Record<string, unknown>,
    });
  }

  // Get trades
  const trades = await dbQuery<TradeRow>(`SELECT * FROM trades ORDER BY created_at DESC LIMIT ?`, [subLimit]);
  for (const t of trades) {
    logs.push({
      id: t.id,
      type: 'trade',
      timestamp: t.created_at,
      symbol: t.symbol,
      data: t as unknown as Record<string, unknown>,
    });
  }

  // Get executions
  const execs = await dbQuery<ExecutionRow>(`SELECT * FROM executions ORDER BY created_at DESC LIMIT ?`, [subLimit]);
  for (const e of execs) {
    logs.push({
      id: e.id,
      type: 'execution',
      timestamp: e.created_at,
      symbol: e.symbol,
      data: e as unknown as Record<string, unknown>,
    });
  }

  // Sort by timestamp descending
  logs.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return logs.slice(0, limit);
}

/**
 * Get statistics summary
 */
export async function getStats(): Promise<{
  runs: number;
  cycles: number;
  recommendations: number;
  trades: number;
  executions: number;
  winRate: number;
  totalPnl: number;
}> {
  const [cycleRow, recRow, tradeRow, execRow, winRow, lossRow, pnlRow, runRow] = await Promise.all([
    dbQueryOne<{ count: number }>('SELECT COUNT(*) as count FROM cycles'),
    dbQueryOne<{ count: number }>('SELECT COUNT(*) as count FROM recommendations'),
    dbQueryOne<{ count: number }>("SELECT COUNT(*) as count FROM trades WHERE status NOT IN ('rejected', 'cancelled', 'error')"),
    dbQueryOne<{ count: number }>('SELECT COUNT(*) as count FROM executions'),
    dbQueryOne<{ count: number }>("SELECT COUNT(*) as count FROM trades WHERE pnl > 0 AND status NOT IN ('rejected', 'cancelled', 'error')"),
    dbQueryOne<{ count: number }>("SELECT COUNT(*) as count FROM trades WHERE pnl < 0 AND status NOT IN ('rejected', 'cancelled', 'error')"),
    dbQueryOne<{ total: number }>("SELECT COALESCE(SUM(pnl), 0) as total FROM trades WHERE pnl IS NOT NULL AND status NOT IN ('rejected', 'cancelled', 'error')"),
    dbQueryOne<{ count: number }>('SELECT COUNT(*) as count FROM runs'),
  ]);

  // Ensure numeric types (PostgreSQL returns strings for aggregates)
  const wins = Number(winRow?.count) || 0;
  const losses = Number(lossRow?.count) || 0;
  const winRate = (wins + losses) > 0 ? wins / (wins + losses) : 0;

  return {
    runs: Number(runRow?.count) || 0,
    cycles: Number(cycleRow?.count) || 0,
    recommendations: Number(recRow?.count) || 0,
    trades: Number(tradeRow?.count) || 0,
    executions: Number(execRow?.count) || 0,
    winRate,
    totalPnl: Number(pnlRow?.total) || 0,
  };
}

// ============================================================
// HIERARCHICAL DATA FOR LOG TRAIL
// ============================================================

export interface RunWithHierarchy extends RunRow {
  cycles: CycleWithRecommendations[];
}

export interface CycleWithRecommendations extends CycleRow {
  recommendations: RecommendationWithTrades[];
}

export interface RecommendationWithTrades extends RecommendationRow {
  trades: TradeWithExecutions[];
}

export interface TradeWithExecutions extends TradeRow {
  executions: ExecutionRow[];
}

export interface InstanceWithHierarchy extends InstanceRow {
  runs: RunWithHierarchy[];
  total_cycles: number;
  total_recommendations: number;
  total_trades: number;
  total_pnl: number;
  win_count: number;
  loss_count: number;
}

/**
 * Get instances with full hierarchy for LogTrail (Level 0)
 * Instance → Runs → Cycles → Recommendations → Trades → Executions
 */
export async function getInstancesWithHierarchy(limit: number = 10): Promise<InstanceWithHierarchy[]> {
  // Get all active instances
  const instances = await dbQuery<InstanceRow>(`
    SELECT * FROM instances
    WHERE is_active = true
    ORDER BY name
  `);

  const results: InstanceWithHierarchy[] = [];
  for (const instance of instances) {
    // Get runs for this instance (limited)
    const runs = await dbQuery<RunRow>(`
      SELECT * FROM runs
      WHERE instance_id = ?
      ORDER BY started_at DESC
      LIMIT ?
    `, [instance.id, limit]);

    const runsWithHierarchy: RunWithHierarchy[] = [];
    for (const run of runs) {
      runsWithHierarchy.push({
        ...run,
        cycles: await getCyclesWithRecommendations(run.id),
      });
    }

    // Aggregate stats across all runs of this instance
    const stats = await dbQueryOne<{
      total_cycles: number;
      total_recommendations: number;
      total_trades: number;
      total_pnl: number;
      win_count: number;
      loss_count: number;
    }>(`
      SELECT
        COALESCE(SUM(r.total_cycles), 0) as total_cycles,
        COALESCE(SUM(r.total_recommendations), 0) as total_recommendations,
        COALESCE(COUNT(DISTINCT t.id), 0) as total_trades,
        COALESCE(SUM(CASE WHEN t.pnl IS NOT NULL THEN t.pnl ELSE 0 END), 0) as total_pnl,
        COALESCE(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END), 0) as win_count,
        COALESCE(SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END), 0) as loss_count
      FROM runs r
      LEFT JOIN cycles c ON c.run_id = r.id
      LEFT JOIN trades t ON t.cycle_id = c.id AND t.status NOT IN ('rejected', 'cancelled', 'error')
      WHERE r.instance_id = ?
    `, [instance.id]) || { total_cycles: 0, total_recommendations: 0, total_trades: 0, total_pnl: 0, win_count: 0, loss_count: 0 };

    results.push({
      ...instance,
      runs: runsWithHierarchy,
      total_cycles: stats.total_cycles,
      total_recommendations: stats.total_recommendations,
      total_trades: stats.total_trades,
      total_pnl: stats.total_pnl,
      win_count: stats.win_count,
      loss_count: stats.loss_count,
    });
  }
  return results;
}

/**
 * Get runs with full hierarchy for LogTrail
 */
export async function getRunsWithHierarchy(limit: number = 10): Promise<RunWithHierarchy[]> {
  // Get runs
  const runs = await dbQuery<RunRow>(`
    SELECT * FROM runs
    ORDER BY started_at DESC
    LIMIT ?
  `, [limit]);

  const results: RunWithHierarchy[] = [];
  for (const run of runs) {
    results.push({
      ...run,
      cycles: await getCyclesWithRecommendations(run.id),
    });
  }
  return results;
}

/**
 * Get cycles with recommendations for a run
 */
async function getCyclesWithRecommendations(runId: string): Promise<CycleWithRecommendations[]> {
  const cycles = await dbQuery<CycleRow>(`
    SELECT * FROM cycles
    WHERE run_id = ?
    ORDER BY started_at DESC
  `, [runId]);

  const results: CycleWithRecommendations[] = [];
  for (const cycle of cycles) {
    results.push({
      ...cycle,
      recommendations: await getRecommendationsWithTrades(cycle.id),
    });
  }
  return results;
}

/**
 * Get recommendations with trades for a cycle
 */
async function getRecommendationsWithTrades(cycleId: string): Promise<RecommendationWithTrades[]> {
  const recommendations = await dbQuery<RecommendationRow>(`
    SELECT * FROM recommendations
    WHERE cycle_id = ?
    ORDER BY created_at DESC
  `, [cycleId]);

  const results: RecommendationWithTrades[] = [];
  for (const rec of recommendations) {
    results.push({
      ...rec,
      trades: await getTradesWithExecutions(rec.id),
    });
  }
  return results;
}

/**
 * Get trades with executions for a recommendation
 */
async function getTradesWithExecutions(recommendationId: string): Promise<TradeWithExecutions[]> {
  const trades = await dbQuery<TradeRow>(`
    SELECT * FROM trades
    WHERE recommendation_id = ?
    ORDER BY created_at DESC
  `, [recommendationId]);

  const results: TradeWithExecutions[] = [];
  for (const trade of trades) {
    results.push({
      ...trade,
      executions: await getExecutionsByTradeId(trade.id),
    });
  }
  return results;
}

/**
 * Get executions for a trade
 */
async function getExecutionsByTradeId(tradeId: string): Promise<ExecutionRow[]> {
  return dbQuery<ExecutionRow>(`
    SELECT * FROM executions
    WHERE trade_id = ?
    ORDER BY exec_time DESC
  `, [tradeId]);
}

// ============================================================
// STATS OPERATIONS (Aggregated metrics)
// ============================================================

export interface StatsResult {
  images_analyzed: number;
  valid_signals: number;
  avg_confidence: number;
  actionable_percent: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  total_pnl: number;
}

/**
 * Helper to normalize stats from PostgreSQL (which returns strings for aggregates)
 */
function normalizeStats(
  imagesAnalyzed: number | string | null | undefined,
  recs: { total?: number | string; actionable?: number | string; avg_conf?: number | string | null } | null,
  trades: { total?: number | string; wins?: number | string; losses?: number | string; total_pnl?: number | string } | null
): StatsResult {
  const recsTotal = Number(recs?.total) || 0;
  const recsActionable = Number(recs?.actionable) || 0;
  const avgConf = Number(recs?.avg_conf) || 0;
  const tradesTotal = Number(trades?.total) || 0;
  const tradesWins = Number(trades?.wins) || 0;
  const tradesLosses = Number(trades?.losses) || 0;
  const tradesPnl = Number(trades?.total_pnl) || 0;

  return {
    images_analyzed: Number(imagesAnalyzed) || 0,
    valid_signals: recsActionable,
    avg_confidence: avgConf,
    actionable_percent: recsTotal > 0 ? (recsActionable / recsTotal) * 100 : 0,
    total_trades: tradesTotal,
    win_count: tradesWins,
    loss_count: tradesLosses,
    total_pnl: tradesPnl,
  };
}

/**
 * Get stats for a specific cycle
 */
export async function getStatsByCycleId(cycleId: string): Promise<StatsResult> {
  const [cycle, recs, trades] = await Promise.all([
    dbQueryOne<CycleRow>('SELECT * FROM cycles WHERE id = ?', [cycleId]),
    dbQueryOne<{ total: number; actionable: number; avg_conf: number | null }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN recommendation IN ('BUY', 'SELL', 'LONG', 'SHORT') THEN 1 ELSE 0 END) as actionable,
             AVG(confidence) as avg_conf
      FROM recommendations WHERE cycle_id = ?
    `, [cycleId]),
    dbQueryOne<{ total: number; wins: number; losses: number; total_pnl: number }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
             SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
             SUM(COALESCE(pnl, 0)) as total_pnl
      FROM trades
      WHERE cycle_id = ?
        AND status NOT IN ('rejected', 'cancelled', 'error')
    `, [cycleId]),
  ]);

  return normalizeStats(cycle?.charts_captured, recs, trades);
}

/**
 * Get stats for a specific run
 */
export async function getStatsByRunId(runId: string): Promise<StatsResult> {
  const [cycles, recs, trades] = await Promise.all([
    dbQueryOne<{ total: number | null }>('SELECT SUM(charts_captured) as total FROM cycles WHERE run_id = ?', [runId]),
    dbQueryOne<{ total: number; actionable: number; avg_conf: number | null }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN rec.recommendation IN ('BUY', 'SELL', 'LONG', 'SHORT') THEN 1 ELSE 0 END) as actionable,
             AVG(rec.confidence) as avg_conf
      FROM recommendations rec
      JOIN cycles c ON rec.cycle_id = c.id
      WHERE c.run_id = ?
    `, [runId]),
    dbQueryOne<{ total: number; wins: number; losses: number; total_pnl: number }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
             SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
             SUM(COALESCE(pnl, 0)) as total_pnl
      FROM trades
      WHERE run_id = ?
        AND status NOT IN ('rejected', 'cancelled', 'error')
    `, [runId]),
  ]);

  return normalizeStats(cycles?.total, recs, trades);
}

/**
 * Get stats for a specific instance (all runs)
 */
export async function getStatsByInstanceId(instanceId: string): Promise<StatsResult> {
  const [cycles, recs, trades] = await Promise.all([
    dbQueryOne<{ total: number | null }>(`
      SELECT SUM(c.charts_captured) as total
      FROM cycles c
      JOIN runs r ON c.run_id = r.id
      WHERE r.instance_id = ?
    `, [instanceId]),
    dbQueryOne<{ total: number; actionable: number; avg_conf: number | null }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN rec.recommendation IN ('BUY', 'SELL', 'LONG', 'SHORT') THEN 1 ELSE 0 END) as actionable,
             AVG(rec.confidence) as avg_conf
      FROM recommendations rec
      JOIN cycles c ON rec.cycle_id = c.id
      JOIN runs r ON c.run_id = r.id
      WHERE r.instance_id = ?
    `, [instanceId]),
    dbQueryOne<{ total: number; wins: number; losses: number; total_pnl: number }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
             SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END) as losses,
             SUM(COALESCE(t.pnl, 0)) as total_pnl
      FROM trades t
      JOIN runs r ON t.run_id = r.id
      WHERE r.instance_id = ?
        AND t.status NOT IN ('rejected', 'cancelled', 'error')
    `, [instanceId]),
  ]);

  return normalizeStats(cycles?.total, recs, trades);
}

/**
 * Get global stats (all instances)
 */
export async function getGlobalStats(): Promise<StatsResult & { instance_count: number }> {
  const [instances, cycles, recs, trades] = await Promise.all([
    dbQueryOne<{ total: number }>('SELECT COUNT(*) as total FROM instances WHERE is_active = true'),
    dbQueryOne<{ total: number | null }>('SELECT SUM(charts_captured) as total FROM cycles'),
    dbQueryOne<{ total: number; actionable: number; avg_conf: number | null }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN recommendation IN ('BUY', 'SELL', 'LONG', 'SHORT') THEN 1 ELSE 0 END) as actionable,
             AVG(confidence) as avg_conf
      FROM recommendations
    `),
    dbQueryOne<{ total: number; wins: number; losses: number; total_pnl: number }>(`
      SELECT COUNT(*) as total,
             SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
             SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
             SUM(COALESCE(pnl, 0)) as total_pnl
      FROM trades
      WHERE status NOT IN ('rejected', 'cancelled', 'error')
    `),
  ]);

  return {
    instance_count: Number(instances?.total) || 0,
    ...normalizeStats(cycles?.total, recs, trades),
  };
}

/**
 * Get stats for the latest run of an instance
 */
export async function getLatestRunStatsByInstanceId(instanceId: string): Promise<StatsResult | null> {
  // Get the latest run for this instance
  const latestRun = await dbQueryOne<{ id: string }>(`
    SELECT id FROM runs
    WHERE instance_id = ?
    ORDER BY started_at DESC
    LIMIT 1
  `, [instanceId]);

  if (!latestRun) return null;

  return getStatsByRunId(latestRun.id);
}

/**
 * Get stats for the latest cycle of the latest run of an instance
 */
export async function getLatestCycleStatsByInstanceId(instanceId: string): Promise<StatsResult | null> {
  // Get the latest cycle for this instance's runs
  const latestCycle = await dbQueryOne<{ id: string }>(`
    SELECT c.id FROM cycles c
    JOIN runs r ON c.run_id = r.id
    WHERE r.instance_id = ?
    ORDER BY c.started_at DESC
    LIMIT 1
  `, [instanceId]);

  if (!latestCycle) return null;

  return getStatsByCycleId(latestCycle.id);
}


// ============================================================
// ERROR LOGS
// ============================================================

export interface ErrorLogRow {
  id: string;
  timestamp: string;
  level: string;
  run_id: string | null;
  cycle_id: string | null;
  trade_id: string | null;
  symbol: string | null;
  component: string | null;
  event: string | null;
  message: string;
  stack_trace: string | null;
  context: string | null;
  created_at: string;
}

/**
 * Get recent error logs
 */
export async function getErrorLogs(limit = 100, instanceId?: string): Promise<ErrorLogRow[]> {
  if (instanceId) {
    // Filter by instance via run_id
    // IMPORTANT: Include logs with run_id IS NULL (errors before run started)
    return dbQuery<ErrorLogRow>(`
      SELECT el.* FROM error_logs el
      LEFT JOIN runs r ON el.run_id = r.id
      WHERE r.instance_id = ? OR el.run_id IS NULL
      ORDER BY el.timestamp DESC
      LIMIT ?
    `, [instanceId, limit]);
  }

  return dbQuery<ErrorLogRow>(`
    SELECT * FROM error_logs
    ORDER BY timestamp DESC
    LIMIT ?
  `, [limit]);
}

interface RunWithLogs {
  run_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  log_count: number;
  logs: ErrorLogRow[];
}

/**
 * Get error logs grouped by run
 */
export async function getErrorLogsGroupedByRun(_limit = 200, instanceId?: string): Promise<RunWithLogs[]> {
  // Get runs with log counts
  const runsQuery = instanceId
    ? `
      SELECT
        el.run_id,
        r.started_at,
        r.ended_at,
        COUNT(*) as log_count,
        MAX(el.timestamp) as last_log_time
      FROM error_logs el
      LEFT JOIN runs r ON el.run_id = r.id
      WHERE r.instance_id = ? OR el.run_id IS NULL
      GROUP BY el.run_id, r.started_at, r.ended_at
      ORDER BY COALESCE(r.started_at, MAX(el.timestamp)) DESC
      LIMIT 20
    `
    : `
      SELECT
        el.run_id,
        r.started_at,
        r.ended_at,
        COUNT(*) as log_count,
        MAX(el.timestamp) as last_log_time
      FROM error_logs el
      LEFT JOIN runs r ON el.run_id = r.id
      GROUP BY el.run_id, r.started_at, r.ended_at
      ORDER BY COALESCE(r.started_at, MAX(el.timestamp)) DESC
      LIMIT 20
    `;

  const runs = instanceId
    ? await dbQuery<{ run_id: string | null; started_at: string | null; ended_at: string | null; log_count: number }>(runsQuery, [instanceId])
    : await dbQuery<{ run_id: string | null; started_at: string | null; ended_at: string | null; log_count: number }>(runsQuery);

  // Get logs for each run
  // IMPORTANT: Fetch ALL logs for each run (no limit) to match the log_count shown in header
  // The limit parameter is for the number of runs, not logs per run
  const result: RunWithLogs[] = [];

  for (const run of runs) {
    const logs = run.run_id
      ? await dbQuery<ErrorLogRow>(`SELECT * FROM error_logs WHERE run_id = ? ORDER BY timestamp ASC`, [run.run_id])
      : await dbQuery<ErrorLogRow>(`SELECT * FROM error_logs WHERE run_id IS NULL ORDER BY timestamp ASC`);

    result.push({
      run_id: run.run_id,
      started_at: run.started_at,
      ended_at: run.ended_at,
      log_count: run.log_count,
      logs
    });
  }

  return result;
}

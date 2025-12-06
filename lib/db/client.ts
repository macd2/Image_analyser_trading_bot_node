/**
 * Database abstraction layer
 *
 * SQLite for development, PostgreSQL for production
 * Swap by setting DB_TYPE=postgres and DATABASE_URL env vars
 */

import Database from 'better-sqlite3';
import { Pool } from 'pg';
import path from 'path';

export type DbType = 'sqlite' | 'postgres';

// Configuration from environment
const config = {
  type: (process.env.DB_TYPE as DbType) || 'sqlite',
  sqlitePath: process.env.SQLITE_PATH || path.join(process.cwd(), 'data', 'backtests.db'),
  postgresUrl: process.env.DATABASE_URL || '',

};

// Database instances
let sqliteDb: Database.Database | null = null;
let pgPool: Pool | null = null;

/**
 * Initialize SQLite connection
 */
function initSqlite(): Database.Database {
  if (!sqliteDb) {
    sqliteDb = new Database(config.sqlitePath, { readonly: false });
    sqliteDb.pragma('journal_mode = WAL');
  }
  return sqliteDb;
}

/**
 * Initialize PostgreSQL connection pool
 * Configured for Supabase connection pooler (Transaction mode)
 */
function initPostgres(): Pool {
  if (!pgPool) {
    pgPool = new Pool({
      connectionString: config.postgresUrl,
      // Connection pool settings for Supabase pooler
      max: 10,                        // Max pool size
      idleTimeoutMillis: 30000,       // Close idle connections after 30s
      connectionTimeoutMillis: 10000, // Timeout for new connections
      allowExitOnIdle: true,          // Allow pool to exit when idle
    });

    // Handle pool errors gracefully
    pgPool.on('error', (err) => {
      console.error('[PostgreSQL Pool Error]', err.message);
      // Don't crash - the pool will attempt to reconnect
    });
  }
  return pgPool;
}

/**
 * Convert SQLite placeholder (?) to PostgreSQL ($1, $2, etc)
 */
function convertPlaceholders(sql: string): string {
  let idx = 0;
  return sql.replace(/\?/g, () => `$${++idx}`);
}

/**
 * Execute a SELECT query
 */
export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  if (config.type === 'sqlite') {
    const db = initSqlite();
    return db.prepare(sql).all(...params) as T[];
  } else {
    const pool = initPostgres();
    const pgSql = convertPlaceholders(sql);
    const result = await pool.query(pgSql, params);
    return result.rows as T[];
  }
}

/**
 * Execute an INSERT/UPDATE/DELETE query
 */
export async function execute(sql: string, params: unknown[] = []): Promise<{ changes: number; lastId: number }> {
  if (config.type === 'sqlite') {
    const db = initSqlite();
    const result = db.prepare(sql).run(...params);
    return { changes: result.changes, lastId: result.lastInsertRowid as number };
  } else {
    const pool = initPostgres();
    const pgSql = convertPlaceholders(sql);
    const result = await pool.query(pgSql, params);
    return { changes: result.rowCount || 0, lastId: 0 };
  }
}

/**
 * Execute a single-row query
 */
export async function queryOne<T>(sql: string, params: unknown[] = []): Promise<T | null> {
  const results = await query<T>(sql, params);
  return results[0] || null;
}

/**
 * Check database availability
 */
export async function isDatabaseAvailable(): Promise<boolean> {
  try {
    if (config.type === 'sqlite') {
      initSqlite().prepare('SELECT 1').get();
      return true;
    } else {
      const pool = initPostgres();
      await pool.query('SELECT 1');
      return true;
    }
  } catch {
    return false;
  }
}

/**
 * Get database info for debugging
 */
export function getDatabaseInfo() {
  return {
    type: config.type,
    path: config.type === 'sqlite' ? config.sqlitePath : config.postgresUrl.split('@')[1]?.split('/')[0] || 'postgres',
  };
}

/**
 * Close all connections
 */
export async function closeDatabase(): Promise<void> {
  if (sqliteDb) {
    sqliteDb.close();
    sqliteDb = null;
  }
  if (pgPool) {
    await pgPool.end();
    pgPool = null;
  }
}

/**
 * Get current database type
 */
export function getDbType(): DbType {
  return config.type;
}


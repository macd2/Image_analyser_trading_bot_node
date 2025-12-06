/**
 * Settings persistence layer
 * Store and retrieve instance-specific settings from SQLite or PostgreSQL
 *
 * Uses DB_TYPE env var to switch between:
 * - 'sqlite': Local SQLite file (development)
 * - 'postgres': Supabase PostgreSQL (production)
 */

import Database from 'better-sqlite3';
import { Pool } from 'pg';
import path from 'path';
import fs from 'fs';

type DbType = 'sqlite' | 'postgres';

const DB_TYPE: DbType = (process.env.DB_TYPE as DbType) || 'sqlite';
const DB_PATH = process.env.SQLITE_PATH || path.join(process.cwd(), 'data', 'bot.db');
const DATABASE_URL = process.env.DATABASE_URL || '';

// Database instances
let sqliteDb: Database.Database | null = null;
let pgPool: Pool | null = null;

function getSqliteDb(): Database.Database {
  if (!sqliteDb) {
    const dataDir = path.dirname(DB_PATH);
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
    sqliteDb = new Database(DB_PATH);
    sqliteDb.pragma('journal_mode = WAL');
  }
  return sqliteDb;
}

function getPgPool(): Pool {
  if (!pgPool) {
    pgPool = new Pool({
      connectionString: DATABASE_URL,
      ssl: { rejectUnauthorized: false },
      max: 5,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000,
    });
    pgPool.on('error', (err) => {
      console.error('[Settings] PostgreSQL pool error:', err.message);
    });
  }
  return pgPool;
}

export interface SettingsRecord {
  id: number;
  instance_id: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * Get settings for an instance - async to support both SQLite and PostgreSQL
 */
export async function getSettings<T = Record<string, unknown>>(instanceId: string): Promise<T | null> {
  if (DB_TYPE === 'postgres') {
    const pool = getPgPool();
    const result = await pool.query('SELECT settings FROM settings WHERE instance_id = $1', [instanceId]);
    if (result.rows.length === 0) return null;
    const settings = result.rows[0].settings;
    return (typeof settings === 'string' ? JSON.parse(settings) : settings) as T;
  } else {
    const db = getSqliteDb();
    const row = db.prepare('SELECT settings FROM settings WHERE instance_id = ?').get(instanceId) as { settings: string } | undefined;
    if (!row) return null;
    return JSON.parse(row.settings) as T;
  }
}

/**
 * Save settings for an instance (upsert) - async for PostgreSQL
 */
export async function saveSettings<T = Record<string, unknown>>(instanceId: string, settings: T): Promise<void> {
  const json = JSON.stringify(settings);

  if (DB_TYPE === 'postgres') {
    const pool = getPgPool();
    await pool.query(`
      INSERT INTO settings (instance_id, settings) VALUES ($1, $2)
      ON CONFLICT(instance_id) DO UPDATE SET settings = EXCLUDED.settings, updated_at = CURRENT_TIMESTAMP
    `, [instanceId, json]);
  } else {
    const db = getSqliteDb();
    db.prepare(`
      INSERT INTO settings (instance_id, settings) VALUES (?, ?)
      ON CONFLICT(instance_id) DO UPDATE SET settings = excluded.settings, updated_at = CURRENT_TIMESTAMP
    `).run(instanceId, json);
  }
}

/**
 * Update specific keys in settings (merge) - async for PostgreSQL
 */
export async function updateSettings<T = Record<string, unknown>>(instanceId: string, partial: Partial<T>): Promise<T> {
  const existing = await getSettings<T>(instanceId) || {} as T;
  const merged = { ...existing, ...partial };
  await saveSettings(instanceId, merged);
  return merged;
}

/**
 * Delete settings for an instance - async for PostgreSQL
 */
export async function deleteSettings(instanceId: string): Promise<boolean> {
  if (DB_TYPE === 'postgres') {
    const pool = getPgPool();
    const result = await pool.query('DELETE FROM settings WHERE instance_id = $1', [instanceId]);
    return (result.rowCount || 0) > 0;
  } else {
    const db = getSqliteDb();
    const result = db.prepare('DELETE FROM settings WHERE instance_id = ?').run(instanceId);
    return result.changes > 0;
  }
}

/**
 * List all instance IDs with settings - async for PostgreSQL
 */
export async function listInstances(): Promise<string[]> {
  if (DB_TYPE === 'postgres') {
    const pool = getPgPool();
    const result = await pool.query('SELECT instance_id FROM settings ORDER BY instance_id');
    return result.rows.map((r: { instance_id: string }) => r.instance_id);
  } else {
    const db = getSqliteDb();
    const rows = db.prepare('SELECT instance_id FROM settings ORDER BY instance_id').all() as { instance_id: string }[];
    return rows.map(r => r.instance_id);
  }
}


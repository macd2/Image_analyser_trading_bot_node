/**
 * Settings persistence layer
 * Store and retrieve instance-specific settings from SQLite
 */

import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';

const DB_PATH = process.env.SQLITE_PATH || path.join(process.cwd(), 'data', 'bot.db');

function getDb(): Database.Database {
  const dataDir = path.dirname(DB_PATH);
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  const db = new Database(DB_PATH);
  db.pragma('journal_mode = WAL');
  return db;
}

export interface SettingsRecord {
  id: number;
  instance_id: string;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/**
 * Get settings for an instance
 */
export function getSettings<T = Record<string, unknown>>(instanceId: string): T | null {
  const db = getDb();
  try {
    const row = db.prepare('SELECT settings FROM settings WHERE instance_id = ?').get(instanceId) as { settings: string } | undefined;
    if (!row) return null;
    return JSON.parse(row.settings) as T;
  } finally {
    db.close();
  }
}

/**
 * Save settings for an instance (upsert)
 */
export function saveSettings<T = Record<string, unknown>>(instanceId: string, settings: T): void {
  const db = getDb();
  try {
    const json = JSON.stringify(settings);
    db.prepare(`
      INSERT INTO settings (instance_id, settings) VALUES (?, ?)
      ON CONFLICT(instance_id) DO UPDATE SET settings = excluded.settings, updated_at = CURRENT_TIMESTAMP
    `).run(instanceId, json);
  } finally {
    db.close();
  }
}

/**
 * Update specific keys in settings (merge)
 */
export function updateSettings<T = Record<string, unknown>>(instanceId: string, partial: Partial<T>): T {
  const db = getDb();
  try {
    const existing = getSettings<T>(instanceId) || {} as T;
    const merged = { ...existing, ...partial };
    saveSettings(instanceId, merged);
    return merged;
  } finally {
    db.close();
  }
}

/**
 * Delete settings for an instance
 */
export function deleteSettings(instanceId: string): boolean {
  const db = getDb();
  try {
    const result = db.prepare('DELETE FROM settings WHERE instance_id = ?').run(instanceId);
    return result.changes > 0;
  } finally {
    db.close();
  }
}

/**
 * List all instance IDs with settings
 */
export function listInstances(): string[] {
  const db = getDb();
  try {
    const rows = db.prepare('SELECT instance_id FROM settings ORDER BY instance_id').all() as { instance_id: string }[];
    return rows.map(r => r.instance_id);
  } finally {
    db.close();
  }
}


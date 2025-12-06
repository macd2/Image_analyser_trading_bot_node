/**
 * Database Migration Runner
 * Applies SQL migrations in order, tracks applied migrations
 */

import Database from 'better-sqlite3';
import fs from 'fs';
import path from 'path';

const MIGRATIONS_DIR = path.join(process.cwd(), 'lib', 'db', 'migrations');
const DB_PATH = process.env.SQLITE_PATH || path.join(process.cwd(), 'data', 'bot.db');

// Ensure data directory exists
const dataDir = path.dirname(DB_PATH);
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

// Create migrations tracking table
db.exec(`
  CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
`);

/**
 * Get list of applied migrations
 */
function getAppliedMigrations(): string[] {
  const rows = db.prepare('SELECT name FROM _migrations ORDER BY id').all() as { name: string }[];
  return rows.map(r => r.name);
}

/**
 * Get list of pending migrations
 */
function getPendingMigrations(): string[] {
  const applied = new Set(getAppliedMigrations());
  const files = fs.readdirSync(MIGRATIONS_DIR)
    .filter(f => f.endsWith('.sql'))
    .sort();
  return files.filter(f => !applied.has(f));
}

/**
 * Apply a single migration
 */
function applyMigration(filename: string): void {
  const filepath = path.join(MIGRATIONS_DIR, filename);
  const sql = fs.readFileSync(filepath, 'utf-8');
  
  console.log(`Applying migration: ${filename}`);
  
  db.transaction(() => {
    db.exec(sql);
    db.prepare('INSERT INTO _migrations (name) VALUES (?)').run(filename);
  })();
  
  console.log(`✓ Applied: ${filename}`);
}

/**
 * Run all pending migrations
 */
export function runMigrations(): { applied: string[]; pending: string[] } {
  const pending = getPendingMigrations();
  const applied: string[] = [];
  
  if (pending.length === 0) {
    console.log('No pending migrations.');
    return { applied, pending: [] };
  }
  
  console.log(`Found ${pending.length} pending migration(s)`);
  
  for (const migration of pending) {
    try {
      applyMigration(migration);
      applied.push(migration);
    } catch (error) {
      console.error(`Failed to apply ${migration}:`, error);
      throw error;
    }
  }
  
  return { applied, pending: getPendingMigrations() };
}

/**
 * Get migration status
 */
export function getMigrationStatus(): { applied: string[]; pending: string[] } {
  return {
    applied: getAppliedMigrations(),
    pending: getPendingMigrations(),
  };
}

/**
 * Get database connection for queries
 */
export function getDb(): Database.Database {
  return db;
}

// Run migrations if called directly
if (require.main === module) {
  console.log('Running database migrations...');
  console.log(`Database: ${DB_PATH}`);
  const result = runMigrations();
  console.log(`\nApplied ${result.applied.length} migration(s)`);
  if (result.pending.length > 0) {
    console.log(`Pending: ${result.pending.length}`);
  }
  db.close();
}


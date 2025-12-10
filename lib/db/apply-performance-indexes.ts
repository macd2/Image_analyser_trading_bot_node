/**
 * Apply performance indexes migration directly using the database client.
 * This script can be run with: npx tsx lib/db/apply-performance-indexes.ts
 */

import { dbQuery } from './trading-db';

async function applyIndexes() {
  console.log('Applying performance indexes...');

  const indexes = [
    // trades indexes
    'CREATE INDEX IF NOT EXISTS idx_trades_cycle ON trades(cycle_id)',
    'CREATE INDEX IF NOT EXISTS idx_trades_recommendation ON trades(recommendation_id)',
    'CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at)',
    // runs composite index
    'CREATE INDEX IF NOT EXISTS idx_runs_instance_started ON runs(instance_id, started_at DESC)',
  ];

  for (const sql of indexes) {
    try {
      console.log(`Executing: ${sql}`);
      await dbQuery(sql);
      console.log('  -> OK');
    } catch (error) {
      console.error(`  -> ERROR: ${error instanceof Error ? error.message : error}`);
      // Continue with other indexes
    }
  }

  console.log('All indexes applied (or already exist).');
}

if (require.main === module) {
  applyIndexes()
    .then(() => {
      console.log('Migration completed.');
      process.exit(0);
    })
    .catch((error) => {
      console.error('Migration failed:', error);
      process.exit(1);
    });
}

export default applyIndexes;
#!/usr/bin/env tsx

/**
 * Reset all filled and closed dry-run trades to executor initial state
 * This restores trades to the state they were in when first created by the executor
 *
 * Usage: npx tsx scripts/reset-trades.ts [--dry-run]
 *   --dry-run: Show what will be reset without making changes
 */

import { dbQuery, dbExecute } from '@/lib/db/trading-db';
import * as readline from 'readline';

const isDryRun = process.argv.includes('--dry-run');

async function resetTrades() {
  try {
    console.log('🔍 Checking trades to reset...\n');

    // Check what will be reset
    const counts = await dbQuery<any>(`
      SELECT
        COUNT(*) as total_trades,
        COUNT(CASE WHEN status = 'filled' THEN 1 END) as filled_trades,
        COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades
      FROM trades
      WHERE dry_run = true AND (status = 'filled' OR status = 'closed')
    `);

    const { total_trades, filled_trades, closed_trades } = counts[0];
    console.log(`Total trades to reset: ${total_trades}`);
    console.log(`  - Filled trades: ${filled_trades}`);
    console.log(`  - Closed trades: ${closed_trades}\n`);

    if (isDryRun) {
      console.log('📋 DRY RUN MODE - No changes will be made\n');
    }

    if (total_trades === 0) {
      console.log('✅ No trades to reset');
      process.exit(0);
    }

    // Show sample
    const samples = await dbQuery<any>(`
      SELECT id, symbol, status, filled_at, exit_price, exit_reason, pnl, closed_at
      FROM trades
      WHERE dry_run = true AND (status = 'filled' OR status = 'closed')
      LIMIT 3
    `);

    console.log('Sample trades to reset:');
    samples.forEach((t: any) => {
      console.log(`  ${t.id} (${t.symbol}): ${t.status} -> paper_trade`);
    });
    console.log();

    // If dry run mode, just show samples and exit
    if (isDryRun) {
      const samples = await dbQuery<any>(`
        SELECT id, symbol, status, filled_at, exit_price, exit_reason, pnl, closed_at
        FROM trades
        WHERE dry_run = true AND (status = 'filled' OR status = 'closed')
        LIMIT 5
      `);

      console.log('Sample trades that would be reset:');
      samples.forEach((t: any) => {
        console.log(`  ${t.id.substring(0, 8)} (${t.symbol}): ${t.status} -> paper_trade`);
      });
      console.log();
      process.exit(0);
    }

    // Ask for confirmation
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    rl.question(`Reset ${total_trades} trades? (yes/no): `, async (answer) => {
      rl.close();

      if (answer.toLowerCase() !== 'yes') {
        console.log('❌ Cancelled');
        process.exit(0);
      }

      console.log('\n⏳ Resetting trades...\n');

      // Reset all filled or closed trades to initial state
      const result = await dbExecute(`
        UPDATE trades
        SET
          status = 'paper_trade',
          filled_at = NULL,
          exit_price = NULL,
          exit_reason = NULL,
          pnl = NULL,
          pnl_percent = NULL,
          closed_at = NULL,
          avg_exit_price = NULL,
          closed_size = NULL
        WHERE dry_run = true AND (status = 'filled' OR status = 'closed')
      `);

      console.log(`✅ Reset ${result.changes} trades to paper_trade status`);
      console.log('   All exit fields cleared');
      process.exit(0);
    });
  } catch (err) {
    console.error('❌ Error:', err instanceof Error ? err.message : String(err));
    process.exit(1);
  }
}

resetTrades();


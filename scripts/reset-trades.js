#!/usr/bin/env node

/**
 * Reset all closed or paper trades to executor initial state
 * This restores trades to the state they were in when first created by the executor
 */

// Use dynamic import for TypeScript module
const importModule = async () => {
  const module = await import('../lib/db/trading-db.ts');
  return module;
};

let dbQuery, execute;

async function resetTrades() {
  try {
    console.log('🔍 Checking trades to reset...\n');

    // Check what will be reset
    const counts = await dbQuery(`
      SELECT 
        COUNT(*) as total_trades,
        COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_trades,
        COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trades
      FROM trades
      WHERE dry_run = true AND (status = 'closed' OR status = 'paper_trade')
    `);

    const { total_trades, closed_trades, paper_trades } = counts[0];
    console.log(`Total trades to reset: ${total_trades}`);
    console.log(`  - Closed trades: ${closed_trades}`);
    console.log(`  - Paper trades: ${paper_trades}\n`);

    if (total_trades === 0) {
      console.log('✅ No trades to reset');
      process.exit(0);
    }

    // Show sample
    const samples = await dbQuery(`
      SELECT id, symbol, status, filled_at, exit_price, exit_reason, pnl, closed_at
      FROM trades
      WHERE dry_run = true AND (status = 'closed' OR status = 'paper_trade')
      LIMIT 3
    `);

    console.log('Sample trades to reset:');
    samples.forEach(t => {
      console.log(`  ${t.id} (${t.symbol}): ${t.status} -> paper_trade`);
    });
    console.log();

    // Ask for confirmation
    const readline = require('readline');
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

      // Reset all closed or paper trades to initial state
      await execute(`
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
        WHERE dry_run = true AND (status = 'closed' OR status = 'paper_trade')
      `);

      console.log(`✅ Reset ${total_trades} trades to paper_trade status`);
      console.log('   All exit fields cleared');
      process.exit(0);
    });
  } catch (err) {
    console.error('❌ Error:', err.message);
    process.exit(1);
  }
}

resetTrades();


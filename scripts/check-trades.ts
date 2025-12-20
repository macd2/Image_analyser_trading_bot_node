#!/usr/bin/env tsx

import { dbQuery } from '@/lib/db/trading-db';

async function checkTrades() {
  try {
    // Check all dry run trades
    const allDryRun = await dbQuery<any>(`
      SELECT 
        status,
        COUNT(*) as count
      FROM trades
      WHERE dry_run = true
      GROUP BY status
      ORDER BY count DESC
    `);
    
    console.log('📊 All dry_run trades by status:');
    allDryRun.forEach((row: any) => {
      console.log(`  ${row.status}: ${row.count}`);
    });
    
    // Show some samples
    const samples = await dbQuery<any>(`
      SELECT id, symbol, status, filled_at, exit_price, closed_at
      FROM trades
      WHERE dry_run = true
      ORDER BY created_at DESC
      LIMIT 15
    `);
    
    console.log('\n📋 Sample trades (most recent):');
    samples.forEach((t: any) => {
      const filled = t.filled_at ? '✓' : '✗';
      const exit = t.exit_price ? '✓' : '✗';
      const closed = t.closed_at ? '✓' : '✗';
      console.log(`  ${t.id.substring(0, 8)} (${t.symbol}): ${t.status.padEnd(12)} | filled=${filled} exit=${exit} closed=${closed}`);
    });
    
    process.exit(0);
  } catch (err) {
    console.error('Error:', err);
    process.exit(1);
  }
}

checkTrades();


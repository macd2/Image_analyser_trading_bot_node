import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

async function resetSpreadTrades() {
  const client = await pool.connect();
  const isDryRun = process.argv.includes('--dry-run') || process.argv.includes('-n');
  
  try {
    console.log(`\n🔍 Finding spread-based trades to reset...\n`);

    // First, show what we're about to reset
    const checkResult = await client.query(`
      SELECT 
        id, 
        symbol, 
        side, 
        entry_price, 
        quantity, 
        stop_loss, 
        take_profit,
        status, 
        exit_reason,
        pnl, 
        pnl_percent, 
        filled_at, 
        closed_at
      FROM trades
      WHERE strategy_type = 'spread_based' 
        AND status IN ('filled', 'closed')
      ORDER BY created_at DESC
      LIMIT 5
    `);

    console.log('📋 Sample of spread-based trades to reset:');
    console.table(checkResult.rows);

    const countResult = await client.query(`
      SELECT 
        COUNT(*) as total_count,
        COUNT(CASE WHEN status = 'closed' THEN 1 END) as closed_count,
        COUNT(CASE WHEN status = 'filled' THEN 1 END) as filled_count
      FROM trades
      WHERE strategy_type = 'spread_based' 
        AND status IN ('filled', 'closed')
    `);
    
    const { total_count, closed_count, filled_count } = countResult.rows[0];
    console.log(`\n📊 Total spread-based trades to reset: ${total_count}`);
    console.log(`   - Closed trades: ${closed_count}`);
    console.log(`   - Filled trades: ${filled_count}\n`);
    
    if (total_count === 0) {
      console.log('✅ No spread-based trades to reset!');
      await pool.end();
      return;
    }

    if (isDryRun) {
      console.log('🔍 DRY RUN MODE - No changes will be made\n');
      console.log('✅ Dry run complete. To apply changes, run:');
      console.log('   npm run reset:spread-trades\n');
      await pool.end();
      return;
    }

    // Ask for confirmation
    const readline = require('readline');
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    rl.question(`⚠️  Reset ${total_count} spread-based trades? (yes/no): `, async (answer: string) => {
      rl.close();

      if (answer.toLowerCase() !== 'yes') {
        console.log('❌ Cancelled\n');
        await pool.end();
        return;
      }

      console.log('\n⏳ Resetting spread-based trades...\n');

      // Reset all spread-based trades to paper_trade status
      // CRITICAL: Preserve entry data (entry_price, stop_loss, take_profit, strategy_metadata)
      const resetResult = await client.query(`
        UPDATE trades
        SET
          status = 'paper_trade',
          fill_price = NULL,
          fill_quantity = NULL,
          fill_time = NULL,
          filled_at = NULL,
          pair_fill_price = NULL,
          exit_price = NULL,
          pair_exit_price = NULL,
          exit_reason = NULL,
          closed_at = NULL,
          pnl = NULL,
          pnl_percent = NULL,
          avg_exit_price = NULL,
          closed_size = NULL,
          updated_at = CURRENT_TIMESTAMP
        WHERE strategy_type = 'spread_based' 
          AND status IN ('filled', 'closed')
      `);
      
      console.log(`✅ Reset ${resetResult.rowCount} spread-based trades to paper_trade status\n`);
      
      // Verify the reset
      console.log('✔️ Verifying reset...');
      const verifyResult = await client.query(`
        SELECT 
          COUNT(*) as total,
          COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trade_count,
          COUNT(CASE WHEN filled_at IS NULL THEN 1 END) as unfilled_count
        FROM trades
        WHERE strategy_type = 'spread_based' 
          AND status IN ('paper_trade', 'filled', 'closed')
      `);
      
      const { total, paper_trade_count, unfilled_count } = verifyResult.rows[0];
      console.log(`✅ Verification complete:`);
      console.log(`   - Total spread trades: ${total}`);
      console.log(`   - Now paper_trade: ${paper_trade_count}`);
      console.log(`   - Unfilled: ${unfilled_count}\n`);
      
      console.log('📝 Trades are now ready for simulator re-evaluation:');
      console.log('   ✓ status: paper_trade');
      console.log('   ✓ filled_at: NULL');
      console.log('   ✓ All fill/exit/pnl data: NULL');
      console.log('   ✓ Entry setup (entry_price, stop_loss, take_profit): INTACT');
      console.log('   ✓ Strategy metadata: INTACT\n');
      
      await pool.end();
    });
    
  } catch (error) {
    console.error('❌ Error:', error);
    await pool.end();
    process.exit(1);
  }
}

resetSpreadTrades();


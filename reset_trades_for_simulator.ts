import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

async function resetTrades() {
  const client = await pool.connect();
  
  try {
    console.log('🔍 Finding trades with pattern: filled_at IS NULL AND status=closed...\n');

    // First, show what we're about to reset
    const checkResult = await client.query(`
      SELECT id, symbol, side, entry_price, quantity, stop_loss, take_profit,
             status, fill_price, pnl, pnl_percent, filled_at, closed_at
      FROM trades
      WHERE filled_at IS NULL AND status = 'closed'
      ORDER BY created_at DESC
      LIMIT 5
    `);

    console.log('Sample of trades to reset:');
    console.table(checkResult.rows);

    const countResult = await client.query(`
      SELECT COUNT(*) as count FROM trades
      WHERE filled_at IS NULL AND status = 'closed'
    `);
    
    const totalCount = parseInt(countResult.rows[0].count, 10);
    console.log(`\n📊 Total trades to reset: ${totalCount}\n`);
    
    if (totalCount === 0) {
      console.log('✅ No trades to reset!');
      return;
    }
    
    // Reset trades to paper_trade status (as if just submitted)
    console.log('🔄 Resetting trades to paper_trade status...');
    const resetResult = await client.query(`
      UPDATE trades
      SET
        status = 'paper_trade',
        fill_price = NULL,
        fill_quantity = NULL,
        fill_time = NULL,
        filled_at = NULL,
        exit_price = NULL,
        exit_reason = NULL,
        closed_at = NULL,
        pnl = NULL,
        pnl_percent = NULL,
        updated_at = CURRENT_TIMESTAMP
      WHERE filled_at IS NULL AND status = 'closed'
    `);
    
    console.log(`✅ Reset ${resetResult.rowCount} trades to paper_trade status\n`);
    
    // Verify the reset
    console.log('✔️ Verifying reset...');
    const verifyResult = await client.query(`
      SELECT COUNT(*) as count,
             COUNT(CASE WHEN status = 'paper_trade' THEN 1 END) as paper_trade_count
      FROM trades
      WHERE filled_at IS NULL AND status = 'closed'
    `);
    
    const remaining = parseInt(verifyResult.rows[0].count, 10);
    if (remaining === 0) {
      console.log('✅ All trades successfully reset!');
      console.log('\n📝 Trades are now ready for simulator re-evaluation:');
      console.log('   - status: paper_trade');
      console.log('   - filled_at: NULL');
      console.log('   - All fill/exit/pnl data: NULL');
      console.log('   - Entry setup (entry_price, stop_loss, take_profit): INTACT');
    } else {
      console.log(`⚠️  Warning: ${remaining} trades still have the pattern`);
    }
    
  } catch (error) {
    console.error('❌ Error:', error);
  } finally {
    client.release();
    await pool.end();
  }
}

resetTrades();


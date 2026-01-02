const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

// Load env from .env.local
const envPath = path.join(__dirname, '..', '.env.local');
const envContent = fs.readFileSync(envPath, 'utf-8');
const env = {};

envContent.split('\n').forEach(line => {
  if (line && !line.startsWith('#') && line.includes('=')) {
    const [key, value] = line.split('=');
    env[key.trim()] = value.trim();
  }
});

const supabaseUrl = env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseKey = env.SUPABASE_SERVICE_ROLE_KEY;

console.log('Supabase URL:', supabaseUrl ? 'set' : 'NOT SET');
console.log('Service Role Key:', supabaseKey ? 'set' : 'NOT SET');

if (!supabaseUrl || !supabaseKey) {
  console.error('❌ Missing Supabase credentials');
  process.exit(1);
}

const supabase = createClient(supabaseUrl, supabaseKey);

(async () => {
  try {
    // Get count - spread trades have pair_quantity set
    const { data: trades, error: fetchError } = await supabase
      .from('trades')
      .select('id, symbol, side, status, pair_quantity, order_id_pair')
      .eq('symbol', 'OGUSDT')
      .not('pair_quantity', 'is', null);

    if (fetchError) {
      console.error('❌ Error fetching trades:', fetchError);
      process.exit(1);
    }

    console.log(`Found ${trades?.length || 0} spread trades for OGUSDT`);

    if (trades && trades.length > 0) {
      console.log('\nTrades to be deleted:');
      trades.forEach(trade => {
        console.log(`  - ${trade.id}: ${trade.symbol} (${trade.side}) - ${trade.status} - pair_qty: ${trade.pair_quantity}`);
      });

      // Delete them
      const { error: deleteError } = await supabase
        .from('trades')
        .delete()
        .eq('symbol', 'OGUSDT')
        .not('pair_quantity', 'is', null);

      if (deleteError) {
        console.error('❌ Error deleting trades:', deleteError);
        process.exit(1);
      }

      console.log(`\n✅ Deleted ${trades.length} spread trades for OGUSDT`);
    } else {
      console.log('No spread trades found for OGUSDT');
    }

    process.exit(0);
  } catch (error) {
    console.error('❌ Error:', error);
    process.exit(1);
  }
})();


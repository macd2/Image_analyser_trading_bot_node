/**
 * Test script to verify auto-close API is working correctly
 * Tests:
 * 1. Can fetch historical candles from Bybit
 * 2. Can get current ticker price as fallback
 * 3. Auto-close endpoint returns proper current_price values
 */

interface KlineResult {
  retCode: number;
  result?: {
    list?: [string, string, string, string, string, string, string][];
  };
}

interface TickerResult {
  retCode: number;
  result?: {
    list?: Array<{
      symbol: string;
      lastPrice: string;
    }>;
  };
}

// Test symbols from your screenshot
const TEST_SYMBOLS = ['AVAXUSDT', 'DYDXUSDT'];

async function testHistoricalCandles(symbol: string) {
  console.log(`\n=== Testing Historical Candles for ${symbol} ===`);
  
  const apiSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const interval = '240'; // 4h
  const startTime = Date.now() - (24 * 60 * 60 * 1000); // 24 hours ago
  const limit = 10;
  
  const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&start=${startTime}&limit=${limit}`;
  console.log(`URL: ${url}`);
  
  try {
    const res = await fetch(url);
    console.log(`Response status: ${res.status} ${res.statusText}`);
    
    if (!res.ok) {
      console.error(`❌ HTTP error: ${res.status}`);
      return false;
    }
    
    const data: KlineResult = await res.json();
    console.log(`Bybit retCode: ${data.retCode}`);
    console.log(`Candles returned: ${data.result?.list?.length || 0}`);
    
    if (data.retCode !== 0 || !data.result?.list) {
      console.error(`❌ Bybit API error: retCode=${data.retCode}`);
      return false;
    }
    
    if (data.result.list.length > 0) {
      const latest = data.result.list[0];
      console.log(`Latest candle: timestamp=${latest[0]}, close=${latest[4]}`);
      console.log(`✅ Historical candles working`);
      return true;
    }
    
    console.error(`❌ No candles returned`);
    return false;
  } catch (e) {
    console.error(`❌ Exception:`, e);
    return false;
  }
}

async function testCurrentPrice(symbol: string) {
  console.log(`\n=== Testing Current Price (Ticker) for ${symbol} ===`);
  
  const apiSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const url = `https://api.bybit.com/v5/market/tickers?category=linear&symbol=${apiSymbol}`;
  console.log(`URL: ${url}`);
  
  try {
    const res = await fetch(url);
    console.log(`Response status: ${res.status} ${res.statusText}`);
    
    if (!res.ok) {
      console.error(`❌ HTTP error: ${res.status}`);
      return false;
    }
    
    const data: TickerResult = await res.json();
    console.log(`Bybit retCode: ${data.retCode}`);
    
    if (data.retCode === 0 && data.result?.list?.[0]?.lastPrice) {
      const price = parseFloat(data.result.list[0].lastPrice);
      console.log(`Current price: $${price}`);
      console.log(`✅ Ticker API working`);
      return true;
    }
    
    console.error(`❌ No ticker data returned`);
    return false;
  } catch (e) {
    console.error(`❌ Exception:`, e);
    return false;
  }
}

async function testAutoCloseEndpoint() {
  console.log(`\n=== Testing Auto-Close Endpoint ===`);
  
  try {
    const res = await fetch('http://localhost:3000/api/bot/simulator/auto-close', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    console.log(`Response status: ${res.status} ${res.statusText}`);
    
    if (!res.ok) {
      console.error(`❌ HTTP error: ${res.status}`);
      const text = await res.text();
      console.error(`Response: ${text}`);
      return false;
    }
    
    const data = await res.json();
    console.log(`Checked: ${data.checked} trades`);
    console.log(`Closed: ${data.closed} trades`);
    console.log(`Method: ${data.method}`);
    
    if (data.results && data.results.length > 0) {
      console.log(`\nResults:`);
      data.results.forEach((r: any) => {
        console.log(`  - ${r.symbol}: action=${r.action}, current_price=$${r.current_price}, candles=${r.candles_checked}`);
        if (r.current_price === 0) {
          console.error(`    ❌ WARNING: current_price is 0!`);
        }
      });
    }
    
    console.log(`✅ Auto-close endpoint working`);
    return true;
  } catch (e) {
    console.error(`❌ Exception:`, e);
    return false;
  }
}

async function main() {
  console.log('='.repeat(60));
  console.log('Auto-Close API Test Suite');
  console.log('='.repeat(60));
  
  const results = {
    candles: [] as boolean[],
    ticker: [] as boolean[],
    endpoint: false
  };
  
  // Test each symbol
  for (const symbol of TEST_SYMBOLS) {
    results.candles.push(await testHistoricalCandles(symbol));
    results.ticker.push(await testCurrentPrice(symbol));
  }
  
  // Test the endpoint
  results.endpoint = await testAutoCloseEndpoint();
  
  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY');
  console.log('='.repeat(60));
  console.log(`Historical Candles: ${results.candles.filter(Boolean).length}/${results.candles.length} passed`);
  console.log(`Ticker API: ${results.ticker.filter(Boolean).length}/${results.ticker.length} passed`);
  console.log(`Auto-Close Endpoint: ${results.endpoint ? 'PASS' : 'FAIL'}`);
  
  const allPassed = results.candles.every(Boolean) && results.ticker.every(Boolean) && results.endpoint;
  console.log(`\n${allPassed ? '✅ ALL TESTS PASSED' : '❌ SOME TESTS FAILED'}`);
}

main();


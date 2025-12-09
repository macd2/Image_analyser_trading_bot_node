/**
 * Auto-Close Paper Trades API
 * POST /api/bot/simulator/auto-close - Check and close paper trades based on HISTORICAL candle data
 * Fetches all candles from trade creation to now and checks each for SL/TP hit
 * Uses existing trading-db.ts and Bybit API directly - no Python needed
 */

import { NextResponse } from 'next/server';
import { dbQuery, dbExecute, isTradingDbAvailable, TradeRow } from '@/lib/db/trading-db';

interface KlineResult {
  retCode: number;
  result?: {
    // [timestamp, open, high, low, close, volume, turnover]
    list?: [string, string, string, string, string, string, string][];
  };
}

interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface FillResult {
  filled: boolean;
  fillPrice: number | null;
  fillTimestamp: number | null;
  fillCandleIndex: number;
}

interface ExitResult {
  hit: boolean;
  reason: 'tp_hit' | 'sl_hit' | null;
  exitPrice: number | null;
  exitTimestamp: number | null;
  currentPrice: number;
}

const TIMEFRAME_MAP: Record<string, string> = {
  '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
  '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
  '1d': 'D', '1D': 'D'
};

const TIMEFRAME_MS: Record<string, number> = {
  '1m': 60000, '3m': 180000, '5m': 300000, '15m': 900000, '30m': 1800000,
  '1h': 3600000, '2h': 7200000, '4h': 14400000, '6h': 21600000, '12h': 43200000,
  '1d': 86400000, '1D': 86400000
};

/**
 * Store candles to klines table (upsert - ON CONFLICT DO NOTHING)
 */
async function storeCandles(
  symbol: string,
  timeframe: string,
  candles: Candle[]
): Promise<void> {
  if (candles.length === 0) return;

  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;

  // Insert each candle (ON CONFLICT DO NOTHING for duplicates)
  for (const c of candles) {
    try {
      await dbExecute(
        `INSERT INTO klines (symbol, timeframe, category, start_time, open_price, high_price, low_price, close_price, volume, turnover)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (symbol, timeframe, start_time) DO NOTHING`,
        [normSymbol, timeframe, 'linear', c.timestamp, c.open, c.high, c.low, c.close, 0, 0]
      );
    } catch {
      // Ignore duplicate key errors
    }
  }
}

/**
 * Fetch candles from database first, then API if missing
 * Always stores fetched candles to database for future use
 */
async function getHistoricalCandles(
  symbol: string,
  timeframe: string,
  startTime: number // Unix timestamp in ms
): Promise<Candle[]> {
  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const now = Date.now();

  // First, try to get candles from database
  const dbCandles = await dbQuery<{
    start_time: number;
    open_price: number;
    high_price: number;
    low_price: number;
    close_price: number;
  }>(
    `SELECT start_time, open_price, high_price, low_price, close_price
     FROM klines
     WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
     ORDER BY start_time ASC`,
    [normSymbol, timeframe, startTime, now]
  );

  // Calculate how many candles we should have
  const tfMs = TIMEFRAME_MS[timeframe] || 3600000;
  const expectedCandles = Math.ceil((now - startTime) / tfMs);

  // If we have enough candles from DB, use them
  if (dbCandles.length >= expectedCandles * 0.8) { // 80% threshold
    console.log(`[Auto-Close] Using ${dbCandles.length} cached candles for ${symbol} ${timeframe}`);
    return dbCandles.map(c => ({
      timestamp: c.start_time,
      open: c.open_price,
      high: c.high_price,
      low: c.low_price,
      close: c.close_price
    }));
  }

  // Otherwise fetch from Bybit API
  console.log(`[Auto-Close] Fetching candles from Bybit for ${symbol} ${timeframe} (had ${dbCandles.length}, need ~${expectedCandles})`);

  try {
    const apiSymbol = normSymbol;
    const interval = TIMEFRAME_MAP[timeframe] || '60';

    // Bybit allows max 200 candles per request
    const limit = Math.min(expectedCandles + 5, 200);

    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&start=${startTime}&limit=${limit}`;
    const res = await fetch(url);

    if (!res.ok) {
      console.error(`[Auto-Close] Bybit API error for ${symbol}: ${res.status} ${res.statusText}`);
      // Fall back to whatever we have in DB
      return dbCandles.map(c => ({
        timestamp: c.start_time,
        open: c.open_price,
        high: c.high_price,
        low: c.low_price,
        close: c.close_price
      }));
    }

    const data: KlineResult = await res.json();
    if (data.retCode !== 0 || !data.result?.list) {
      console.error(`[Auto-Close] Bybit returned error for ${symbol}: retCode=${data.retCode}`);
      return dbCandles.map(c => ({
        timestamp: c.start_time,
        open: c.open_price,
        high: c.high_price,
        low: c.low_price,
        close: c.close_price
      }));
    }

    // Parse candles - Bybit returns newest first, so reverse
    const candles: Candle[] = data.result.list.map(c => ({
      timestamp: parseInt(c[0]),
      open: parseFloat(c[1]),
      high: parseFloat(c[2]),
      low: parseFloat(c[3]),
      close: parseFloat(c[4])
    })).reverse(); // Oldest first for chronological checking

    // Store fetched candles to database for future use
    await storeCandles(symbol, timeframe, candles);
    console.log(`[Auto-Close] Stored ${candles.length} candles to database for ${symbol} ${timeframe}`);

    return candles;
  } catch (e) {
    console.error(`Failed to get candles for ${symbol}:`, e);
    // Fall back to DB candles
    return dbCandles.map(c => ({
      timestamp: c.start_time,
      open: c.open_price,
      high: c.high_price,
      low: c.low_price,
      close: c.close_price
    }));
  }
}

/**
 * Get current ticker price from Bybit as fallback
 */
async function getCurrentPrice(symbol: string): Promise<number> {
  try {
    const apiSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
    const res = await fetch(
      `https://api.bybit.com/v5/market/tickers?category=linear&symbol=${apiSymbol}`
    );

    if (!res.ok) return 0;

    const data = await res.json();
    if (data.retCode === 0 && data.result?.list?.[0]?.lastPrice) {
      return parseFloat(data.result.list[0].lastPrice);
    }
    return 0;
  } catch (e) {
    console.error(`Failed to get current price for ${symbol}:`, e);
    return 0;
  }
}

/**
 * Find the first candle where entry price was touched (trade fill)
 * For LONG: entry price must be touched (low <= entry <= high)
 * For SHORT: entry price must be touched (low <= entry <= high)
 */
function findFillCandle(
  candles: Candle[],
  entryPrice: number
): FillResult {
  for (let i = 0; i < candles.length; i++) {
    const candle = candles[i];
    // Entry is filled when price touches entry level
    if (candle.low <= entryPrice && entryPrice <= candle.high) {
      return {
        filled: true,
        fillPrice: entryPrice,
        fillTimestamp: candle.timestamp,
        fillCandleIndex: i
      };
    }
  }
  return { filled: false, fillPrice: null, fillTimestamp: null, fillCandleIndex: -1 };
}

/**
 * Check historical candles for SL/TP hit
 * Returns the first candle where SL or TP was hit
 * IMPORTANT: Only checks candles AFTER the fill candle
 */
function checkHistoricalSLTP(
  candles: Candle[],
  isLong: boolean,
  stopLoss: number,
  takeProfit: number,
  startFromIndex: number = 0
): ExitResult {
  const currentPrice = candles.length > 0 ? candles[candles.length - 1].close : 0;

  // Start checking from the candle AFTER fill
  for (let i = startFromIndex; i < candles.length; i++) {
    const candle = candles[i];
    // For each candle, check if high/low crossed SL or TP
    // We need to determine which was hit FIRST within the candle

    if (isLong) {
      // Long position: SL hit if low <= stopLoss, TP hit if high >= takeProfit
      const slHit = candle.low <= stopLoss;
      const tpHit = candle.high >= takeProfit;

      if (slHit && tpHit) {
        // Both hit in same candle - determine which first by checking open price
        // If open is closer to SL, assume SL hit first (conservative)
        if (Math.abs(candle.open - stopLoss) < Math.abs(candle.open - takeProfit)) {
          return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
        } else {
          return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
        }
      } else if (slHit) {
        return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
      } else if (tpHit) {
        return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
      }
    } else {
      // Short position: SL hit if high >= stopLoss, TP hit if low <= takeProfit
      const slHit = candle.high >= stopLoss;
      const tpHit = candle.low <= takeProfit;

      if (slHit && tpHit) {
        // Both hit in same candle - determine which first
        if (Math.abs(candle.open - stopLoss) < Math.abs(candle.open - takeProfit)) {
          return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
        } else {
          return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
        }
      } else if (slHit) {
        return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
      } else if (tpHit) {
        return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
      }
    }
  }

  return { hit: false, reason: null, exitPrice: null, exitTimestamp: null, currentPrice };
}

/**
 * POST /api/bot/simulator/auto-close
 * Check all open paper trades using HISTORICAL candles from trade creation
 * Accurately detects if SL/TP was hit at any point since trade was created
 */
export async function POST() {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Get all open paper trades
    const openTrades = await dbQuery<TradeRow>(`
      SELECT
        t.*,
        COALESCE(t.timeframe, rec.timeframe) as timeframe,
        COALESCE(t.entry_price, rec.entry_price) as entry_price,
        COALESCE(t.stop_loss, rec.stop_loss) as stop_loss,
        COALESCE(t.take_profit, rec.take_profit) as take_profit
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      WHERE t.pnl IS NULL
        AND t.status IN ('paper_trade', 'pending_fill', 'filled')
      ORDER BY t.created_at DESC
    `);

    const results: Array<{
      trade_id: string;
      symbol: string;
      action: 'checked' | 'closed' | 'filled';
      current_price: number;
      fill_timestamp?: string;
      exit_reason?: string;
      exit_timestamp?: string;
      pnl?: number;
      candles_checked?: number;
      checked_at?: string;
    }> = [];

    let closedCount = 0;
    let filledCount = 0;

    for (const trade of openTrades) {
      const isLong = trade.side === 'Buy';
      const entryPrice = trade.entry_price || 0;
      const stopLoss = trade.stop_loss || 0;
      const takeProfit = trade.take_profit || 0;
      const timeframe = trade.timeframe || '1h';

      // Parse trade creation time
      const createdAt = new Date(trade.created_at).getTime();

      // Fetch all candles from trade creation to now
      const candles = await getHistoricalCandles(trade.symbol, timeframe, createdAt);

      if (candles.length === 0) {
        // Fallback: get current price from ticker API
        const currentPrice = await getCurrentPrice(trade.symbol);
        console.log(`[Auto-Close] No candles for ${trade.symbol}, using ticker price: ${currentPrice}`);

        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: currentPrice,
          candles_checked: 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // STEP 1: Check if trade is already filled or find fill candle
      let fillCandleIndex = 0;
      const alreadyFilled = trade.status === 'filled' && trade.filled_at;

      if (alreadyFilled) {
        // Trade already filled - find the fill candle index to start SL/TP check from
        const filledAtMs = new Date(trade.filled_at as string).getTime();
        fillCandleIndex = candles.findIndex(c => c.timestamp >= filledAtMs);
        if (fillCandleIndex === -1) fillCandleIndex = 0;
      } else {
        // Find fill candle (first candle where entry price was touched)
        const fillResult = findFillCandle(candles, entryPrice);

        if (!fillResult.filled) {
          // Trade not filled yet - still pending
          const currentPrice = candles[candles.length - 1].close;
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: currentPrice,
            candles_checked: candles.length,
            checked_at: new Date().toISOString()
          });
          continue;
        }

        // Trade is now filled - update database with fill info
        const fillTime = new Date(fillResult.fillTimestamp!).toISOString();
        await dbExecute(`
          UPDATE trades SET
            fill_price = ?,
            fill_time = ?,
            filled_at = ?,
            status = 'filled'
          WHERE id = ?
        `, [
          fillResult.fillPrice,
          fillTime,
          fillTime,
          trade.id
        ]);

        filledCount++;
        fillCandleIndex = fillResult.fillCandleIndex + 1; // Start SL/TP check from NEXT candle
        console.log(`[Auto-Close] ${trade.symbol} FILLED at ${fillResult.fillPrice} on ${fillTime}`);
      }

      // STEP 2: Check for SL/TP hit starting from candle AFTER fill
      const exitResult = checkHistoricalSLTP(candles, isLong, stopLoss, takeProfit, fillCandleIndex);

      if (exitResult.hit && exitResult.exitPrice && exitResult.reason) {
        // Calculate P&L using fill price (which equals entry price for limit orders)
        const fillPrice = trade.fill_price || entryPrice;
        const qty = trade.quantity || 1;
        const pnl = isLong
          ? (exitResult.exitPrice - fillPrice) * qty
          : (fillPrice - exitResult.exitPrice) * qty;
        const pnlPercent = fillPrice > 0 ? (pnl / (fillPrice * qty)) * 100 : 0;

        // Get exit timestamp as ISO string
        const exitTime = exitResult.exitTimestamp
          ? new Date(exitResult.exitTimestamp).toISOString()
          : new Date().toISOString();

        // Update trade in database with actual exit time
        await dbExecute(`
          UPDATE trades SET
            exit_price = ?,
            exit_reason = ?,
            closed_at = ?,
            pnl = ?,
            pnl_percent = ?,
            status = 'closed'
          WHERE id = ?
        `, [
          exitResult.exitPrice,
          exitResult.reason,
          exitTime,
          Math.round(pnl * 100) / 100,
          Math.round(pnlPercent * 100) / 100,
          trade.id
        ]);

        closedCount++;
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'closed',
          current_price: exitResult.currentPrice,
          exit_reason: exitResult.reason,
          exit_timestamp: exitTime,
          pnl: Math.round(pnl * 100) / 100,
          candles_checked: candles.length,
          checked_at: new Date().toISOString()
        });
      } else {
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: alreadyFilled ? 'checked' : 'filled',
          current_price: exitResult.currentPrice,
          candles_checked: candles.length,
          checked_at: new Date().toISOString()
        });
      }
    }

    return NextResponse.json({
      success: true,
      checked: openTrades.length,
      filled: filledCount,
      closed: closedCount,
      method: 'historical_candles_with_fill',
      results
    });
  } catch (error) {
    console.error('Auto-close error:', error);
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}


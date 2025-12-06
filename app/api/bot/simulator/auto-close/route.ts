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
 * Fetch historical candles from trade creation to now
 */
async function getHistoricalCandles(
  symbol: string,
  timeframe: string,
  startTime: number // Unix timestamp in ms
): Promise<Candle[]> {
  try {
    const apiSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
    const interval = TIMEFRAME_MAP[timeframe] || '60';
    const now = Date.now();

    // Calculate how many candles we need
    const tfMs = TIMEFRAME_MS[timeframe] || 3600000;
    const candlesNeeded = Math.ceil((now - startTime) / tfMs) + 1;

    // Bybit allows max 200 candles per request
    const limit = Math.min(candlesNeeded, 200);

    const res = await fetch(
      `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&start=${startTime}&limit=${limit}`
    );

    if (!res.ok) return [];

    const data: KlineResult = await res.json();
    if (data.retCode !== 0 || !data.result?.list) return [];

    // Parse candles - Bybit returns newest first, so reverse
    const candles: Candle[] = data.result.list.map(c => ({
      timestamp: parseInt(c[0]),
      open: parseFloat(c[1]),
      high: parseFloat(c[2]),
      low: parseFloat(c[3]),
      close: parseFloat(c[4])
    })).reverse(); // Oldest first for chronological checking

    return candles;
  } catch (e) {
    console.error(`Failed to get candles for ${symbol}:`, e);
    return [];
  }
}

/**
 * Check historical candles for SL/TP hit
 * Returns the first candle where SL or TP was hit
 */
function checkHistoricalSLTP(
  candles: Candle[],
  isLong: boolean,
  stopLoss: number,
  takeProfit: number
): ExitResult {
  const currentPrice = candles.length > 0 ? candles[candles.length - 1].close : 0;

  for (const candle of candles) {
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
      action: 'checked' | 'closed';
      current_price: number;
      exit_reason?: string;
      exit_timestamp?: string;
      pnl?: number;
      candles_checked?: number;
      checked_at?: string;
    }> = [];

    let closedCount = 0;

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
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: 0,
          candles_checked: 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // Check historical candles for SL/TP hit
      const exitResult = checkHistoricalSLTP(candles, isLong, stopLoss, takeProfit);

      if (exitResult.hit && exitResult.exitPrice && exitResult.reason) {
        // Calculate P&L
        const qty = trade.quantity || 1;
        const pnl = isLong
          ? (exitResult.exitPrice - entryPrice) * qty
          : (entryPrice - exitResult.exitPrice) * qty;
        const pnlPercent = entryPrice > 0 ? (pnl / (entryPrice * qty)) * 100 : 0;

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
          action: 'checked',
          current_price: exitResult.currentPrice,
          candles_checked: candles.length,
          checked_at: new Date().toISOString()
        });
      }
    }

    return NextResponse.json({
      success: true,
      checked: openTrades.length,
      closed: closedCount,
      method: 'historical_candles',
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


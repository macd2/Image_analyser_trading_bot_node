/**
 * Bot Trade Candles API - GET historical candles for a trade
 * Fetches candles from database cache for displaying on trade charts
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery } from '@/lib/db/trading-db';

export interface CandlesResponse {
  candles: Array<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  symbol: string;
  timeframe: string;
  error?: string;
}

/**
 * GET /api/bot/trade-candles - Get historical candles for a trade
 * Query params:
 *   - symbol: string (required) - Trading pair symbol (e.g., BTCUSDT)
 *   - timeframe: string (required) - Candle timeframe (e.g., 1h, 4h, 1d)
 *   - timestamp: number (required) - Trade timestamp in milliseconds
 *   - before: number (default: 50) - Number of candles before the trade
 *   - after: number (default: 20) - Number of candles after the trade
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol');
  const timeframe = searchParams.get('timeframe');
  const timestamp = searchParams.get('timestamp');
  const before = parseInt(searchParams.get('before') || '50', 10);
  const after = parseInt(searchParams.get('after') || '20', 10);

  if (!symbol || !timeframe || !timestamp) {
    return NextResponse.json(
      { error: 'Missing required parameters: symbol, timeframe, timestamp' },
      { status: 400 }
    );
  }

  try {
    const timestampMs = parseInt(timestamp, 10);
    const timeframeMs = getTimeframeMs(timeframe);

    // Convert Bybit format to our format if needed
    const dbTimeframe = bybitToOurFormat(timeframe);

    // Calculate time window
    const startTime = timestampMs - (before * timeframeMs);
    const endTime = timestampMs + (after * timeframeMs);

    // Query database for candles
    const candles = await dbQuery<any>(`
      SELECT
        start_time as time,
        open_price as open,
        high_price as high,
        low_price as low,
        close_price as close,
        volume
      FROM klines
      WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
      ORDER BY start_time ASC
    `, [symbol, dbTimeframe, startTime, endTime]);

    // Ensure numeric types (PostgreSQL may return strings)
    // CRITICAL: Convert milliseconds to seconds for lightweight-charts
    // Database stores start_time in milliseconds, but chart expects seconds
    const normalizedCandles = (candles || []).map(candle => {
      const timeMs = Number(candle.time);
      // If timestamp is in milliseconds (> 10 billion), convert to seconds
      const timeSeconds = timeMs > 10000000000 ? Math.floor(timeMs / 1000) : timeMs;
      return {
        ...candle,
        time: timeSeconds,
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
        volume: Number(candle.volume),
      };
    });

    return NextResponse.json({
      candles: normalizedCandles,
      symbol: symbol,
      timeframe: timeframe
    });
  } catch (error) {
    console.error('Trade candles GET error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch candles' },
      { status: 500 }
    );
  }
}

/**
 * Convert Bybit format timeframe to our format
 * Bybit uses: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M
 * We use: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w, 1M
 */
function bybitToOurFormat(timeframe: string): string {
  const map: Record<string, string> = {
    '1': '1m',
    '3': '3m',
    '5': '5m',
    '15': '15m',
    '30': '30m',
    '60': '1h',
    '120': '2h',
    '240': '4h',
    '360': '6h',
    '720': '12h',
    'D': '1d',
    'W': '1w',
    'M': '1M',
  };
  return map[timeframe] || timeframe; // Return as-is if already in our format
}

/**
 * Convert timeframe string to milliseconds
 */
function getTimeframeMs(timeframe: string): number {
  const timeframeMap: Record<string, number> = {
    '1m': 60 * 1000,
    '3m': 3 * 60 * 1000,
    '5m': 5 * 60 * 1000,
    '15m': 15 * 60 * 1000,
    '30m': 30 * 60 * 1000,
    '1h': 60 * 60 * 1000,
    '2h': 2 * 60 * 60 * 1000,
    '4h': 4 * 60 * 60 * 1000,
    '6h': 6 * 60 * 60 * 1000,
    '12h': 12 * 60 * 60 * 1000,
    '1d': 24 * 60 * 60 * 1000,
    '1w': 7 * 24 * 60 * 60 * 1000,
    '1M': 30 * 24 * 60 * 60 * 1000,
  };
  return timeframeMap[timeframe] || 60 * 60 * 1000; // Default to 1h
}


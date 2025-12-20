/**
 * Bot Spread Pair Candles API - GET historical candles for pair symbol in spread-based trades
 * Fetches candles from database cache for the pair asset in cointegration trades
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
  pair_symbol: string;
  timeframe: string;
  error?: string;
}

/**
 * GET /api/bot/spread-pair-candles - Get historical candles for pair symbol in spread trade
 * Query params:
 *   - pair_symbol: string (required) - Pair symbol (e.g., ETHUSDT)
 *   - timeframe: string (required) - Candle timeframe (e.g., 1h, 4h, 1d)
 *   - timestamp: number (required) - Trade timestamp in milliseconds
 *   - before: number (default: 50) - Number of candles before the trade
 *   - after: number (default: 20) - Number of candles after the trade
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const pairSymbol = searchParams.get('pair_symbol');
  const timeframe = searchParams.get('timeframe');
  const timestamp = searchParams.get('timestamp');
  const before = parseInt(searchParams.get('before') || '50', 10);
  const after = parseInt(searchParams.get('after') || '20', 10);

  if (!pairSymbol || !timeframe || !timestamp) {
    return NextResponse.json(
      { error: 'Missing required parameters: pair_symbol, timeframe, timestamp' },
      { status: 400 }
    );
  }

  try {
    const timestampMs = parseInt(timestamp, 10);
    const timeframeMs = getTimeframeMs(timeframe);

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
    `, [pairSymbol, timeframe, startTime, endTime]);

    // Ensure numeric types (PostgreSQL may return strings)
    const normalizedCandles = (candles || []).map(candle => ({
      ...candle,
      time: Number(candle.time),
      open: Number(candle.open),
      high: Number(candle.high),
      low: Number(candle.low),
      close: Number(candle.close),
      volume: Number(candle.volume),
    }));

    return NextResponse.json({
      candles: normalizedCandles,
      pair_symbol: pairSymbol,
      timeframe: timeframe
    });
  } catch (error) {
    console.error('Spread pair candles GET error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch pair candles' },
      { status: 500 }
    );
  }
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


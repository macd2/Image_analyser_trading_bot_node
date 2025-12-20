/**
 * Bot Spread Pair Candles API - GET historical candles for pair symbol in spread-based trades
 * Fetches candles from database cache, with on-demand fetching from exchange if needed
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, dbExecute } from '@/lib/db/trading-db';

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
    let candles = await dbQuery<any>(`
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

    // If no candles found, try to fetch from exchange
    if (!candles || candles.length === 0) {
      console.log(`[Spread Pair Candles] No candles found for ${pairSymbol} ${timeframe}, fetching from exchange...`);
      try {
        const fetchedCandles = await fetchCandlesFromExchange(pairSymbol, timeframe, startTime, endTime);
        if (fetchedCandles && fetchedCandles.length > 0) {
          // Store fetched candles in database
          await storeCandlesInDatabase(fetchedCandles, pairSymbol, timeframe);
          candles = fetchedCandles;
          console.log(`[Spread Pair Candles] Fetched and stored ${fetchedCandles.length} candles for ${pairSymbol}`);
        }
      } catch (fetchError) {
        console.warn(`[Spread Pair Candles] Failed to fetch candles from exchange: ${fetchError}`);
        // Continue with empty candles - frontend will handle gracefully
      }
    }

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

/**
 * Fetch candles from Bybit exchange
 */
async function fetchCandlesFromExchange(
  symbol: string,
  timeframe: string,
  startTimeMs: number,
  endTimeMs: number
): Promise<any[]> {
  try {
    // Convert timeframe to Bybit format
    const bybitTimeframe = timeframeToBybit(timeframe);

    // Fetch from Bybit API
    const response = await fetch(
      `https://api.bybit.com/v5/market/kline?category=spot&symbol=${symbol}&interval=${bybitTimeframe}&start=${Math.floor(startTimeMs / 1000)}&end=${Math.floor(endTimeMs / 1000)}&limit=1000`
    );

    if (!response.ok) {
      throw new Error(`Bybit API error: ${response.statusText}`);
    }

    const data = await response.json();
    if (!data.result || !data.result.list) {
      return [];
    }

    // Convert Bybit format to our format
    return data.result.list.map((candle: any[]) => ({
      time: parseInt(candle[0]) * 1000, // Convert to milliseconds
      open: parseFloat(candle[1]),
      high: parseFloat(candle[2]),
      low: parseFloat(candle[3]),
      close: parseFloat(candle[4]),
      volume: parseFloat(candle[5]),
    }));
  } catch (error) {
    console.error(`Failed to fetch candles from Bybit for ${symbol}:`, error);
    throw error;
  }
}

/**
 * Convert our timeframe format to Bybit format
 */
function timeframeToBybit(timeframe: string): string {
  const map: Record<string, string> = {
    '1m': '1',
    '3m': '3',
    '5m': '5',
    '15m': '15',
    '30m': '30',
    '1h': '60',
    '2h': '120',
    '4h': '240',
    '6h': '360',
    '12h': '720',
    '1d': 'D',
    '1w': 'W',
    '1M': 'M',
  };
  return map[timeframe] || '60';
}

/**
 * Store candles in database
 */
async function storeCandlesInDatabase(
  candles: any[],
  symbol: string,
  timeframe: string
): Promise<void> {
  try {
    for (const candle of candles) {
      await dbExecute(
        `INSERT INTO klines (symbol, timeframe, category, start_time, open_price, high_price, low_price, close_price, volume, turnover)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT (symbol, timeframe, start_time) DO NOTHING`,
        [
          symbol,
          timeframe,
          'spot',
          candle.time,
          candle.open,
          candle.high,
          candle.low,
          candle.close,
          candle.volume,
          0 // turnover not available from API
        ]
      );
    }
  } catch (error) {
    console.error(`Failed to store candles in database for ${symbol}:`, error);
    throw error;
  }
}


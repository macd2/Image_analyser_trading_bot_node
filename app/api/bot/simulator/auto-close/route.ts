/**
 * Auto-Close Paper Trades API
 * POST /api/bot/simulator/auto-close - Check and close paper trades based on HISTORICAL candle data
 * Fetches all candles from trade creation to now and checks each for SL/TP hit
 * Also checks for max_open_bars setting to cancel stale trades
 * Uses existing trading-db.ts and Bybit API directly - no Python needed
 */

import { NextResponse } from 'next/server';
import { dbQuery, dbExecute, isTradingDbAvailable, TradeRow } from '@/lib/db/trading-db';
import { getSettings } from '@/lib/db/settings';

type MaxOpenBarsConfig = Record<string, number>;

interface SimulatorSettings {
  max_open_bars_before_filled?: MaxOpenBarsConfig;
  max_open_bars_after_filled?: MaxOpenBarsConfig;
  // Strategy-type-specific settings
  max_open_bars_before_filled_price_based?: MaxOpenBarsConfig;
  max_open_bars_after_filled_price_based?: MaxOpenBarsConfig;
  max_open_bars_before_filled_spread_based?: MaxOpenBarsConfig;
  max_open_bars_after_filled_spread_based?: MaxOpenBarsConfig;
}

// Read max_open_bars configs from database (persisted settings)
async function getMaxOpenBarsConfigs(): Promise<{
  before_filled: MaxOpenBarsConfig;
  after_filled: MaxOpenBarsConfig;
  before_filled_price_based: MaxOpenBarsConfig;
  after_filled_price_based: MaxOpenBarsConfig;
  before_filled_spread_based: MaxOpenBarsConfig;
  after_filled_spread_based: MaxOpenBarsConfig;
}> {
  try {
    const settings = await getSettings<SimulatorSettings>('simulator');
    return {
      before_filled: (settings?.max_open_bars_before_filled && typeof settings.max_open_bars_before_filled === 'object') ? settings.max_open_bars_before_filled : {},
      after_filled: (settings?.max_open_bars_after_filled && typeof settings.max_open_bars_after_filled === 'object') ? settings.max_open_bars_after_filled : {},
      before_filled_price_based: (settings?.max_open_bars_before_filled_price_based && typeof settings.max_open_bars_before_filled_price_based === 'object') ? settings.max_open_bars_before_filled_price_based : {},
      after_filled_price_based: (settings?.max_open_bars_after_filled_price_based && typeof settings.max_open_bars_after_filled_price_based === 'object') ? settings.max_open_bars_after_filled_price_based : {},
      before_filled_spread_based: (settings?.max_open_bars_before_filled_spread_based && typeof settings.max_open_bars_before_filled_spread_based === 'object') ? settings.max_open_bars_before_filled_spread_based : {},
      after_filled_spread_based: (settings?.max_open_bars_after_filled_spread_based && typeof settings.max_open_bars_after_filled_spread_based === 'object') ? settings.max_open_bars_after_filled_spread_based : {}
    };
  } catch {
    // Ignore errors, return defaults
  }
  return {
    before_filled: {},
    after_filled: {},
    before_filled_price_based: {},
    after_filled_price_based: {},
    before_filled_spread_based: {},
    after_filled_spread_based: {}
  }; // Empty = all disabled
}

async function getMaxOpenBarsForTimeframe(
  timeframe: string,
  tradeStatus: 'pending_fill' | 'paper_trade' | 'filled',
  strategyType?: string | null
): Promise<number> {
  const configs = await getMaxOpenBarsConfigs();

  // Determine which config to use based on strategy type
  let config: MaxOpenBarsConfig;

  if (strategyType === 'price_based') {
    // Use price-based strategy config, fall back to global if not set
    config = (tradeStatus === 'filled')
      ? { ...configs.after_filled, ...configs.after_filled_price_based }
      : { ...configs.before_filled, ...configs.before_filled_price_based };
  } else if (strategyType === 'spread_based') {
    // Use spread-based strategy config, fall back to global if not set
    config = (tradeStatus === 'filled')
      ? { ...configs.after_filled, ...configs.after_filled_spread_based }
      : { ...configs.before_filled, ...configs.before_filled_spread_based };
  } else {
    // Unknown or null strategy type - use global config
    config = (tradeStatus === 'filled') ? configs.after_filled : configs.before_filled;
  }

  // Try exact match first, then normalized (1D -> 1d)
  return config[timeframe] ?? config[timeframe.toLowerCase()] ?? 0;
}

/**
 * SANITY CHECK: Validate timestamp ordering for trade lifecycle
 * Returns error message if validation fails, null if valid
 * CRITICAL: A trade must follow this timeline: created_at <= filled_at <= closed_at
 */
function validateTradeTimestamps(
  createdAt: string | Date,
  filledAt: string | Date | null,
  closedAt: string | Date | null
): string | null {
  try {
    const createdMs = new Date(createdAt).getTime();

    if (isNaN(createdMs)) {
      return `Invalid created_at timestamp: ${createdAt}`;
    }

    if (filledAt) {
      const filledMs = new Date(filledAt).getTime();
      if (isNaN(filledMs)) {
        return `Invalid filled_at timestamp: ${filledAt}`;
      }
      if (filledMs < createdMs) {
        return `CRITICAL: filled_at (${new Date(filledMs).toISOString()}) is BEFORE created_at (${new Date(createdMs).toISOString()})`;
      }

      if (closedAt) {
        const closedMs = new Date(closedAt).getTime();
        if (isNaN(closedMs)) {
          return `Invalid closed_at timestamp: ${closedAt}`;
        }
        if (closedMs < createdMs) {
          return `CRITICAL: closed_at (${new Date(closedMs).toISOString()}) is BEFORE created_at (${new Date(createdMs).toISOString()})`;
        }
        if (closedMs < filledMs) {
          return `CRITICAL: closed_at (${new Date(closedMs).toISOString()}) is BEFORE filled_at (${new Date(filledMs).toISOString()})`;
        }
      }
    } else if (closedAt) {
      // Trade is closed but never filled - this is invalid
      return `CRITICAL: Trade has closed_at but no filled_at - a trade cannot close without being filled first`;
    }

    return null; // All validations passed
  } catch (e) {
    return `Timestamp validation error: ${e}`;
  }
}

/**
 * Extract strategy name from instance settings JSON
 */
function getStrategyNameFromSettings(settingsJson: unknown): string | null {
  try {
    if (!settingsJson) return null;
    const settings = typeof settingsJson === 'string' ? JSON.parse(settingsJson) : settingsJson;
    return settings?.strategy || null;
  } catch {
    return null;
  }
}

/**
 * Normalize timestamp to milliseconds (number)
 * Handles: ISO strings, Date objects, numbers, null/undefined
 * Returns: milliseconds since epoch or null if invalid
 */
function normalizeTimestamp(ts: unknown): number | null {
  if (ts === null || ts === undefined) {
    return null;
  }

  // Already a number - validate it's a valid timestamp
  if (typeof ts === 'number') {
    if (isNaN(ts) || ts < 0) {
      return null;
    }
    return ts;
  }

  // String - try to parse as ISO or number
  if (typeof ts === 'string') {
    // Try parsing as ISO string first
    const isoDate = new Date(ts);
    if (!isNaN(isoDate.getTime())) {
      return isoDate.getTime();
    }
    // Try parsing as number string
    const numVal = parseInt(ts, 10);
    if (!isNaN(numVal) && numVal > 0) {
      return numVal;
    }
    return null;
  }

  // Date object
  if (ts instanceof Date) {
    const ms = ts.getTime();
    if (!isNaN(ms)) {
      return ms;
    }
    return null;
  }

  return null;
}

/**
 * Log error to database for audit trail
 * Stores errors in a way that can be queried later for debugging
 */
async function logSimulatorError(
  tradeId: string,
  errorType: string,
  errorMessage: string,
  metadata?: Record<string, any>
): Promise<void> {
  try {
    console.error(`[SIMULATOR ERROR] Trade ${tradeId} - ${errorType}: ${errorMessage}`, metadata || {});

    // Store error in database for audit trail
    // Using a simple approach: store as JSON in a logs table or update trade with error info
    // For now, we'll just ensure it's logged to console with structured format
    // TODO: Consider adding a simulator_errors table for persistent error tracking
  } catch (e) {
    console.error(`[SIMULATOR] Failed to log error:`, e);
  }
}

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
  volume?: number;
  turnover?: number;
}

interface FillResult {
  filled: boolean;
  fillPrice: number | null;
  fillTimestamp: number | null;
  fillCandleIndex: number;
  pair_fill_price?: number | null;  // For spread-based trades
}

interface ExitResult {
  hit: boolean;
  reason: 'tp_hit' | 'sl_hit' | null;
  exitPrice: number | null;
  exitTimestamp: number | null;
  currentPrice: number;
  pair_exit_price?: number | null;  // For spread-based trades
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
        [normSymbol, timeframe, 'linear', c.timestamp, c.open, c.high, c.low, c.close, c.volume || 0, c.turnover || 0]
      );
    } catch {
      // Ignore duplicate key errors
    }
  }
}

/**
 * Fetch candles from Bybit and store only COMPLETE candles to database
 * A candle is complete if it started more than 1 timeframe ago
 */
async function fetchAndStoreCandles(
  symbol: string,
  timeframe: string
): Promise<void> {
  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const tfMs = TIMEFRAME_MS[timeframe] || 3600000;
  const now = Date.now();

  try {
    const apiSymbol = normSymbol;
    const interval = TIMEFRAME_MAP[timeframe] || '60';
    const limit = 200; // Max allowed by Bybit

    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&limit=${limit}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!res.ok) {
      console.error(`[Auto-Close] Bybit API error for ${symbol}: ${res.status}`);
      return;
    }

    const data: KlineResult = await res.json();
    if (data.retCode !== 0 || !data.result?.list) {
      console.error(`[Auto-Close] Bybit error for ${symbol}: ${(data as any).retMsg}`);
      return;
    }

    // Parse candles - Bybit returns newest first, so reverse
    const candles: Candle[] = data.result.list.map(c => ({
      timestamp: parseInt(c[0]),
      open: parseFloat(c[1]),
      high: parseFloat(c[2]),
      low: parseFloat(c[3]),
      close: parseFloat(c[4]),
      volume: parseFloat(c[5] || '0'),
      turnover: parseFloat(c[6] || '0')
    })).reverse();

    // Filter to only store COMPLETE candles (older than 1 timeframe)
    const candlesToStore = candles.filter(c => {
      const candleAge = now - c.timestamp;
      return candleAge >= tfMs;
    });

    if (candlesToStore.length < candles.length) {
      console.log(`[Auto-Close] Filtered out ${candles.length - candlesToStore.length} incomplete candle(s)`);
    }

    await storeCandles(symbol, timeframe, candlesToStore);
    console.log(`[Auto-Close] Stored ${candlesToStore.length} candles for ${symbol} ${timeframe}`);
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      console.error(`[Auto-Close] Bybit API timeout for ${symbol}`);
    } else {
      console.error(`[Auto-Close] Failed to fetch candles for ${symbol}:`, e);
    }
  }
}

/**
 * Fetch candles from database first, then API if missing
 * Always stores fetched candles to database for future use
 * CRITICAL: Ensures klines table is up-to-date by checking if latest candle is complete
 */
async function getHistoricalCandles(
  symbol: string,
  timeframe: string,
  startTime: number // Unix timestamp in ms
): Promise<Candle[]> {
  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const now = Date.now();
  const tfMs = TIMEFRAME_MS[timeframe] || 3600000;

  // STEP 1: Check if the klines table has up-to-date data for this symbol/timeframe
  // Get the latest candle timestamp in the database
  const latestCandleResult = await dbQuery<{ max_ts: number | null }>(
    `SELECT MAX(start_time) as max_ts FROM klines WHERE symbol = ? AND timeframe = ?`,
    [normSymbol, timeframe]
  );

  // PostgreSQL bigint is now configured to return as number (see lib/db/client.ts)
  // But normalize it just in case it comes back as a string
  const rawLatestCandleTs = latestCandleResult[0]?.max_ts;
  const latestCandleTs = normalizeTimestamp(rawLatestCandleTs) || 0;
  const latestCompleteCandle = Math.max(0, now - (now % tfMs) - tfMs); // Timestamp of the latest COMPLETE candle (ensure >= 0)

  // Validate timestamps before converting to Date (prevent Invalid time value errors)
  const isValidTimestamp = (ts: number) => ts > 0 && ts < 8640000000000000; // Max valid JS timestamp
  const latestCandleStr = isValidTimestamp(latestCandleTs) ? new Date(latestCandleTs).toISOString() : 'no candles';
  const latestCompleteStr = isValidTimestamp(latestCompleteCandle) ? new Date(latestCompleteCandle).toISOString() : 'no complete candles yet';
  console.log(`[Auto-Close] ${symbol} ${timeframe}: latest candle in DB=${latestCandleStr}, latest complete=${latestCompleteStr}`);

  // If the latest candle in DB is older than the latest complete candle, we need to fetch from Bybit
  const needsFetch = latestCandleTs < latestCompleteCandle;

  if (needsFetch) {
    console.log(`[Auto-Close] Klines table is stale for ${symbol} ${timeframe}, fetching from Bybit...`);
    // Fetch from Bybit to update the database with newer complete candles
    await fetchAndStoreCandles(symbol, timeframe);
  }

  // STEP 2: Now query the database for candles >= startTime
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
  const expectedCandles = Math.ceil((now - startTime) / tfMs);

  // If we have enough candles from DB, use them
  if (dbCandles.length >= expectedCandles * 0.8) { // 80% threshold
    console.log(`[Auto-Close] Using ${dbCandles.length} cached candles for ${symbol} ${timeframe}`);
    return dbCandles.map(c => ({
      timestamp: normalizeTimestamp(c.start_time) || 0,
      open: c.open_price,
      high: c.high_price,
      low: c.low_price,
      close: c.close_price
    }));
  }

  // If we don't have candles >= startTime, we need to fetch from Bybit
  // This can happen if the trade was created after the latest candle in the DB
  if (dbCandles.length === 0) {
    const startTimeStr = (startTime > 0 && startTime < 8640000000000000) ? new Date(startTime).toISOString() : startTime.toString();
    console.log(`[Auto-Close] No candles found for ${symbol} ${timeframe} >= ${startTimeStr}, fetching from Bybit...`);
  }

  // Otherwise fetch from Bybit API as fallback
  console.log(`[Auto-Close] Still missing candles for ${symbol} ${timeframe} (had ${dbCandles.length}, need ~${expectedCandles}), fetching from Bybit...`);

  try {
    const apiSymbol = normSymbol;
    const interval = TIMEFRAME_MAP[timeframe] || '60';
    const limit = Math.min(expectedCandles + 5, 200);

    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&limit=${limit}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);

    if (!res.ok) {
      console.error(`[Auto-Close] Bybit API error for ${symbol}: ${res.status}`);
      return dbCandles.map(c => ({
        timestamp: normalizeTimestamp(c.start_time) || 0,
        open: c.open_price,
        high: c.high_price,
        low: c.low_price,
        close: c.close_price
      }));
    }

    const data: KlineResult = await res.json();
    if (data.retCode !== 0 || !data.result?.list) {
      console.error(`[Auto-Close] Bybit error for ${symbol}: ${(data as any).retMsg}`);
      return dbCandles.map(c => ({
        timestamp: normalizeTimestamp(c.start_time) || 0,
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
      close: parseFloat(c[4]),
      volume: parseFloat(c[5] || '0'),
      turnover: parseFloat(c[6] || '0')
    })).reverse();

    console.log(`[Auto-Close] Bybit returned ${candles.length} candles for ${symbol} ${timeframe}`);

    // Store complete candles to database
    const candlesToStore = candles.filter(c => {
      const candleAge = now - c.timestamp;
      return candleAge >= tfMs;
    });

    if (candlesToStore.length < candles.length) {
      console.log(`[Auto-Close] Filtered out ${candles.length - candlesToStore.length} incomplete candle(s)`);
    }

    await storeCandles(symbol, timeframe, candlesToStore);
    console.log(`[Auto-Close] Stored ${candlesToStore.length} candles to database for ${symbol} ${timeframe}`);

    // CRITICAL FIX: Filter candles to only include those >= startTime
    // The Bybit API returns the latest N candles, not candles from a specific start time
    // So we must filter to ensure we only return candles after the trade was created
    const filteredCandles = candles.filter(c => c.timestamp >= startTime);
    const startTimeStr = (startTime > 0 && startTime < 8640000000000000) ? new Date(startTime).toISOString() : startTime.toString();
    console.log(`[Auto-Close] Filtered ${candles.length} candles to ${filteredCandles.length} candles >= ${startTimeStr}`);

    return filteredCandles;
  } catch (e) {
    if (e instanceof Error && e.name === 'AbortError') {
      console.error(`[Auto-Close] Bybit API timeout for ${symbol}`);
    } else {
      console.error(`[Auto-Close] Failed to fetch candles for ${symbol}:`, e);
    }
    return dbCandles.map(c => ({
      timestamp: normalizeTimestamp(c.start_time) || 0,
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
 * Find the first candle where spread-based trade entry is valid
 * For spread-based strategies, entry is signal-based, not price-based
 *
 * Entry is filled when:
 * 1. Both symbols' prices are touched (main and pair)
 * 2. The spread at that point is close to the entry spread (within tolerance)
 *
 * This prevents false fills where one symbol touches but the spread is invalid
 */
function findSpreadBasedFillCandle(
  mainCandles: Candle[],
  pairCandles: Candle[],
  entryPrice: number,
  pairEntryPrice: number,
  beta: number,
  entrySpread: number,
  spreadStd: number
): FillResult {
  // Tolerance: allow spread to be within 1.5 standard deviations of entry spread
  const spreadTolerance = 1.5 * spreadStd;

  // Both candle arrays must have same length and be aligned by timestamp
  const minLength = Math.min(mainCandles.length, pairCandles.length);

  for (let i = 0; i < minLength; i++) {
    const mainCandle = mainCandles[i];
    const pairCandle = pairCandles[i];

    // Check if both symbols' entry prices are touched in this candle
    const mainTouched = mainCandle.low <= entryPrice && entryPrice <= mainCandle.high;
    const pairTouched = pairCandle.low <= pairEntryPrice && pairEntryPrice <= pairCandle.high;

    if (mainTouched && pairTouched) {
      // Both symbols touched - verify spread is valid
      const currentSpread = pairCandle.close - beta * mainCandle.close;
      const spreadDiff = Math.abs(currentSpread - entrySpread);

      if (spreadDiff <= spreadTolerance) {
        // Spread is within tolerance - trade is filled
        return {
          filled: true,
          fillPrice: entryPrice,
          fillTimestamp: mainCandle.timestamp,
          fillCandleIndex: i,
          pair_fill_price: pairEntryPrice
        };
      }
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
 * Check strategy-specific exit conditions using Python strategy.should_exit()
 * Returns exit result if strategy says to exit, null otherwise
 * Falls back to price-level checks if strategy is not available
 */
async function checkStrategyExit(
  trade: TradeRow,
  candles: Candle[],
  startFromIndex: number = 0,
  strategyName?: string | null
): Promise<ExitResult | null> {
  // If no strategy name, cannot use strategy-specific logic
  if (!strategyName) {
    return null;
  }

  try {
    const { spawn } = await import('child_process');
    const path = await import('path');

    // Prepare data for Python script
    const candlesData = candles.slice(startFromIndex).map(c => ({
      timestamp: c.timestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close
    }));

    // Fetch strategy metadata from recommendation (single source of truth)
    let strategyMetadata: any = {};
    if (trade.recommendation_id) {
      try {
        const rec = await dbQuery<any>(`
          SELECT strategy_metadata FROM recommendations WHERE id = ?
        `, [trade.recommendation_id]);

        if (rec && rec.length > 0 && rec[0].strategy_metadata) {
          strategyMetadata = typeof rec[0].strategy_metadata === 'string'
            ? JSON.parse(rec[0].strategy_metadata)
            : rec[0].strategy_metadata;
        }
      } catch (error) {
        console.warn(`[Auto-Close] Failed to fetch strategy metadata from recommendation: ${error}`);
      }
    }

    const tradeData = {
      symbol: trade.symbol,
      side: trade.side,
      entry_price: trade.entry_price,
      stop_loss: trade.stop_loss,
      take_profit: trade.take_profit,
      strategy_metadata: strategyMetadata
    };

    // Fetch pair candles if this is a spread-based trade
    let pairCandlesData: any[] = [];
    const metadata = strategyMetadata;
    if (metadata && metadata.pair_symbol) {
      try {
        const pairSymbol = metadata.pair_symbol;
        // Get the timeframe from the first candle or default to '1h'
        const timeframe = candles.length > 0 ? '1h' : '1h';

        // Get the time range from the candles
        if (candles.length > 0) {
          const startTime = candles[0].timestamp;
          const endTime = candles[candles.length - 1].timestamp;

          // STEP 1: Query pair candles from klines table
          const pairCandles = await dbQuery<any>(`
            SELECT
              start_time as timestamp,
              open_price as open,
              high_price as high,
              low_price as low,
              close_price as close
            FROM klines
            WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
            ORDER BY start_time ASC
          `, [pairSymbol, timeframe, startTime, endTime]);

          pairCandlesData = pairCandles || [];
          if (pairCandlesData.length > 0) {
            console.log(`[Auto-Close] Fetched ${pairCandlesData.length} pair candles for ${pairSymbol} from database`);
          } else {
            // STEP 2: If not in database, fetch from Bybit API
            console.log(`[Auto-Close] No pair candles in database for ${pairSymbol}, fetching from Bybit API...`);
            try {
              await fetchAndStoreCandles(pairSymbol, timeframe);

              // Now try to fetch from database again
              const pairCandlesFromApi = await dbQuery<any>(`
                SELECT
                  start_time as timestamp,
                  open_price as open,
                  high_price as high,
                  low_price as low,
                  close_price as close
                FROM klines
                WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
              `, [pairSymbol, timeframe, startTime, endTime]);

              pairCandlesData = pairCandlesFromApi || [];
              if (pairCandlesData.length > 0) {
                console.log(`[Auto-Close] Fetched ${pairCandlesData.length} pair candles for ${pairSymbol} from Bybit API`);
              }
            } catch (apiError) {
              console.warn(`[Auto-Close] Failed to fetch pair candles from Bybit API for ${pairSymbol}: ${apiError}`);
              // Continue without pair candles - strategy will fetch from API if needed
            }
          }
        }
      } catch (error) {
        console.warn(`[Auto-Close] Failed to fetch pair candles: ${error}`);
        // Continue without pair candles - strategy will fetch from API if needed
      }
    }

    // Call Python script
    return new Promise((resolve) => {
      const pythonScript = path.join(process.cwd(), 'python', 'check_strategy_exit.py');

      let stdout = '';
      let stderr = '';

      const pythonProcess = spawn('python3', [
        pythonScript,
        trade.id,
        strategyName,
        JSON.stringify(candlesData),
        JSON.stringify(tradeData),
        JSON.stringify(pairCandlesData)
      ], {
        cwd: process.cwd(),
        env: { ...process.env }
      });

      pythonProcess.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      pythonProcess.on('close', (code) => {
        if (code !== 0) {
          console.warn(`[Auto-Close] Strategy exit check failed for ${trade.symbol}: ${stderr}`);
          resolve(null);
          return;
        }

        try {
          const result = JSON.parse(stdout);

          if (result.should_exit && result.exit_price && result.exit_reason) {
            const exitResult: ExitResult = {
              hit: true,
              reason: result.exit_reason,
              exitPrice: result.exit_price,
              exitTimestamp: result.exit_timestamp || candles[startFromIndex]?.timestamp || Date.now(),
              currentPrice: result.current_price || candles[candles.length - 1]?.close || 0
            };

            // Add pair_exit_price if available (for spread-based trades)
            if (result.pair_exit_price !== undefined) {
              exitResult.pair_exit_price = result.pair_exit_price;
            }

            resolve(exitResult);
          } else {
            resolve(null);
          }
        } catch (error) {
          console.warn(`[Auto-Close] Failed to parse strategy exit result: ${error}`);
          resolve(null);
        }
      });

      pythonProcess.on('error', (error) => {
        console.warn(`[Auto-Close] Error spawning strategy exit check: ${error}`);
        resolve(null);
      });
    });
  } catch (error) {
    console.warn(`[Auto-Close] Error calling strategy exit check: ${error}`);
    return null;
  }
}

/**
 * POST /api/bot/simulator/auto-close
 * Check all open paper trades using HISTORICAL candles from trade creation
 * Accurately detects if SL/TP was hit at any point since trade was created
 */
export async function POST() {
  const checkStartTime = Date.now();
  console.log(`[Auto-Close] POST handler called at ${new Date().toISOString()}`);

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Get all open paper trades with instance information
    const openTrades = await dbQuery<TradeRow & { instance_name: string; strategy_name?: string }>(`
      SELECT
        t.*,
        COALESCE(t.timeframe, rec.timeframe) as timeframe,
        COALESCE(t.entry_price, rec.entry_price) as entry_price,
        COALESCE(t.stop_loss, rec.stop_loss) as stop_loss,
        COALESCE(t.take_profit, rec.take_profit) as take_profit,
        i.name as instance_name,
        i.settings as instance_settings
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      LEFT JOIN runs r ON t.run_id = r.id
      LEFT JOIN instances i ON r.instance_id = i.id
      WHERE t.pnl IS NULL
        AND t.status IN ('paper_trade', 'pending_fill', 'filled')
      ORDER BY t.created_at DESC
    `);

    console.log(`[Auto-Close] Found ${openTrades.length} trades to check`);

    const results: Array<{
      trade_id: string;
      symbol: string;
      action: 'checked' | 'closed' | 'filled' | 'cancelled';
      current_price: number;
      instance_name?: string;
      strategy_name?: string;
      timeframe?: string;
      fill_timestamp?: string;
      exit_reason?: string;
      exit_timestamp?: string;
      pnl?: number;
      candles_checked?: number;
      bars_open?: number;
      checked_at?: string;
      position_size_usd?: number;
      risk_amount_usd?: number;
    }> = [];

    let closedCount = 0;
    let filledCount = 0;
    let cancelledCount = 0;

    for (const trade of openTrades) {
      const timeframe = trade.timeframe || '1h';
      const strategyName = getStrategyNameFromSettings((trade as any).instance_settings);
      try {
        const isLong = trade.side === 'Buy';
        const entryPrice = trade.entry_price || 0;
        const stopLoss = trade.stop_loss || 0;
        const takeProfit = trade.take_profit || 0;

        // Get max open bars for this trade's timeframe, status, and strategy type (0 = disabled)
        const maxOpenBars = await getMaxOpenBarsForTimeframe(
          timeframe,
          trade.status as 'pending_fill' | 'paper_trade' | 'filled',
          trade.strategy_type
        );

        // Parse trade creation time - validate it's a valid date
        const createdAt = normalizeTimestamp(trade.created_at);
        if (createdAt === null) {
          console.error(`[Auto-Close] Invalid created_at date for trade ${trade.id}: ${trade.created_at}`);
          continue; // Skip this trade
        }

        // CRITICAL: Use recommendation's analyzed_at (signal time) as the starting point
        // This ensures we check cand
        // les from when the signal was generated, not when trade was created
        // This is especially important for reset trades where created_at != signal time
        let signalTime = createdAt;

        if (trade.recommendation_id) {
          try {
            const rec = await dbQuery<any>(`
              SELECT analyzed_at FROM recommendations WHERE id = ?
            `, [trade.recommendation_id]);

            if (rec && rec.length > 0) {
              const recAnalyzedAt = normalizeTimestamp(rec[0].analyzed_at);
              if (recAnalyzedAt !== null) {
                signalTime = recAnalyzedAt;
                console.log(`[Auto-Close] Using recommendation signal time: ${new Date(signalTime).toISOString()}`);
              }
            }
          } catch (error) {
            console.warn(`[Auto-Close] Failed to fetch recommendation time for trade ${trade.id}: ${error}`);
            // Fall back to created_at
          }
        }

      // Fetch all candles from signal time (not creation time) to now
      const candles = await getHistoricalCandles(trade.symbol, timeframe, signalTime);

      console.log(`[Auto-Close] Trade ${trade.id} (${trade.symbol}): entry=${entryPrice}, SL=${stopLoss}, TP=${takeProfit}, timeframe=${timeframe}, created=${new Date(createdAt).toISOString()}, candles_fetched=${candles.length}`);

      if (candles.length === 0) {
        // Fallback: get current price from ticker API
        const currentPrice = await getCurrentPrice(trade.symbol);
        console.log(`[Auto-Close] No candles for ${trade.symbol}, using ticker price: ${currentPrice}`);

        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: currentPrice,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // CRITICAL FIX: Filter candles to only include those at or after signal time
      // A trade cannot be filled before the signal was generated!
      const candlesAfterCreation = candles.filter(c => {
        const candleTs = normalizeTimestamp(c.timestamp);
        return candleTs !== null && candleTs >= signalTime;
      });

      if (candlesAfterCreation.length === 0) {
        console.log(`[Auto-Close] No candles after signal time (${new Date(signalTime).toISOString()}), skipping`);
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: 0,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // Log candle time range for debugging
      let firstCandleTime = 'unknown';
      let lastCandleTime = 'unknown';
      try {
        const firstTs = normalizeTimestamp(candlesAfterCreation[0].timestamp);
        const lastTs = normalizeTimestamp(candlesAfterCreation[candlesAfterCreation.length - 1].timestamp);
        if (firstTs !== null) {
          firstCandleTime = new Date(firstTs).toISOString();
        }
        if (lastTs !== null) {
          lastCandleTime = new Date(lastTs).toISOString();
        }
      } catch (e) {
        console.error(`[Auto-Close] Error parsing candle timestamps: ${e}`);
      }
      const signalTime_str = new Date(signalTime).toISOString();
      console.log(`[Auto-Close] Candle range: ${firstCandleTime} to ${lastCandleTime} (signal time: ${signalTime_str})`);

      // STEP 1: Check if trade is already filled or find fill candle
      let fillCandleIndex = 0;
      let fillTime: string | null = null; // Track fill time for sanity checks
      const alreadyFilled = trade.status === 'filled' && trade.filled_at;

      // Fetch strategy metadata for spread-based fill detection
      let strategyMetadata: any = {};
      if (trade.recommendation_id) {
        try {
          const rec = await dbQuery<any>(`
            SELECT strategy_metadata FROM recommendations WHERE id = ?
          `, [trade.recommendation_id]);

          if (rec && rec.length > 0 && rec[0].strategy_metadata) {
            strategyMetadata = typeof rec[0].strategy_metadata === 'string'
              ? JSON.parse(rec[0].strategy_metadata)
              : rec[0].strategy_metadata;
          }
        } catch (error) {
          console.warn(`[Auto-Close] Failed to fetch strategy metadata for fill detection: ${error}`);
        }
      }

      if (alreadyFilled) {
        // Trade already filled - find the fill candle index to start SL/TP check from
        const filledAtMs = normalizeTimestamp(trade.filled_at);
        if (filledAtMs !== null) {
          fillCandleIndex = candlesAfterCreation.findIndex(c => {
            const candleTs = normalizeTimestamp(c.timestamp);
            return candleTs !== null && candleTs >= filledAtMs;
          });

          // CRITICAL: If no candles exist after fill time, we cannot check for exits
          // Skip this trade - it cannot have exited if there are no candles after it filled
          if (fillCandleIndex === -1) {
            console.log(`[Auto-Close] ${trade.symbol} SKIPPED - no candles after fill time (${new Date(filledAtMs).toISOString()})`);
            results.push({
              trade_id: trade.id,
              symbol: trade.symbol,
              action: 'checked',
              current_price: await getCurrentPrice(trade.symbol),
              instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
              timeframe: timeframe,
              candles_checked: candlesAfterCreation.length,
              bars_open: 0,
              checked_at: new Date().toISOString()
            });
            continue;
          }
        }
      } else {
        // Find fill candle - use spread-based logic if this is a spread-based strategy
        let fillResult: FillResult;

        if (strategyMetadata && strategyMetadata.pair_symbol) {
          // Spread-based strategy - need to check both symbols
          console.log(`[Auto-Close] ${trade.symbol} - Spread-based strategy detected, checking both symbols for fill`);

          // Fetch pair candles from database first, then API if missing
          let pairCandles: Candle[] = [];
          try {
            const pairSymbol = strategyMetadata.pair_symbol;
            if (candlesAfterCreation.length > 0) {
              const startTime = candlesAfterCreation[0].timestamp;
              const endTime = candlesAfterCreation[candlesAfterCreation.length - 1].timestamp;

              // STEP 1: Try to fetch from database
              const pairCandlesData = await dbQuery<any>(`
                SELECT
                  start_time as timestamp,
                  open_price as open,
                  high_price as high,
                  low_price as low,
                  close_price as close
                FROM klines
                WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
              `, [pairSymbol, timeframe, startTime, endTime]);

              pairCandles = (pairCandlesData || []).map(c => ({
                timestamp: c.timestamp,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
                volume: 0,
                turnover: 0
              }));

              if (pairCandles.length > 0) {
                console.log(`[Auto-Close] Fetched ${pairCandles.length} pair candles for ${pairSymbol} from database`);
              } else {
                // STEP 2: If not in database, fetch from Bybit API
                console.log(`[Auto-Close] No pair candles in database for ${pairSymbol}, fetching from Bybit API...`);
                try {
                  await fetchAndStoreCandles(pairSymbol, timeframe);

                  // Now try to fetch from database again
                  const pairCandlesDataFromApi = await dbQuery<any>(`
                    SELECT
                      start_time as timestamp,
                      open_price as open,
                      high_price as high,
                      low_price as low,
                      close_price as close
                    FROM klines
                    WHERE symbol = ? AND timeframe = ? AND start_time >= ? AND start_time <= ?
                    ORDER BY start_time ASC
                  `, [pairSymbol, timeframe, startTime, endTime]);

                  pairCandles = (pairCandlesDataFromApi || []).map(c => ({
                    timestamp: c.timestamp,
                    open: c.open,
                    high: c.high,
                    low: c.low,
                    close: c.close,
                    volume: 0,
                    turnover: 0
                  }));

                  if (pairCandles.length > 0) {
                    console.log(`[Auto-Close] Fetched ${pairCandles.length} pair candles for ${pairSymbol} from Bybit API`);
                  }
                } catch (apiError) {
                  console.warn(`[Auto-Close] Failed to fetch pair candles from Bybit API for ${pairSymbol}: ${apiError}`);
                }
              }
            }
          } catch (error) {
            console.warn(`[Auto-Close] Failed to fetch pair candles for spread-based fill detection: ${error}`);
          }

          if (pairCandles.length > 0) {
            // Use spread-based fill detection
            const pairEntryPrice = strategyMetadata.price_y_at_entry || 0;
            const beta = strategyMetadata.beta || 1.0;
            const spreadMean = strategyMetadata.spread_mean || 0;
            const spreadStd = strategyMetadata.spread_std || 1.0;

            fillResult = findSpreadBasedFillCandle(
              candlesAfterCreation,
              pairCandles,
              entryPrice,
              pairEntryPrice,
              beta,
              spreadMean,
              spreadStd
            );
          } else {
            // No pair candles available - trade cannot be filled yet
            // Will retry on next auto-closer run when pair candles may be available
            console.warn(`[Auto-Close] ${trade.symbol} - SPREAD-BASED STRATEGY: No pair candles available after API fetch, cannot validate fill. Trade remains unfilled and will retry.`);
            fillResult = { filled: false, fillPrice: null, fillTimestamp: null, fillCandleIndex: -1 };
          }
        } else {
          // Price-based strategy - use simple entry price check
          fillResult = findFillCandle(candlesAfterCreation, entryPrice);
        }

        if (!fillResult.filled) {
          // Trade not filled yet - check if it's pending_fill and been waiting too long
          // Use ticker price instead of last candle close for current price
          const currentPrice = await getCurrentPrice(trade.symbol);
          const barsPending = candles.length;  // Bars since trade creation

          console.log(`[Auto-Close] ${trade.symbol} NOT FILLED: entry=${entryPrice}, checked ${candles.length} candles, current_price=${currentPrice}`);
          // Log first and last candle for debugging
          if (candles.length > 0) {
            try {
              const firstTs = normalizeTimestamp(candles[0].timestamp);
              const lastTs = normalizeTimestamp(candles[candles.length - 1].timestamp);
              const firstTime = firstTs !== null ? new Date(firstTs).toISOString() : 'invalid';
              const lastTime = lastTs !== null ? new Date(lastTs).toISOString() : 'invalid';
              console.log(`  First candle: ${firstTime} [${candles[0].low}-${candles[0].high}]`);
              console.log(`  Last candle: ${lastTime} [${candles[candles.length - 1].low}-${candles[candles.length - 1].high}]`);
            } catch (e) {
              console.error(`[Auto-Close] Error logging candle times: ${e}`);
            }
          }

          // Apply max bars cancellation to pending_fill and paper_trade status
          if ((trade.status === 'pending_fill' || trade.status === 'paper_trade') && maxOpenBars > 0 && barsPending >= maxOpenBars) {
            // Cancel trade - been pending fill too long
            // NOTE: Never filled = never opened, so NO closed_at, exit_price, or PnL
            const cancelTime = new Date().toISOString();
            await dbExecute(`
              UPDATE trades SET
                exit_reason = 'max_bars_exceeded',
                status = 'cancelled',
                cancelled_at = ?
              WHERE id = ?
            `, [
              cancelTime,
              trade.id
            ]);

            cancelledCount++;
            console.log(`[Auto-Close] ${trade.symbol} CANCELLED (${trade.status}) after ${barsPending} bars (max: ${maxOpenBars}) - never filled`);

            results.push({
              trade_id: trade.id,
              symbol: trade.symbol,
              action: 'cancelled',
              current_price: currentPrice,
              instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
              timeframe: timeframe,
              exit_reason: 'max_bars_exceeded',
              candles_checked: candles.length,
              bars_open: barsPending,
              checked_at: new Date().toISOString()
            });
            continue;
          }

          // Still pending (paper_trade or pending_fill under limit)
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: currentPrice,
            instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
            timeframe: timeframe,
            candles_checked: candles.length,
            bars_open: barsPending,
            checked_at: new Date().toISOString()
          });
          continue;
        }

        // Trade is now filled - update database with fill info
        // Normalize fillTimestamp to milliseconds
        const fillTimeMs = normalizeTimestamp(fillResult.fillTimestamp);

        if (fillTimeMs === null) {
          console.error(`[Auto-Close] Invalid fillTimestamp for trade ${trade.id}: ${fillResult.fillTimestamp}`);
          continue; // Skip this trade
        }

        fillTime = new Date(fillTimeMs).toISOString();

        // SANITY CHECK: Validate filled_at >= created_at
        const fillValidationError = validateTradeTimestamps(
          trade.created_at,
          fillTime,
          null
        );

        if (fillValidationError) {
          await logSimulatorError(
            trade.id,
            'TIMESTAMP_VIOLATION_ON_FILL',
            fillValidationError,
            {
              symbol: trade.symbol,
              created_at: trade.created_at,
              filled_at: fillTime,
              fill_price: fillResult.fillPrice
            }
          );
          console.error(`[Auto-Close] SANITY CHECK FAILED for trade ${trade.id}: ${fillValidationError}`);
          continue; // Skip this trade - do not update database with invalid data
        }

        // For spread-based trades, also update pair_fill_price and order_id_pair
        let updateQuery = `
          UPDATE trades SET
            fill_price = ?,
            fill_time = ?,
            filled_at = ?,
            status = 'filled'`;

        const updateParams: any[] = [
          fillResult.fillPrice,
          fillTime,
          fillTime
        ];

        // Add spread-based columns if this is a spread-based trade
        if (trade.strategy_type === 'spread_based' && fillResult.pair_fill_price !== undefined) {
          updateQuery += `, pair_fill_price = ?`;
          updateParams.push(fillResult.pair_fill_price);
        }

        if (trade.strategy_type === 'spread_based' && trade.order_id_pair) {
          updateQuery += `, order_id_pair = ?`;
          updateParams.push(trade.order_id_pair);
        }

        updateQuery += ` WHERE id = ?`;
        updateParams.push(trade.id);

        await dbExecute(updateQuery, updateParams);

        filledCount++;
        fillCandleIndex = fillResult.fillCandleIndex + 1; // Start SL/TP check from NEXT candle
        console.log(`[Auto-Close] ${trade.symbol} FILLED at ${fillResult.fillPrice} on ${fillTime}`);
      }

      // STEP 2: Check for SL/TP hit starting from candle AFTER fill
      // IMPORTANT: Only proceed if trade is actually filled
      // A trade can only be closed if it was filled first
      const isFilled = alreadyFilled || (trade.status === 'filled' && trade.filled_at);

      if (!isFilled) {
        // Trade was never filled - cannot close it
        // This should not happen as unfilled trades are handled above, but safety check
        console.log(`[Auto-Close] ${trade.symbol} SKIPPED - trade not filled, cannot close`);
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: await getCurrentPrice(trade.symbol),
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: candles.length,
          bars_open: 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // STEP 2A: Validate that trade has associated strategy
      if (!trade.strategy_name) {
        console.error(`[Auto-Close] ${trade.symbol} ERROR - Trade has no associated strategy_name. Cannot determine exit logic.`);
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: await getCurrentPrice(trade.symbol),
          instance_name: trade.instance_name,
          strategy_name: undefined,
          timeframe: timeframe,
          candles_checked: candles.length,
          bars_open: fillCandleIndex >= 0 ? candles.length - fillCandleIndex : 0,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      // STEP 2B: Determine exit logic based on strategy type
      let exitResult: ExitResult | null = null;
      const strategyType = trade.strategy_type || 'unknown';

      if (strategyType === 'price_based') {
        // Price-based strategies use TP/SL logic
        console.log(`[Auto-Close] ${trade.symbol} - Price-based strategy (${strategyName}), checking SL/TP`);
        exitResult = checkHistoricalSLTP(candlesAfterCreation, isLong, stopLoss, takeProfit, fillCandleIndex);
      } else {
        // Non-price-based strategies (spread-based, etc.) use strategy.should_exit()
        console.log(`[Auto-Close] ${trade.symbol} - ${strategyType} strategy (${strategyName}), checking strategy exit`);
        exitResult = await checkStrategyExit(trade, candlesAfterCreation, fillCandleIndex, strategyName);

        if (!exitResult || !exitResult.hit) {
          // Fallback to price-level checks if strategy exit returns nothing
          console.log(`[Auto-Close] ${trade.symbol} - No strategy exit, falling back to SL/TP`);
          exitResult = checkHistoricalSLTP(candlesAfterCreation, isLong, stopLoss, takeProfit, fillCandleIndex);
        }
      }

      if (exitResult && exitResult.hit) {
        console.log(`[Auto-Close] ${trade.symbol} - Exit triggered: ${exitResult.reason}`);
      }

      // Calculate bars since fill (for max_open_bars check)
      const barsOpen = candlesAfterCreation.length - fillCandleIndex;

      if (exitResult.hit && exitResult.exitPrice && exitResult.reason) {
        // Calculate P&L - handle both price-based and spread-based trades
        let pnl: number;
        let pnlPercent: number;

        if (trade.strategy_type === 'spread_based' && trade.pair_quantity && trade.pair_fill_price && exitResult.pair_exit_price) {
          // Spread-based trade: calculate P&L for both symbols
          const mainFillPrice = trade.fill_price || entryPrice;
          const mainQty = trade.quantity || 1;
          const pairFillPrice = trade.pair_fill_price;
          const pairQty = trade.pair_quantity;

          // Main symbol P&L
          const mainPnl = isLong
            ? (exitResult.exitPrice - mainFillPrice) * mainQty
            : (mainFillPrice - exitResult.exitPrice) * mainQty;

          // Pair symbol P&L (opposite direction)
          const pairPnl = isLong
            ? (pairFillPrice - exitResult.pair_exit_price) * pairQty
            : (exitResult.pair_exit_price - pairFillPrice) * pairQty;

          pnl = mainPnl + pairPnl;

          // P&L percent based on total notional value
          const totalNotional = (mainFillPrice * mainQty) + (pairFillPrice * pairQty);
          pnlPercent = totalNotional > 0 ? (pnl / totalNotional) * 100 : 0;
        } else {
          // Price-based trade: calculate P&L for main symbol only
          const fillPrice = trade.fill_price || entryPrice;
          const qty = trade.quantity || 1;
          pnl = isLong
            ? (exitResult.exitPrice - fillPrice) * qty
            : (fillPrice - exitResult.exitPrice) * qty;
          pnlPercent = fillPrice > 0 ? (pnl / (fillPrice * qty)) * 100 : 0;
        }

        // Get exit timestamp as ISO string
        // exitTimestamp is a number (Unix ms), convert to Date
        let exitTime: string;
        if (exitResult.exitTimestamp) {
          const exitTimeMs = typeof exitResult.exitTimestamp === 'string'
            ? parseInt(exitResult.exitTimestamp, 10)
            : exitResult.exitTimestamp;

          if (!exitTimeMs || isNaN(exitTimeMs)) {
            console.error(`[Auto-Close] Invalid exitTimestamp for trade ${trade.id}: ${exitResult.exitTimestamp}`);
            continue; // Skip this trade
          }
          exitTime = new Date(exitTimeMs).toISOString();
        } else {
          exitTime = new Date().toISOString();
        }

        // SANITY CHECK: Validate complete timestamp chain (created_at <= filled_at <= closed_at)
        // Use fillTime if we just filled in this iteration, otherwise use trade.filled_at
        const actualFilledAt = fillTime || (trade.filled_at as string);

        if (!actualFilledAt) {
          const errorMsg = 'No filled_at timestamp available - cannot close unfilled trade';
          await logSimulatorError(
            trade.id,
            'MISSING_FILLED_AT_ON_CLOSE',
            errorMsg,
            {
              symbol: trade.symbol,
              created_at: trade.created_at,
              exit_time: exitTime,
              exit_reason: exitResult.reason
            }
          );
          console.error(`[Auto-Close] SANITY CHECK FAILED for trade ${trade.id}: ${errorMsg}`);
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: await getCurrentPrice(trade.symbol),
            instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
            timeframe: timeframe,
            candles_checked: candles.length,
            bars_open: barsOpen,
            checked_at: new Date().toISOString(),
            position_size_usd: trade.position_size_usd || undefined,
            risk_amount_usd: trade.risk_amount_usd || undefined
          });
          continue;
        }

        // Comprehensive timestamp validation
        const closeValidationError = validateTradeTimestamps(
          trade.created_at,
          actualFilledAt,
          exitTime
        );

        if (closeValidationError) {
          await logSimulatorError(
            trade.id,
            'TIMESTAMP_VIOLATION_ON_CLOSE',
            closeValidationError,
            {
              symbol: trade.symbol,
              created_at: trade.created_at,
              filled_at: actualFilledAt,
              closed_at: exitTime,
              exit_reason: exitResult.reason,
              exit_price: exitResult.exitPrice,
              pnl: pnl
            }
          );
          console.error(`[Auto-Close] SANITY CHECK FAILED for trade ${trade.id}: ${closeValidationError}`);
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: await getCurrentPrice(trade.symbol),
            instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
            timeframe: timeframe,
            candles_checked: candles.length,
            bars_open: barsOpen,
            checked_at: new Date().toISOString(),
            position_size_usd: trade.position_size_usd || undefined,
            risk_amount_usd: trade.risk_amount_usd || undefined
          });
          continue;
        }

        // Update trade in database with actual exit time
        let exitUpdateQuery = `
          UPDATE trades SET
            exit_price = ?,
            exit_reason = ?,
            closed_at = ?,
            pnl = ?,
            pnl_percent = ?,
            status = 'closed'`;

        const exitUpdateParams: any[] = [
          exitResult.exitPrice,
          exitResult.reason,
          exitTime,
          Math.round(pnl * 100) / 100,
          Math.round(pnlPercent * 100) / 100
        ];

        // Add pair_exit_price for spread-based trades
        if (trade.strategy_type === 'spread_based' && exitResult.pair_exit_price !== undefined) {
          exitUpdateQuery += `, pair_exit_price = ?`;
          exitUpdateParams.push(exitResult.pair_exit_price);
        }

        exitUpdateQuery += ` WHERE id = ?`;
        exitUpdateParams.push(trade.id);

        await dbExecute(exitUpdateQuery, exitUpdateParams);

        // CRITICAL: Update run aggregates when trade closes
        const isWin = pnl > 0;
        const isLoss = pnl < 0;
        await dbExecute(`
          UPDATE runs SET
            total_pnl = total_pnl + ?,
            win_count = win_count + ?,
            loss_count = loss_count + ?
          WHERE id = (
            SELECT run_id FROM trades WHERE id = ?
          )
        `, [
          Math.round(pnl * 100) / 100,
          isWin ? 1 : 0,
          isLoss ? 1 : 0,
          trade.id
        ]);

        closedCount++;
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'closed',
          current_price: exitResult.currentPrice,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          exit_reason: exitResult.reason,
          exit_timestamp: exitTime,
          pnl: Math.round(pnl * 100) / 100,
          candles_checked: candles.length,
          bars_open: barsOpen,
          checked_at: new Date().toISOString(),
          position_size_usd: trade.position_size_usd || undefined,
          risk_amount_usd: trade.risk_amount_usd || undefined
        });
      } else if (maxOpenBars > 0 && barsOpen >= maxOpenBars) {
        // STEP 3: Check for max bars exceeded - cancel the trade
        // Trade has been open too long without hitting TP/SL
        const currentPrice = exitResult.currentPrice;
        const fillPrice = trade.fill_price || entryPrice;
        const qty = trade.quantity || 1;

        // Calculate unrealized P&L at cancellation
        const pnl = isLong
          ? (currentPrice - fillPrice) * qty
          : (fillPrice - currentPrice) * qty;
        const pnlPercent = fillPrice > 0 ? (pnl / (fillPrice * qty)) * 100 : 0;

        const cancelTime = new Date().toISOString();

        // SANITY CHECK: Validate timestamp chain before cancellation
        const actualFilledAt = fillTime || (trade.filled_at as string);
        const cancelValidationError = validateTradeTimestamps(
          trade.created_at,
          actualFilledAt,
          cancelTime
        );

        if (cancelValidationError) {
          await logSimulatorError(
            trade.id,
            'TIMESTAMP_VIOLATION_ON_CANCEL',
            cancelValidationError,
            {
              symbol: trade.symbol,
              created_at: trade.created_at,
              filled_at: actualFilledAt,
              cancel_time: cancelTime,
              bars_open: barsOpen,
              max_bars: maxOpenBars
            }
          );
          console.error(`[Auto-Close] SANITY CHECK FAILED for trade ${trade.id}: ${cancelValidationError}`);
          continue; // Skip this trade - do not update database with invalid data
        }

        // Update trade as cancelled with exit at current price
        await dbExecute(`
          UPDATE trades SET
            exit_price = ?,
            exit_reason = 'max_bars_exceeded',
            closed_at = ?,
            cancelled_at = ?,
            pnl = ?,
            pnl_percent = ?,
            status = 'cancelled'
          WHERE id = ?
        `, [
          currentPrice,
          cancelTime,
          cancelTime,
          Math.round(pnl * 100) / 100,
          Math.round(pnlPercent * 100) / 100,
          trade.id
        ]);

        // CRITICAL: Update run aggregates when trade is cancelled
        const isWin = pnl > 0;
        const isLoss = pnl < 0;
        await dbExecute(`
          UPDATE runs SET
            total_pnl = total_pnl + ?,
            win_count = win_count + ?,
            loss_count = loss_count + ?
          WHERE id = (
            SELECT run_id FROM trades WHERE id = ?
          )
        `, [
          Math.round(pnl * 100) / 100,
          isWin ? 1 : 0,
          isLoss ? 1 : 0,
          trade.id
        ]);

        cancelledCount++;
        console.log(`[Auto-Close] ${trade.symbol} CANCELLED after ${barsOpen} bars (max: ${maxOpenBars})`);

        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'cancelled',
          current_price: currentPrice,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          exit_reason: 'max_bars_exceeded',
          exit_timestamp: cancelTime,
          pnl: Math.round(pnl * 100) / 100,
          candles_checked: candles.length,
          bars_open: barsOpen,
          checked_at: new Date().toISOString(),
          position_size_usd: trade.position_size_usd || undefined,
          risk_amount_usd: trade.risk_amount_usd || undefined
        });
      } else {
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: alreadyFilled ? 'checked' : 'filled',
          current_price: exitResult.currentPrice,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: candles.length,
          bars_open: barsOpen,
          checked_at: new Date().toISOString(),
          position_size_usd: trade.position_size_usd || undefined,
          risk_amount_usd: trade.risk_amount_usd || undefined
        });
      }
      } catch (tradeError) {
        console.error(`[Auto-Close] Error processing trade ${trade.id}:`, tradeError);
        if (tradeError instanceof Error) {
          console.error('Trade error stack:', tradeError.stack);
        }
        // Continue to next trade instead of crashing
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: 0,
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: 0,
          checked_at: new Date().toISOString(),
          position_size_usd: trade.position_size_usd || undefined,
          risk_amount_usd: trade.risk_amount_usd || undefined
        });
      }
    }

    const checkDuration = Date.now() - checkStartTime;
    console.log(`[Auto-Close] Check complete: ${filledCount} filled, ${closedCount} closed, ${cancelledCount} cancelled (took ${checkDuration}ms)`);

    return NextResponse.json({
      success: true,
      checked: openTrades.length,
      filled: filledCount,
      closed: closedCount,
      cancelled: cancelledCount,
      method: 'historical_candles_with_fill',
      results
    });
  } catch (error) {
    console.error('Auto-close error:', error);
    if (error instanceof Error) {
      console.error('Error stack:', error.stack);
    }
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}


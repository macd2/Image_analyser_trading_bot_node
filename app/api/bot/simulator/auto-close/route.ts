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
  const value = config[timeframe] ?? config[timeframe.toLowerCase()];

  // CRITICAL: max_open_bars is strategy-aware config - must be explicitly set, no fallback to 0
  if (value === undefined) {
    // If not configured, return 0 (disabled) - but log warning
    console.warn(`[Auto-Close] WARNING: max_open_bars not configured for ${timeframe}/${tradeStatus}/${strategyType || 'unknown'} - disabling max_bars check`);
    return 0;
  }

  return value;
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

/**
 * Result from strategy exit check
 * Distinguishes between:
 * - { success: true, exit: ExitResult } = strategy check succeeded, trade should exit
 * - { success: true, exit: null } = strategy check succeeded, trade should NOT exit (normal)
 * - { success: false, error: string } = strategy check failed (actual error)
 */
interface StrategyExitCheckResult {
  success: boolean;
  exit?: ExitResult | null;  // Only present if success=true
  error?: string;  // Only present if success=false
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
 * Store candles to klines table (batch insert - ON CONFLICT DO NOTHING)
 */
async function storeCandles(
  symbol: string,
  timeframe: string,
  candles: Candle[]
): Promise<void> {
  if (candles.length === 0) return;

  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;

  // Batch insert all candles at once (much faster than individual inserts)
  try {
    const placeholders = candles.map(() => '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').join(',');
    const values: any[] = [];

    for (const c of candles) {
      values.push(normSymbol, timeframe, 'linear', c.timestamp, c.open, c.high, c.low, c.close, c.volume || 0, c.turnover || 0);
    }

    const result = await dbExecute(
      `INSERT INTO klines (symbol, timeframe, category, start_time, open_price, high_price, low_price, close_price, volume, turnover)
       VALUES ${placeholders}
       ON CONFLICT (symbol, timeframe, start_time) DO NOTHING`,
      values
    );

    // CRITICAL: Log actual result to verify insert happened
    console.log(`[Auto-Close] Batch insert result: ${result.changes} rows affected (attempted ${candles.length} candles)`);

    if (result.changes === 0 && candles.length > 0) {
      console.warn(`[Auto-Close] WARNING: Batch insert returned 0 rows affected for ${candles.length} candles - all may be duplicates`);
    }
  } catch (e) {
    // Log error but don't fail - duplicate candles are expected
    console.error(`[Auto-Close] ERROR storing candles for ${symbol}: ${e}`);
  }
}

/**
 * Determine minimum candles required based on strategy type
 * Different strategies need different amounts of historical data
 */
function getMinimumCandlesRequired(strategyType?: string): number {
  // Spread-based strategies (cointegration) need lookback period (typically 120 candles)
  if (strategyType === 'spread_based') {
    return 120; // Cointegration lookback period
  }

  // Price-based strategies only need current price
  if (strategyType === 'price_based') {
    return 1;
  }

  // Default: assume spread-based (safer to fetch more)
  return 120;
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
    const endTime = now; // Bybit expects milliseconds

    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&limit=${limit}&end=${endTime}`;

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
 *
 * @param symbol - Trading symbol (e.g., 'BTCUSDT')
 * @param timeframe - Candle timeframe (e.g., '1h')
 * @param signalTime - Signal/entry time in milliseconds (Unix timestamp)
 * @param strategyType - Optional strategy type to determine minimum candles needed
 *
 * IMPORTANT: This function automatically extends the start time backwards to include
 * the lookback period needed by the strategy. For example, if strategy needs 120 candles
 * of lookback and signal is at time T, we fetch from (T - 120*timeframe) to now.
 */
async function getHistoricalCandles(
  symbol: string,
  timeframe: string,
  signalTime: number, // Unix timestamp in ms (when signal was generated)
  strategyType?: string
): Promise<Candle[]> {
  const normSymbol = symbol.endsWith('.P') ? symbol.slice(0, -2) : symbol;
  const now = Date.now();

  // Calculate the lookback period needed by the strategy
  const lookbackCandles = getMinimumCandlesRequired(strategyType);
  const tfMs = TIMEFRAME_MS[timeframe] || 3600000;

  // CRITICAL: Extend start time backwards to include lookback period
  // Example: if signal at T and need 120 candles lookback, fetch from (T - 120*tfMs) to now
  const startTime = signalTime - (lookbackCandles * tfMs);

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

  // Calculate how many candles we need
  // CRITICAL: Need lookback period BEFORE entry + all candles from entry to now
  // Example for spread-based (lookback=120):
  //   - If trade is 10 candles old: need 120 (lookback) + 10 (since entry) = 130 total
  //   - If trade is 200 candles old: need 120 (lookback) + 200 (since entry) = 320 total
  const candlesSinceEntry = Math.ceil((now - startTime) / tfMs);
  const totalNeeded = lookbackCandles + candlesSinceEntry;

  console.log(`[Auto-Close] ${symbol} ${timeframe}: lookback=${lookbackCandles}, since_entry=${candlesSinceEntry}, total_needed=${totalNeeded}`);

  // CRITICAL: Check if we have candles covering the REQUIRED TIME RANGE with NO GAPS
  // We need: [startTime (now - lookback - since_entry)] to [now]
  let hasGaps = false;
  if (dbCandles.length > 0) {
    const oldestDbCandle = Math.min(...dbCandles.map(c => normalizeTimestamp(c.start_time) || Infinity));
    const newestDbCandle = Math.max(...dbCandles.map(c => normalizeTimestamp(c.start_time) || 0));

    // Check if DB covers the required range: startTime (lookback before signal) to now
    if (oldestDbCandle <= startTime && newestDbCandle >= now - tfMs) {
      // Check for gaps in the candle sequence
      const sortedCandles = dbCandles
        .map(c => normalizeTimestamp(c.start_time) || 0)
        .sort((a, b) => a - b);

      for (let i = 1; i < sortedCandles.length; i++) {
        const gap = sortedCandles[i] - sortedCandles[i - 1];
        if (gap > tfMs * 1.5) { // Allow 50% tolerance for market hours gaps
          console.log(`[Auto-Close] Gap detected in ${symbol} ${timeframe}: ${gap / tfMs} candles missing`);
          hasGaps = true;
          break;
        }
      }

      if (!hasGaps) {
        console.log(`[Auto-Close] ✅ Using ${dbCandles.length} cached candles for ${symbol} ${timeframe} (covers ${new Date(oldestDbCandle).toISOString()} to ${new Date(newestDbCandle).toISOString()}, no gaps)`);
        return dbCandles.map(c => ({
          timestamp: normalizeTimestamp(c.start_time) || 0,
          open: c.open_price,
          high: c.high_price,
          low: c.low_price,
          close: c.close_price
        }));
      }
    }
  }

  // If we don't have candles covering the required time range or have gaps, fetch from Bybit
  console.log(`[Auto-Close] ${hasGaps ? 'Gaps detected' : 'Missing candles for required time range'} for ${symbol} ${timeframe}, fetching from Bybit...`);

  try {
    const apiSymbol = normSymbol;
    const interval = TIMEFRAME_MAP[timeframe] || '60';

    // CRITICAL: Fetch candles ENDING at 'now' to get the most recent data
    // Use 'end' parameter to fetch candles up to current time
    // Bybit returns newest candles first, so we get the latest 1000 candles
    const limit = 1000;
    const endTime = now; // Bybit expects milliseconds

    const url = `https://api.bybit.com/v5/market/kline?category=linear&symbol=${apiSymbol}&interval=${interval}&limit=${limit}&end=${endTime}`;

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

    // CRITICAL: Check if we have enough candles
    // We need: lookback period + all candles since entry
    if (candles.length < totalNeeded) {
      const errorMsg = `Insufficient candles from Bybit: got ${candles.length}, need ${totalNeeded} (${lookbackCandles} lookback + ${candlesSinceEntry} since entry)`;
      console.error(`[Auto-Close] TRADE SKIPPED: ${errorMsg}`);
      // Return empty array to signal error - trade will be skipped in main loop
      return [];
    }

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

    // CRITICAL: Return ALL candles including lookback period
    // startTime was already extended backwards to include lookback, so all returned candles are needed
    // The Bybit API returns the latest N candles, so we return them as-is
    const startTimeStr = (startTime > 0 && startTime < 8640000000000000) ? new Date(startTime).toISOString() : startTime.toString();
    console.log(`[Auto-Close] Returning ${candles.length} candles (from ${startTimeStr} to now)`);

    return candles;
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
 * Find fill candle for spread-based trades (SIGNAL-BASED APPROACH)
 *
 * For spread-based cointegration strategies, trades are SIGNAL-BASED, not PRICE-LEVEL-BASED.
 * This means:
 * - Trade fills immediately at signal time (or next candle after signal)
 * - Entry price = current price at signal time
 * - No need to wait for specific price levels to be touched
 *
 * The signal is generated when z-score crosses the entry threshold (e.g., z >= 2.0 or z <= -2.0).
 * The trade should fill at the FIRST CANDLE after signal generation.
 */
function findSpreadBasedFillCandle(
  mainCandles: Candle[],
  pairCandles: Candle[],
  entryPrice: number,
  pairEntryPrice: number
): FillResult {
  // Signal-based fill: Trade fills at the FIRST CANDLE after signal generation
  // This is because the signal was already generated when the trade was created
  // The trade should fill immediately at the next available candle

  if (mainCandles.length === 0 || pairCandles.length === 0) {
    return { filled: false, fillPrice: null, fillTimestamp: null, fillCandleIndex: -1 };
  }

  // For signal-based trades, fill at the first candle
  // This represents the trade filling at the signal time (or next candle)
  const mainCandle = mainCandles[0];
  const pairCandle = pairCandles[0];

  // Verify we have valid candles with prices
  if (!mainCandle || !pairCandle || mainCandle.close <= 0 || pairCandle.close <= 0) {
    return { filled: false, fillPrice: null, fillTimestamp: null, fillCandleIndex: -1 };
  }

  // Signal-based fill: Use current prices at signal time as fill prices
  // The entry_price and pair_entry_price stored in the trade are the prices at signal time
  return {
    filled: true,
    fillPrice: entryPrice,
    fillTimestamp: mainCandle.timestamp,
    fillCandleIndex: 0,
    pair_fill_price: pairEntryPrice
  };
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
  const direction = isLong ? 'LONG' : 'SHORT';

  console.log(`[Exit-Check] SL/TP: Starting check from candle ${startFromIndex}/${candles.length}, ${direction} SL=${stopLoss.toFixed(2)} TP=${takeProfit.toFixed(2)}`);

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
          console.log(`[Exit-Check] SL/TP: LONG SL HIT at candle ${i}, low=${candle.low.toFixed(2)} <= SL=${stopLoss.toFixed(2)}`);
          return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
        } else {
          console.log(`[Exit-Check] SL/TP: LONG TP HIT at candle ${i}, high=${candle.high.toFixed(2)} >= TP=${takeProfit.toFixed(2)}`);
          return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
        }
      } else if (slHit) {
        console.log(`[Exit-Check] SL/TP: LONG SL HIT at candle ${i}, low=${candle.low.toFixed(2)} <= SL=${stopLoss.toFixed(2)}`);
        return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
      } else if (tpHit) {
        console.log(`[Exit-Check] SL/TP: LONG TP HIT at candle ${i}, high=${candle.high.toFixed(2)} >= TP=${takeProfit.toFixed(2)}`);
        return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
      }
    } else {
      // Short position: SL hit if high >= stopLoss, TP hit if low <= takeProfit
      const slHit = candle.high >= stopLoss;
      const tpHit = candle.low <= takeProfit;

      if (slHit && tpHit) {
        // Both hit in same candle - determine which first
        if (Math.abs(candle.open - stopLoss) < Math.abs(candle.open - takeProfit)) {
          console.log(`[Exit-Check] SL/TP: SHORT SL HIT at candle ${i}, high=${candle.high.toFixed(2)} >= SL=${stopLoss.toFixed(2)}`);
          return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
        } else {
          console.log(`[Exit-Check] SL/TP: SHORT TP HIT at candle ${i}, low=${candle.low.toFixed(2)} <= TP=${takeProfit.toFixed(2)}`);
          return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
        }
      } else if (slHit) {
        console.log(`[Exit-Check] SL/TP: SHORT SL HIT at candle ${i}, high=${candle.high.toFixed(2)} >= SL=${stopLoss.toFixed(2)}`);
        return { hit: true, reason: 'sl_hit', exitPrice: stopLoss, exitTimestamp: candle.timestamp, currentPrice };
      } else if (tpHit) {
        console.log(`[Exit-Check] SL/TP: SHORT TP HIT at candle ${i}, low=${candle.low.toFixed(2)} <= TP=${takeProfit.toFixed(2)}`);
        return { hit: true, reason: 'tp_hit', exitPrice: takeProfit, exitTimestamp: candle.timestamp, currentPrice };
      }
    }
  }

  console.log(`[Exit-Check] SL/TP: No exit signal found in ${candles.length - startFromIndex} candles`);
  return { hit: false, reason: null, exitPrice: null, exitTimestamp: null, currentPrice };
}

/**
 * Check strategy-specific exit conditions using Python strategy.should_exit()
 * Returns:
 * - { success: true, exit: ExitResult } if strategy says to exit
 * - { success: true, exit: null } if strategy says don't exit (normal case)
 * - { success: false, error: string } if strategy check failed (actual error)
 */
async function checkStrategyExit(
  trade: TradeRow,
  candles: Candle[],
  startFromIndex: number = 0,
  strategyName?: string | null,
  pairCandles: Candle[] = [],
  pairSymbol?: string | null
): Promise<StrategyExitCheckResult> {
  // If no strategy name, cannot use strategy-specific logic
  if (!strategyName) {
    return { success: false, error: 'No strategy name provided' };
  }

  try {
    const { spawn } = await import('child_process');
    const path = await import('path');

    // Determine if spread-based strategy early
    const isSpreadBased = trade.strategy_type === 'spread_based';

    // Prepare data for Python script
    // CRITICAL: For spread-based strategies, pass ALL candles (lookback + walk-forward)
    // For price-based strategies, can slice from startFromIndex
    const candlesData = (isSpreadBased ? candles : candles.slice(startFromIndex)).map(c => ({
      timestamp: c.timestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close
    }));

    // Fetch strategy metadata (single source of truth)
    // CRITICAL: Use trade's own strategy_metadata (stored during trade creation)
    // Fallback to recommendation only if trade doesn't have it
    let strategyMetadata: any = {};

    // PRIORITY 1: Use strategy_metadata from trade (stored during trade creation)
    if (trade.strategy_metadata) {
      strategyMetadata = typeof trade.strategy_metadata === 'string'
        ? JSON.parse(trade.strategy_metadata)
        : trade.strategy_metadata;
    }
    // PRIORITY 2: Fallback to recommendation if trade doesn't have metadata
    else if (trade.recommendation_id) {
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
      strategy_metadata: strategyMetadata,
      strategy_type: trade.strategy_type,  // CRITICAL: Pass strategy_type to Python script for exit logic
      pair_symbol: strategyMetadata?.pair_symbol,  // CRITICAL: Pass pair_symbol for spread-based trades to avoid API calls
      fill_candle_index: startFromIndex  // CRITICAL: Pass fill candle index to Python script to skip lookback candles
    };

    // Use pair candles passed from Step 7, or fetch if not provided
    let pairCandlesData: any[] = [];
    const metadata = strategyMetadata;

    if (isSpreadBased) {
      console.log(`[Exit-Check] Spread-based trade detected: ${trade.symbol}`);
    }

    // If pair candles were already fetched in Step 7, use them
    if (pairCandles && pairCandles.length > 0) {
      console.log(`[Exit-Check] ✅ Using pair candles from Step 7: ${pairCandles.length} candles for ${pairSymbol}`);
      pairCandlesData = pairCandles.map(c => ({
        timestamp: c.timestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close
      }));
      console.log(`[Exit-Check] Converted to pairCandlesData: ${pairCandlesData.length} candles`);
    } else if (metadata && metadata.pair_symbol) {
      console.log(`[Exit-Check] ⚠️ No pair candles from Step 7, will fetch from DB/API for ${metadata.pair_symbol}`);
      const pairSymbol = metadata.pair_symbol;
      if (isSpreadBased) {
        console.log(`[Exit-Check] Pair symbol: ${pairSymbol}`);
      }

      try {
        // Get the timeframe from the first candle or default to '1h'
        const timeframe = candles.length > 0 ? '1h' : '1h';

        // Get the time range from the candles
        if (candles.length > 0) {
          const startTime = candles[0].timestamp;
          const endTime = candles[candles.length - 1].timestamp;
          const now = Date.now();
          const tfMs = TIMEFRAME_MS[timeframe] || 3600000;

          // STEP 1: Check if pair candles in database are stale
          // Get the latest pair candle timestamp in the database
          const latestPairCandleResult = await dbQuery<{ max_ts: number | null }>(
            `SELECT MAX(start_time) as max_ts FROM klines WHERE symbol = ? AND timeframe = ?`,
            [pairSymbol, timeframe]
          );

          const rawLatestPairCandleTs = latestPairCandleResult[0]?.max_ts;
          const latestPairCandleTs = normalizeTimestamp(rawLatestPairCandleTs) || 0;
          const latestCompleteCandle = Math.max(0, now - (now % tfMs) - tfMs); // Timestamp of the latest COMPLETE candle

          // Validate timestamps before converting to Date
          const isValidTimestamp = (ts: number) => ts > 0 && ts < 8640000000000000;
          const latestPairCandleStr = isValidTimestamp(latestPairCandleTs) ? new Date(latestPairCandleTs).toISOString() : 'no candles';
          const latestCompleteStr = isValidTimestamp(latestCompleteCandle) ? new Date(latestCompleteCandle).toISOString() : 'no complete candles yet';

          if (isSpreadBased) {
            console.log(`[Exit-Check] Pair DB status: latest=${latestPairCandleStr}, complete=${latestCompleteStr}`);
          }

          // STEP 2: Query pair candles from klines table
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

          // STEP 3: For simulator, use whatever candles we have (don't fetch from API)
          // The simulator works with historical data, not real-time
          if (pairCandlesData.length === 0) {
            if (isSpreadBased) console.log(`[Exit-Check] No pair candles in DB for ${pairSymbol}`);
          } else {
            if (isSpreadBased) console.log(`[Exit-Check] Using ${pairCandlesData.length} pair candles from DB`);
          }
        }
      } catch (error) {
        console.error(`[Auto-Close] Failed to fetch pair candles for ${pairSymbol}: ${error}`);
        // Continue without pair candles - strategy will fetch from API if needed
      }
    }

    // Call Python script
    return new Promise((resolve) => {
      const pythonScript = path.join(process.cwd(), 'python', 'check_strategy_exit.py');

      let stdout = '';
      let stderr = '';
      let resolved = false;

      if (isSpreadBased) {
        console.log(`[Exit-Check] Calling strategy exit check: ${trade.symbol} (${strategyName}), candles=${candlesData.length}, pair_candles=${pairCandlesData.length}, pair_symbol=${pairSymbol}`);
        if (pairCandlesData.length === 0) {
          console.warn(`[Exit-Check] ⚠️ WARNING: No pair candles being passed to Python script! pairSymbol=${pairSymbol}`);
        }
      } else {
        console.log(`[Auto-Close] Calling Python script for ${trade.symbol} (${strategyName})`);
        console.log(`[Auto-Close] Candles: ${candlesData.length}, Pair candles: ${pairCandlesData.length}`);
      }

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

      // TASK 10: Set timeout to prevent hanging processes (30 seconds)
      const timeout = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          const errorMsg = (
            `[Auto-Close] CRITICAL TIMEOUT: Strategy exit check TIMEOUT for ` +
            `${trade.symbol} (${strategyName}) - process took > 30 seconds. ` +
            `Trade ID: ${trade.id}. Exit signal may have been missed.`
          );
          console.error(errorMsg);
          pythonProcess.kill();
          resolve({ success: false, error: errorMsg });
        }
      }, 30000);

      pythonProcess.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      pythonProcess.on('close', (code) => {
        if (resolved) return; // Already timed out
        resolved = true;
        clearTimeout(timeout);

        // ALWAYS log Python stderr output (contains debug logs)
        if (stderr) {
          console.log(`[Exit-Check] Python script output:\n${stderr}`);
        }

        if (code !== 0) {
          const errorMsg = `Strategy exit check failed with exit code ${code}`;
          console.error(`[Auto-Close] CRITICAL: ${errorMsg} for ${trade.symbol} (${strategyName})`);
          console.error(`[Auto-Close] stdout: ${stdout}`);
          resolve({ success: false, error: errorMsg });
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

            if (isSpreadBased) {
              const pairPriceStr = exitResult.pair_exit_price ? `, pair_exit=${exitResult.pair_exit_price.toFixed(2)}` : '';
              const exitPriceStr = exitResult.exitPrice ? exitResult.exitPrice.toFixed(2) : 'N/A';
              console.log(`[Exit-Check] EXIT SIGNAL: reason=${result.exit_reason}, exit_price=${exitPriceStr}${pairPriceStr}`);
            }

            resolve({ success: true, exit: exitResult });
          } else {
            // Strategy check succeeded, but no exit signal - this is normal
            if (isSpreadBased) {
              console.log(`[Exit-Check] No exit signal (should_exit=${result.should_exit})`);
            } else {
              console.log(`[Auto-Close] ${trade.symbol} - Strategy exit check completed: no exit signal (should_exit=${result.should_exit})`);
            }
            resolve({ success: true, exit: null });
          }
        } catch (error) {
          const errorMsg = `Failed to parse strategy exit result: ${error}`;
          console.error(`[Auto-Close] CRITICAL: ${errorMsg} for ${trade.symbol}`);
          console.error(`[Auto-Close] stdout was: ${stdout}`);
          resolve({ success: false, error: errorMsg });
        }
      });

      pythonProcess.on('error', (error) => {
        if (resolved) return; // Already timed out
        resolved = true;
        clearTimeout(timeout);
        const errorMsg = `Error spawning strategy exit check: ${error}`;
        console.error(`[Auto-Close] CRITICAL: ${errorMsg} for ${trade.symbol}`);
        resolve({ success: false, error: errorMsg });
      });
    });
  } catch (error) {
    const errorMsg = `Error calling strategy exit check: ${error}`;
    console.error(`[Auto-Close] CRITICAL: ${errorMsg} for ${trade.symbol}`);
    return { success: false, error: errorMsg };
  }
}

/**
 * POST /api/bot/simulator/auto-close
 * Check all open paper trades using HISTORICAL candles from trade creation
 * Accurately detects if SL/TP was hit at any point since trade was created
 */
export async function POST() {
  const checkStartTime = Date.now();
  // TASK 10: Log when auto-close route starts
  console.log(`\n${'='.repeat(80)}`);
  console.log(`[Auto-Close] ========== AUTO-CLOSE CHECK STARTED ==========`);
  console.log(`[Auto-Close] Time: ${new Date().toISOString()}`);
  console.log(`${'='.repeat(80)}\n`);

  try {
    if (!await isTradingDbAvailable()) {
      console.error(`[Auto-Close] CRITICAL: Trading database not available`);
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    console.log(`[Auto-Close] Step 1: Fetching all open trades from database...`);
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

    console.log(`[Auto-Close] Step 1 COMPLETE: Found ${openTrades.length} open trades to check`);
    if (openTrades.length === 0) {
      console.log(`[Auto-Close] No trades to process. Exiting.`);
    } else {
      openTrades.forEach((t, idx) => {
        console.log(`  [${idx + 1}] ${t.symbol} (${t.status}) - entry=${t.entry_price}, SL=${t.stop_loss}, TP=${t.take_profit}`);
      });
    }

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
      console.log(`\n${'─'.repeat(80)}`);
      console.log(`[Auto-Close] PROCESSING TRADE: ${trade.symbol} (ID: ${trade.id})`);
      console.log(`[Auto-Close] Status: ${trade.status} | Side: ${trade.side} | Strategy Type: ${trade.strategy_type}`);
      console.log(`${'─'.repeat(80)}`);

      const timeframe = trade.timeframe || '1h';
      // Use trade.strategy_name directly (stored in database), fall back to instance settings for backwards compatibility
      const strategyName = trade.strategy_name || getStrategyNameFromSettings((trade as any).instance_settings);

      console.log(`[Auto-Close] Strategy: ${strategyName || 'UNKNOWN'} | Timeframe: ${timeframe}`);
      console.log(`[Auto-Close] Entry: ${trade.entry_price} | SL: ${trade.stop_loss} | TP: ${trade.take_profit}`);

      try {
        const isLong = trade.side === 'Buy';

        // CRITICAL: These are required trading values - NO FALLBACKS ALLOWED
        if (!trade.entry_price) {
          console.error(`[Auto-Close] TRADE SKIPPED: Missing entry_price for trade ${trade.id}`);
          continue;
        }
        if (!trade.stop_loss) {
          console.error(`[Auto-Close] TRADE SKIPPED: Missing stop_loss for trade ${trade.id}`);
          continue;
        }
        if (!trade.take_profit) {
          console.error(`[Auto-Close] TRADE SKIPPED: Missing take_profit for trade ${trade.id}`);
          continue;
        }

        const entryPrice = trade.entry_price;
        const stopLoss = trade.stop_loss;
        const takeProfit = trade.take_profit;

        console.log(`[Auto-Close] Step 2: Getting max_open_bars config for ${timeframe}/${trade.status}/${trade.strategy_type}...`);
        // Get max open bars for this trade's timeframe, status, and strategy type (0 = disabled)
        const maxOpenBars = await getMaxOpenBarsForTimeframe(
          timeframe,
          trade.status as 'pending_fill' | 'paper_trade' | 'filled',
          trade.strategy_type
        );
        console.log(`[Auto-Close] Step 2 COMPLETE: max_open_bars=${maxOpenBars}`);

        console.log(`[Auto-Close] Step 3: Parsing trade timestamps...`);
        // Parse trade creation time - validate it's a valid date
        const createdAt = normalizeTimestamp(trade.created_at);
        if (createdAt === null) {
          console.error(`[Auto-Close] SKIP: Invalid created_at date for trade ${trade.id}: ${trade.created_at}`);
          continue; // Skip this trade
        }
        console.log(`[Auto-Close] Step 3 COMPLETE: created_at=${new Date(createdAt).toISOString()}`);

        console.log(`[Auto-Close] Step 4: Determining signal time (from recommendation or created_at)...`);
        // CRITICAL: Use recommendation's analyzed_at (signal time) as the starting point
        // This ensures we check candles from when the signal was generated, not when trade was created
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
                console.log(`[Auto-Close] Step 4 COMPLETE: Using recommendation signal time: ${new Date(signalTime).toISOString()}`);
              }
            }
          } catch (error) {
            console.warn(`[Auto-Close] Step 4 WARNING: Failed to fetch recommendation time for trade ${trade.id}: ${error}`);
            console.log(`[Auto-Close] Step 4 COMPLETE: Falling back to created_at: ${new Date(signalTime).toISOString()}`);
          }
        } else {
          console.log(`[Auto-Close] Step 4 COMPLETE: No recommendation_id, using created_at: ${new Date(signalTime).toISOString()}`);
        }

        console.log(`[Auto-Close] Step 5: Fetching historical candles from ${new Date(signalTime).toISOString()} to now...`);
        // Fetch all candles from signal time (not creation time) to now
        const candles = await getHistoricalCandles(trade.symbol, timeframe, signalTime, trade.strategy_type || undefined);
        console.log(`[Auto-Close] Step 5 COMPLETE: Fetched ${candles.length} candles`);

      if (candles.length === 0) {
        // Fallback: get current price from ticker API
        console.log(`[Auto-Close] Step 5 RESULT: No candles available, fetching current price from ticker...`);
        const currentPrice = await getCurrentPrice(trade.symbol);
        console.log(`[Auto-Close] Current price: ${currentPrice}`);

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
        console.log(`[Auto-Close] TRADE SKIPPED: No candles available\n`);
        continue;
      }

      console.log(`[Auto-Close] Step 6: Validating candle data structure...`);
      // CRITICAL: Validate that we have candles BEFORE signal time (for lookback) AND after (for walk-forward)
      const candlesBeforeSignal = candles.filter(c => {
        const candleTs = normalizeTimestamp(c.timestamp);
        return candleTs !== null && candleTs < signalTime;
      });
      const candlesAfterSignal = candles.filter(c => {
        const candleTs = normalizeTimestamp(c.timestamp);
        return candleTs !== null && candleTs >= signalTime;
      });

      const lookbackRequired = getMinimumCandlesRequired(trade.strategy_type || undefined);
      console.log(`[Auto-Close] Step 6 COMPLETE: ${candlesBeforeSignal.length} lookback candles (need ${lookbackRequired}), ${candlesAfterSignal.length} walk-forward candles`);

      // STRICT VALIDATION: Must have enough lookback candles
      if (candlesBeforeSignal.length < lookbackRequired) {
        console.error(`[Auto-Close] TRADE SKIPPED: Insufficient lookback candles: have ${candlesBeforeSignal.length}, need ${lookbackRequired}`);
        const currentPrice = await getCurrentPrice(trade.symbol);
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

      // Use all candles (lookback + walk-forward) for processing
      const candlesAfterCreation = candles;

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

      console.log(`[Auto-Close] Step 7: Checking fill status...`);
      // STEP 1: Check if trade is already filled or find fill candle
      let fillCandleIndex = 0;
      let fillTime: string | null = null; // Track fill time for sanity checks
      const alreadyFilled = trade.status === 'filled' && trade.filled_at;

      console.log(`[Auto-Close] Step 7 DETAIL: alreadyFilled=${alreadyFilled}, trade.status=${trade.status}`);

      // Fetch strategy metadata for spread-based fill detection
      // CRITICAL: Use trade's own strategy_metadata (single source of truth)
      // Fallback to recommendation only if trade doesn't have it
      let strategyMetadata: any = {};
      let pairSymbolForExit: string | null = null;
      let pairCandlesForExit: Candle[] = [];

      // PRIORITY 1: Use strategy_metadata from trade (stored during trade creation)
      if (trade.strategy_metadata) {
        console.log(`[Auto-Close] Step 7 DETAIL: Using strategy_metadata from trade`);
        strategyMetadata = typeof trade.strategy_metadata === 'string'
          ? JSON.parse(trade.strategy_metadata)
          : trade.strategy_metadata;
        console.log(`[Auto-Close] Step 7 DETAIL: Strategy metadata from trade, pair_symbol=${strategyMetadata.pair_symbol}`);
      }
      // PRIORITY 2: Fallback to recommendation if trade doesn't have metadata
      else if (trade.recommendation_id) {
        console.log(`[Auto-Close] Step 7 DETAIL: Trade has no strategy_metadata, fetching from recommendation...`);
        try {
          const rec = await dbQuery<any>(`
            SELECT strategy_metadata FROM recommendations WHERE id = ?
          `, [trade.recommendation_id]);

          if (rec && rec.length > 0 && rec[0].strategy_metadata) {
            strategyMetadata = typeof rec[0].strategy_metadata === 'string'
              ? JSON.parse(rec[0].strategy_metadata)
              : rec[0].strategy_metadata;
            console.log(`[Auto-Close] Step 7 DETAIL: Strategy metadata from recommendation, pair_symbol=${strategyMetadata.pair_symbol}`);
          }
        } catch (error) {
          console.warn(`[Auto-Close] Step 7 WARNING: Failed to fetch strategy metadata from recommendation: ${error}`);
        }
      }

      if (alreadyFilled) {
        console.log(`[Auto-Close] Step 7 RESULT: Trade already filled at ${new Date(trade.filled_at as any).toISOString()}`);
        // Trade already filled - find the fill candle index to start SL/TP check from
        const filledAtMs = normalizeTimestamp(trade.filled_at);
        console.log(`[Auto-Close] Step 7 DETAIL: Finding fill candle index...`);
        if (filledAtMs !== null) {
          fillCandleIndex = candlesAfterCreation.findIndex(c => {
            const candleTs = normalizeTimestamp(c.timestamp);
            return candleTs !== null && candleTs >= filledAtMs;
          });

          // CRITICAL: If no candles exist after fill time, we cannot check for exits
          // Skip this trade - it cannot have exited if there are no candles after it filled
          if (fillCandleIndex === -1) {
            console.log(`[Auto-Close] TRADE SKIPPED: No candles after fill time (${new Date(filledAtMs).toISOString()})\n`);
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
          console.log(`[Auto-Close] Step 7 DETAIL: Fill candle index = ${fillCandleIndex}`);
        }

        // For spread-based strategies, also fetch pair candles for exit checking
        if (strategyMetadata && strategyMetadata.pair_symbol) {
          const pairSymbol = strategyMetadata.pair_symbol;
          pairSymbolForExit = pairSymbol;
          console.log(`[Auto-Close] Step 7 DETAIL: Spread-based strategy (already filled) - fetching pair candles for ${pairSymbol}...`);
          try {
            pairCandlesForExit = await getHistoricalCandles(
              pairSymbol,
              timeframe,
              signalTime,
              trade.strategy_type || undefined
            );
            console.log(`[Auto-Close] Step 7 DETAIL: Fetched ${pairCandlesForExit.length} pair candles for ${pairSymbol} (includes lookback + walk-forward)`);
          } catch (error) {
            console.warn(`[Auto-Close] Step 7 WARNING: Failed to fetch pair candles for ${pairSymbol}: ${error}`);
          }
        }
      } else {
        console.log(`[Auto-Close] Step 7 DETAIL: Trade not yet filled, will search for fill candle...`);
        console.log(`[Auto-Close] Step 7 RESULT: Trade not yet filled, searching for fill candle...`);
        // Find fill candle - use spread-based logic if this is a spread-based strategy
        let fillResult: FillResult;

        if (strategyMetadata && strategyMetadata.pair_symbol) {
          // TASK 8: Spread-based strategy - SIGNAL-BASED FILL
          // For signal-based trades, fill immediately at signal time without waiting for pair candles
          console.log(`[Auto-Close] Step 7 DETAIL: Spread-based strategy detected (signal-based fill)`);

          // TASK 8: Fetch FULL pair candles for exit signal detection
          const pairSymbol = strategyMetadata.pair_symbol;

          // CRITICAL: Pair entry price is REQUIRED for spread-based trades - NO FALLBACK
          if (strategyMetadata.price_y_at_entry === undefined || strategyMetadata.price_y_at_entry === null) {
            console.error(`[Auto-Close] TRADE SKIPPED: Missing price_y_at_entry in strategy_metadata for spread-based trade ${trade.id}`);
            continue;
          }

          const pairEntryPrice = strategyMetadata.price_y_at_entry;
          pairSymbolForExit = pairSymbol; // Store for Step 8

          console.log(`[Auto-Close] Step 7 DETAIL: Fetching pair candles for ${pairSymbol}...`);
          const pairFetchStart = Date.now();
          try {
            console.log(`[Auto-Close] Step 7 DETAIL: Calling getHistoricalCandles for ${pairSymbol}...`);
            pairCandlesForExit = await getHistoricalCandles(
              pairSymbol,
              timeframe,
              signalTime,
              trade.strategy_type || undefined
            );
            const pairFetchDuration = Date.now() - pairFetchStart;
            console.log(`[Auto-Close] Step 7 DETAIL: getHistoricalCandles returned ${pairCandlesForExit.length} candles in ${pairFetchDuration}ms (includes lookback + walk-forward)`);

            if (!pairCandlesForExit || pairCandlesForExit.length === 0) {
              console.error(
                `[Auto-Close] Step 7 WARNING: Failed to fetch pair candles for ${pairSymbol}. ` +
                `Cannot check exit signals for spread-based trade ${trade.symbol}`
              );
            } else {
              const minRequired = getMinimumCandlesRequired(trade.strategy_type || undefined);
              const signalTimeStr = new Date(signalTime).toISOString();
              const nowStr = new Date().toISOString();
              console.log(
                `[Auto-Close] Step 7 COMPLETE: Fetched ${pairCandlesForExit.length} pair candles for ${pairSymbol} ` +
                `(${candles.length} main candles). ` +
                `Min required: ${minRequired}, Time range: ${signalTimeStr} to ${nowStr}`
              );
            }
          } catch (e) {
            const pairFetchDuration = Date.now() - pairFetchStart;
            console.error(
              `[Auto-Close] Step 7 ERROR: Failed to fetch pair candles for ${pairSymbol} after ${pairFetchDuration}ms: ${e}. ` +
              `Cannot check exit signals for spread-based trade ${trade.symbol}`
            );
          }

          // Signal-based fill: Trade fills at the first candle after signal generation
          console.log(`[Auto-Close] Step 7 DETAIL: Checking spread-based fill...`);
          fillResult = findSpreadBasedFillCandle(
            candlesAfterCreation,
            pairCandlesForExit.length > 0 ? pairCandlesForExit : [],  // Pass full pair candles array
            entryPrice,
            pairEntryPrice
          );

          if (fillResult.filled) {
            console.log(`[Auto-Close] Step 7 RESULT: SPREAD-BASED FILL - Trade filled at signal time`);
          } else {
            console.log(`[Auto-Close] Step 7 RESULT: SPREAD-BASED NOT FILLED - No fill signal detected`);
          }
        } else {
          // Price-based strategy - use simple entry price check
          console.log(`[Auto-Close] Step 7 DETAIL: Checking price-based fill...`);
          fillResult = findFillCandle(candlesAfterCreation, entryPrice);
          if (fillResult.filled) {
            console.log(`[Auto-Close] Step 7 RESULT: PRICE-BASED FILL - Trade filled`);
          } else {
            console.log(`[Auto-Close] Step 7 RESULT: PRICE-BASED NOT FILLED - Entry price not reached`);
          }
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

      console.log(`[Auto-Close] ✅ REACHED STEP 8: Checking exit conditions...`);
      // STEP 2: Check for SL/TP hit starting from candle AFTER fill
      // IMPORTANT: Only proceed if trade is actually filled
      // A trade can only be closed if it was filled first
      const isFilled = alreadyFilled || (trade.status === 'filled' && trade.filled_at);

      if (!isFilled) {
        // Trade was never filled - cannot close it
        // This should not happen as unfilled trades are handled above, but safety check
        console.log(`[Auto-Close] TRADE SKIPPED: Trade not filled, cannot check exit\n`);
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
      // Use strategyName extracted from instance_settings (line 959), not trade.strategy_name
      if (!strategyName) {
        console.error(`[Auto-Close] TRADE SKIPPED: No strategy_name found. Cannot determine exit logic.\n`);
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

      // Calculate bars since fill (for max_open_bars check)
      const barsOpen = candlesAfterCreation.length - fillCandleIndex;
      console.log(`[Auto-Close] Step 8 DETAIL: Bars open since fill = ${barsOpen}`);

      // STEP 2B: Determine exit logic based on strategy type
      let exitResult: ExitResult | null = null;
      const strategyType = trade.strategy_type || 'unknown';

      if (strategyType === 'price_based') {
        // Price-based strategies use TP/SL logic
        console.log(`[Auto-Close] Step 8 DETAIL: Price-based strategy - checking SL/TP`);
        exitResult = checkHistoricalSLTP(candlesAfterCreation, isLong, stopLoss, takeProfit, fillCandleIndex);
      } else if (strategyType === 'spread_based') {
        // Spread-based strategies use strategy.should_exit() ONLY
        console.log(`[Auto-Close] Step 8 DETAIL: Spread-based strategy - calling Python exit check`);
        console.log(`[Auto-Close] Step 8 DETAIL: About to call checkStrategyExit for ${trade.symbol} with pair_symbol=${pairSymbolForExit}...`);
        const checkStartTime = Date.now();
        const strategyCheckResult = await checkStrategyExit(trade, candlesAfterCreation, fillCandleIndex, strategyName, pairCandlesForExit, pairSymbolForExit || undefined);
        const checkDuration = Date.now() - checkStartTime;
        console.log(`[Auto-Close] Step 8 DETAIL: checkStrategyExit returned after ${checkDuration}ms`);

        // Handle strategy check result
        if (!strategyCheckResult.success) {
          // Strategy check failed - log error and skip trade
          console.error(`[Auto-Close] Step 8 RESULT: FAILED - ${strategyCheckResult.error}`);
          console.log(`[Auto-Close] TRADE SKIPPED: Strategy exit check failed\n`);
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: await getCurrentPrice(trade.symbol),
            instance_name: trade.instance_name,
            strategy_name: strategyName || undefined,
            timeframe: timeframe,
            candles_checked: candlesAfterCreation.length,
            bars_open: barsOpen,
            checked_at: new Date().toISOString()
          });
          continue;
        }

        // Strategy check succeeded - use the exit result (may be null if no exit signal)
        exitResult = strategyCheckResult.exit || null;

        if (!exitResult || !exitResult.hit) {
          // No exit signal - trade remains open (this is normal)
          console.log(`[Auto-Close] Step 8 RESULT: No exit signal - trade remains open`);
          console.log(`[Auto-Close] TRADE CHECKED: No action taken\n`);
          results.push({
            trade_id: trade.id,
            symbol: trade.symbol,
            action: 'checked',
            current_price: await getCurrentPrice(trade.symbol),
            instance_name: trade.instance_name,
            strategy_name: strategyName || undefined,
            timeframe: timeframe,
            candles_checked: candlesAfterCreation.length,
            bars_open: barsOpen,
            checked_at: new Date().toISOString()
          });
          continue;
        }
      } else {
        // Unknown strategy type - log error and skip
        // This is a safety net for future strategy types that haven't been implemented yet
        console.error(`[Auto-Close] Step 8 RESULT: FAILED - Unknown strategy type '${strategyType}'`);
        await logSimulatorError(
          trade.id,
          'UNKNOWN_STRATEGY_TYPE',
          `Unknown strategy type: ${strategyType}. Only 'price_based' and 'spread_based' are supported.`,
          {
            symbol: trade.symbol,
            strategy_type: strategyType,
            strategy_name: strategyName
          }
        );
        results.push({
          trade_id: trade.id,
          symbol: trade.symbol,
          action: 'checked',
          current_price: await getCurrentPrice(trade.symbol),
          instance_name: trade.instance_name,
          strategy_name: strategyName || undefined,
          timeframe: timeframe,
          candles_checked: candlesAfterCreation.length,
          bars_open: barsOpen,
          checked_at: new Date().toISOString()
        });
        continue;
      }

      if (exitResult && exitResult.hit) {
        console.log(`[Auto-Close] Step 8 RESULT: EXIT SIGNAL DETECTED - reason=${exitResult.reason}`);

        // PRIORITY 4: SANITY CHECK - Detect suspicious spread-based trade exits
        // Warn if spread-based trade exits on fill candle (fillCandleIndex === 0)
        if (trade.strategy_type === 'spread_based' && fillCandleIndex === 0) {
          console.warn(`[Auto-Close] SANITY CHECK WARNING: Spread-based trade exiting on fill candle. Reason: ${exitResult.reason}`);

          // If exit reason is tp_hit or sl_hit, this is a CRITICAL BUG
          // Spread-based trades should ONLY exit via z_score_exit or max_spread_deviation_exceeded
          if (exitResult.reason === 'tp_hit' || exitResult.reason === 'sl_hit') {
            console.error(`[Auto-Close] CRITICAL BUG: Spread-based trade should NOT exit via price-level SL/TP!`);
            console.error(`[Auto-Close] This indicates the Python script is still checking price-level SL/TP for spread-based trades.`);

            // Log to database for investigation
            await logSimulatorError(
              trade.id,
              'SPREAD_TRADE_PRICE_LEVEL_EXIT',
              `Spread-based trade exited via ${exitResult.reason} instead of z-score exit. This should not happen after the fix.`,
              {
                exit_result: exitResult,
                fill_candle_index: fillCandleIndex,
                strategy_type: trade.strategy_type,
                strategy_name: strategyName
              }
            );
          }
        }
      }

      if (exitResult && exitResult.hit && exitResult.exitPrice && exitResult.reason) {
        console.log(`[Auto-Close] Step 9: Processing trade closure...`);
        // Calculate P&L - handle both price-based and spread-based trades
        let pnl: number;
        let pnlPercent: number;

        if (trade.strategy_type === 'spread_based' && trade.pair_quantity && trade.pair_fill_price && exitResult.pair_exit_price) {
          // Spread-based trade: calculate P&L for both symbols
          console.log(`[Auto-Close] Step 9 DETAIL: Calculating P&L for spread-based trade...`);

          // CRITICAL: All values required for spread-based P&L - NO FALLBACKS
          if (!trade.fill_price) {
            console.error(`[Auto-Close] TRADE SKIPPED: Missing fill_price for spread-based trade ${trade.id}`);
            continue;
          }
          if (!trade.quantity) {
            console.error(`[Auto-Close] TRADE SKIPPED: Missing quantity for spread-based trade ${trade.id}`);
            continue;
          }

          const mainFillPrice = trade.fill_price;
          const mainQty = trade.quantity;
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

          console.log(`[Auto-Close] Step 9 DETAIL: Main P&L=${mainPnl.toFixed(2)}, Pair P&L=${pairPnl.toFixed(2)}, Total P&L=${pnl.toFixed(2)} (${pnlPercent.toFixed(2)}%)`);
        } else {
          // Price-based trade: calculate P&L for main symbol only
          console.log(`[Auto-Close] Step 9 DETAIL: Calculating P&L for price-based trade...`);

          // CRITICAL: All values required for price-based P&L - NO FALLBACKS
          if (!trade.fill_price) {
            console.error(`[Auto-Close] TRADE SKIPPED: Missing fill_price for price-based trade ${trade.id}`);
            continue;
          }
          if (!trade.quantity) {
            console.error(`[Auto-Close] TRADE SKIPPED: Missing quantity for price-based trade ${trade.id}`);
            continue;
          }

          const fillPrice = trade.fill_price;
          const qty = trade.quantity;
          pnl = isLong
            ? (exitResult.exitPrice - fillPrice) * qty
            : (fillPrice - exitResult.exitPrice) * qty;
          pnlPercent = fillPrice > 0 ? (pnl / (fillPrice * qty)) * 100 : 0;

          console.log(`[Auto-Close] Step 9 DETAIL: P&L=${pnl.toFixed(2)} (${pnlPercent.toFixed(2)}%)`);
        }

        console.log(`[Auto-Close] Step 9 DETAIL: Converting exit timestamp...`);
        // Get exit timestamp as ISO string
        // exitTimestamp is a number (Unix ms), convert to Date
        let exitTime: string;
        if (exitResult.exitTimestamp) {
          const exitTimeMs = typeof exitResult.exitTimestamp === 'string'
            ? parseInt(exitResult.exitTimestamp, 10)
            : exitResult.exitTimestamp;

          if (!exitTimeMs || isNaN(exitTimeMs)) {
            console.error(`[Auto-Close] Step 9 FAILED: Invalid exitTimestamp for trade ${trade.id}: ${exitResult.exitTimestamp}`);
            continue; // Skip this trade
          }
          exitTime = new Date(exitTimeMs).toISOString();
        } else {
          exitTime = new Date().toISOString();
        }
        console.log(`[Auto-Close] Step 9 DETAIL: Exit time=${exitTime}`);

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

        console.log(`[Auto-Close] Step 10: Updating database with trade closure...`);
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
        console.log(`[Auto-Close] Step 10 DETAIL: Trade record updated`);

        console.log(`[Auto-Close] Step 10 DETAIL: Updating run aggregates...`);
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
        console.log(`[Auto-Close] Step 10 COMPLETE: Run aggregates updated`);

        closedCount++;
        console.log(`[Auto-Close] TRADE CLOSED: ${trade.symbol} | Exit: ${exitResult.reason} @ ${exitResult.exitPrice.toFixed(2)} | P&L: ${pnl.toFixed(2)} (${pnlPercent.toFixed(2)}%)\n`);

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
    const stillOpen = openTrades.length - filledCount - closedCount - cancelledCount;

    // TASK 10: Log completion statistics
    console.log(`\n${'='.repeat(80)}`);
    console.log(`[Auto-Close] ========== AUTO-CLOSE CHECK COMPLETED ==========`);
    console.log(`[Auto-Close] Summary:`);
    console.log(`[Auto-Close]   Total trades checked: ${openTrades.length}`);
    console.log(`[Auto-Close]   Filled: ${filledCount}`);
    console.log(`[Auto-Close]   Closed: ${closedCount}`);
    console.log(`[Auto-Close]   Cancelled: ${cancelledCount}`);
    console.log(`[Auto-Close]   Still open: ${stillOpen}`);
    console.log(`[Auto-Close]   Duration: ${checkDuration}ms`);
    console.log(`[Auto-Close] Time: ${new Date().toISOString()}`);
    console.log(`${'='.repeat(80)}\n`);

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
    console.error(`\n[Auto-Close] CRITICAL ERROR: Auto-close check failed`);
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


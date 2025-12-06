/**
 * Bot Trade Candles API - GET historical candles for a trade
 * Fetches candles from Bybit for displaying on trade charts
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

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
    // Use bot-specific candle fetcher (copied from tournament version with enhancements)
    const pythonScript = path.join(process.cwd(), 'python', 'trading_bot', 'utils', 'get_trade_candles_bot_control.py');

    const pythonProcess = spawn('python3', [
      pythonScript,
      symbol,
      timeframe,
      timestamp,
      before.toString(),
      after.toString()
    ]);

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    const result = await new Promise<CandlesResponse>((resolve, reject) => {
      pythonProcess.on('close', (code) => {
        if (code !== 0) {
          console.error('Python script error:', stderr);
          reject(new Error(`Python script exited with code ${code}: ${stderr}`));
          return;
        }

        try {
          const data = JSON.parse(stdout);
          resolve(data);
        } catch (err) {
          console.error('Failed to parse Python output:', stdout);
          reject(new Error('Failed to parse candles data'));
        }
      });
    });

    return NextResponse.json(result);
  } catch (error) {
    console.error('Trade candles GET error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch candles' },
      { status: 500 }
    );
  }
}


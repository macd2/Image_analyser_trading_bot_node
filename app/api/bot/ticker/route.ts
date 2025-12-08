/**
 * Get current ticker price for a symbol from Bybit
 * GET /api/bot/ticker?symbol=BTCUSDT
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol');

  if (!symbol) {
    return NextResponse.json(
      { error: 'Missing required parameter: symbol' },
      { status: 400 }
    );
  }

  try {
    const pythonScript = path.join(process.cwd(), 'python', 'trading_bot', 'utils', 'get_ticker.py');

    const pythonProcess = spawn('python3', [pythonScript, symbol], {
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
    });

    await new Promise<void>((resolve, reject) => {
      pythonProcess.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`Python process exited with code ${code}: ${stderr}`));
        }
      });

      pythonProcess.on('error', (err) => {
        reject(err);
      });

      // Timeout after 10 seconds
      setTimeout(() => {
        pythonProcess.kill();
        reject(new Error('Ticker fetch timeout'));
      }, 10000);
    });

    const result = JSON.parse(stdout.trim());

    if (result.error) {
      return NextResponse.json({ error: result.error }, { status: 500 });
    }

    return NextResponse.json(result);
  } catch (error) {
    console.error('Ticker API error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}


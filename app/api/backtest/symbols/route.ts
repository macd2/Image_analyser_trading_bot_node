/**
 * Get available symbols and timeframes from chart images directory
 */

import { NextResponse } from 'next/server';
import { readdir } from 'fs/promises';
import path from 'path';

export async function GET() {
  try {
    const chartsDir = process.env.PYTHON_CHARTS_PATH
      ? path.resolve(process.cwd(), process.env.PYTHON_CHARTS_PATH)
      : path.resolve(process.cwd(), '../../data/charts/.backup');

    // Read all files in charts directory
    const files = await readdir(chartsDir);

    // Extract unique symbols and timeframes from filenames (format: SYMBOL_TIMEFRAME_TIMESTAMP.png)
    const symbolSet = new Set<string>();
    const timeframeSet = new Set<string>();
    files.forEach(file => {
      if (file.endsWith('.png')) {
        const parts = file.split('_');
        const symbol = parts[0];
        const timeframe = parts[1];
        if (symbol && symbol.endsWith('USDT')) {
          symbolSet.add(symbol);
        }
        if (timeframe && /^[0-9]+[mhd]$/i.test(timeframe)) {
          timeframeSet.add(timeframe.toLowerCase());
        }
      }
    });

    const symbols = Array.from(symbolSet).sort();
    // Sort timeframes by duration (5m < 15m < 1h < 4h < 1d)
    const timeframeOrder = ['5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'];
    const timeframes = Array.from(timeframeSet).sort((a, b) => {
      const idxA = timeframeOrder.indexOf(a);
      const idxB = timeframeOrder.indexOf(b);
      return (idxA === -1 ? 999 : idxA) - (idxB === -1 ? 999 : idxB);
    });

    return NextResponse.json({
      symbols,
      timeframes,
      count: symbols.length,
      chartsDir
    });
  } catch (error) {
    console.error('Error reading symbols:', error);
    return NextResponse.json({
      error: 'Failed to read symbols',
      symbols: [],
      timeframes: [],
      count: 0
    }, { status: 500 });
  }
}


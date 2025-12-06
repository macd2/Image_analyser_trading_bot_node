import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function GET(request: NextRequest): Promise<Response> {
  const searchParams = request.nextUrl.searchParams;
  const symbol = searchParams.get('symbol');
  const timeframe = searchParams.get('timeframe');
  const timestamp = searchParams.get('timestamp');
  const candlesBefore = searchParams.get('before') || '50';
  const candlesAfter = searchParams.get('after') || '150';  // More candles after for expired trades

  if (!symbol || !timeframe || !timestamp) {
    return NextResponse.json(
      { error: 'Missing required parameters: symbol, timeframe, timestamp' },
      { status: 400 }
    );
  }

  const pythonDir = path.join(process.cwd(), 'python');
  const scriptPath = path.join(pythonDir, 'prompt_performance', 'get_trade_candles.py');

  return new Promise((resolve) => {
    const proc = spawn('python3', [
      scriptPath,
      symbol,
      timeframe,
      timestamp,
      candlesBefore,
      candlesAfter
    ], {
      cwd: pythonDir,
      env: { ...process.env, PYTHONPATH: pythonDir }
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      if (code !== 0) {
        console.error('Python error:', stderr);
        resolve(NextResponse.json({ error: stderr || 'Failed to fetch candles' }, { status: 500 }));
        return;
      }

      try {
        const result = JSON.parse(stdout);
        resolve(NextResponse.json(result));
      } catch {
        resolve(NextResponse.json({ error: 'Invalid JSON from Python' }, { status: 500 }));
      }
    });

    proc.on('error', (err) => {
      resolve(NextResponse.json({ error: err.message }, { status: 500 }));
    });
  });
}


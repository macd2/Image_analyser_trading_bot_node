/**
 * Backtest API - Triggers Python backtest runner with real-time progress
 */

import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

export interface BacktestRequest {
  prompts: string[];
  symbols: string[];
  numImages: number;
  timeframes: string[];
}

interface BacktestState {
  status: 'starting' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  result?: unknown;
  logs: string[];
  config?: BacktestRequest;
  process?: ChildProcess;
  startedAt: number;
}

// Store running backtests (global for this instance)
const runningBacktests = new Map<string, BacktestState>();

export async function POST(request: Request) {
  try {
    const body: BacktestRequest = await request.json();
    const { prompts, symbols, numImages, timeframes } = body;

    // Validate
    if (!prompts?.length) return NextResponse.json({ error: 'No prompts selected' }, { status: 400 });
    if (!symbols?.length) return NextResponse.json({ error: 'No symbols selected' }, { status: 400 });

    // Generate run ID
    const runId = `bt_${Date.now()}`;
    const totalImages = prompts.length * symbols.length * numImages;

    // Store initial status
    runningBacktests.set(runId, {
      status: 'starting',
      progress: 0,
      logs: [],
      config: body,
      startedAt: Date.now(),
    });

    // Python code is in ./python folder (standalone)
    const pythonDir = path.resolve(process.cwd(), 'python');
    const chartsDir = process.env.PYTHON_CHARTS_PATH
      ? path.resolve(process.cwd(), process.env.PYTHON_CHARTS_PATH)
      : path.resolve(process.cwd(), 'data/charts/.backup');
    // Note: analysis_results.db is legacy - backtests now use data/backtests.db
    const dbPath = process.env.PYTHON_DATABASE_PATH
      ? path.resolve(process.cwd(), process.env.PYTHON_DATABASE_PATH)
      : path.resolve(process.cwd(), 'data/backtests.db');

    // Run Python backtest with progress output
    const pythonCode = `
import sys
sys.path.insert(0, '${pythonDir}')
from prompt_performance.backtest_with_images import ImageBacktester
import json

print("PROGRESS:0:Initializing backtest...", flush=True)

total = ${totalImages}
processed = 0

def progress_callback(data):
    global processed
    processed += 1
    pct = min(int((processed / total) * 100), 95)
    event_type = data.get('type', 'unknown')

    if event_type == 'image_start':
        prompt = data.get('prompt_name', 'unknown')
        symbol = data.get('symbol', 'unknown')
        print(f"PROGRESS:{pct}:Analyzing {symbol} with {prompt}", flush=True)
    elif event_type == 'start':
        print(f"PROGRESS:5:Starting backtest run...", flush=True)
    elif event_type == 'complete':
        print(f"PROGRESS:95:Backtest complete, saving results...", flush=True)

bt = ImageBacktester(
    charts_dir='${chartsDir}',
    db_path='${dbPath}',
    progress_callback=progress_callback
)
print("PROGRESS:10:Backtest initialized, selecting images...", flush=True)

result = bt.backtest_with_images(
    prompts=${JSON.stringify(prompts)},
    symbols=${JSON.stringify(symbols)},
    num_images=${numImages},
    timeframes=${JSON.stringify(timeframes.length ? timeframes : null)},
    verbose=True
)
print("PROGRESS:98:Finalizing results...", flush=True)
print("RESULT:" + json.dumps(result), flush=True)
print("PROGRESS:100:Completed", flush=True)
`;

    const python = spawn('python3', ['-c', pythonCode], {
      cwd: pythonDir,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    });

    const state = runningBacktests.get(runId)!;
    state.process = python;
    state.status = 'running';

    python.stdout.on('data', (data) => {
      const lines = data.toString().split('\n').filter(Boolean);
      for (const line of lines) {
        if (line.startsWith('PROGRESS:')) {
          const parts = line.split(':');
          const pct = parseInt(parts[1]) || state.progress;
          const msg = parts.slice(2).join(':') || '';
          state.progress = pct;
          if (msg) {
            state.logs.push(`[${pct}%] ${msg}`);
            if (state.logs.length > 100) state.logs.shift();
          }
        } else if (line.startsWith('RESULT:')) {
          try {
            state.result = JSON.parse(line.slice(7));
            state.progress = 100;
          } catch { /* ignore parse errors */ }
        } else {
          // Filter: only INFO, WARNING, ERROR level logs (skip DEBUG)
          const isImportant = line.includes('INFO') ||
                             line.includes('WARNING') ||
                             line.includes('ERROR') ||
                             line.includes('✓') ||
                             line.includes('✗') ||
                             line.includes('Win') ||
                             line.includes('Loss') ||
                             line.includes('Analyzing') ||
                             line.includes('Completed') ||
                             line.includes('Started');
          if (isImportant) {
            state.logs.push(line);
            if (state.logs.length > 100) state.logs.shift();
          }
        }
      }
    });

    python.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) {
        state.logs.push(`[stderr] ${msg}`);
        if (state.logs.length > 50) state.logs.shift();
      }
    });

    python.on('close', (code) => {
      if (state.status === 'cancelled') return;

      if (code === 0) {
        state.status = 'completed';
        state.progress = 100;
        if (!state.result) {
          state.result = { success: true, message: 'Backtest completed' };
        }
      } else {
        state.status = 'failed';
        state.result = { error: state.logs.slice(-5).join('\n') || 'Unknown error' };
      }
    });

    return NextResponse.json({
      success: true,
      runId,
      message: 'Backtest started',
      config: body,
    });
  } catch (error) {
    console.error('Backtest API error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to start backtest' },
      { status: 500 }
    );
  }
}

// GET - Check backtest status
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const runId = searchParams.get('runId');

  if (!runId) {
    // Return summary of all backtests
    const all: Record<string, { status: string; progress: number; startedAt: number }> = {};
    runningBacktests.forEach((state, id) => {
      all[id] = { status: state.status, progress: state.progress, startedAt: state.startedAt };
    });
    return NextResponse.json({ backtests: all });
  }

  const state = runningBacktests.get(runId);
  if (!state) {
    return NextResponse.json({ error: 'Backtest not found' }, { status: 404 });
  }

  // Return state without the process object
  return NextResponse.json({
    runId,
    status: state.status,
    progress: state.progress,
    result: state.result,
    logs: state.logs.slice(-20), // Last 20 log lines
    config: state.config,
    startedAt: state.startedAt,
  });
}

// DELETE - Cancel a backtest
export async function DELETE(request: Request) {
  const { searchParams } = new URL(request.url);
  const runId = searchParams.get('runId');

  if (!runId) {
    return NextResponse.json({ error: 'Missing runId' }, { status: 400 });
  }

  const state = runningBacktests.get(runId);
  if (!state) {
    return NextResponse.json({ error: 'Backtest not found' }, { status: 404 });
  }

  // Kill the process if running
  if (state.process && state.status === 'running') {
    state.process.kill('SIGTERM');
    state.status = 'cancelled';
    state.logs.push('Cancelled by user');
  }

  return NextResponse.json({ success: true, runId, status: 'cancelled' });
}


/**
 * Tournament History API - List completed tournament runs from DB
 */

import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function GET(request: Request): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const tournamentId = searchParams.get('id');
  const limit = parseInt(searchParams.get('limit') || '20');

  const pythonDir = path.join(process.cwd(), 'python');

  // Build Python script to query the store
  const script = tournamentId
    ? `
import json
import sys
sys.path.insert(0, '${pythonDir}')
from prompt_performance.core.backtest_store import BacktestStore
store = BacktestStore()
result = store.tournament_get('${tournamentId}')
print(json.dumps(result or {'error': 'not found'}))
`
    : `
import json
import sys
sys.path.insert(0, '${pythonDir}')
from prompt_performance.core.backtest_store import BacktestStore
store = BacktestStore()
runs = store.tournament_list(limit=${limit})
print(json.dumps({'runs': runs}))
`;

  return new Promise<Response>((resolve) => {
    // Pass environment variables to Python subprocess (needed for DB_TYPE, DATABASE_URL)
    const proc = spawn('python3', ['-c', script], {
      cwd: pythonDir,
      env: { ...process.env }
    });
    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      if (code !== 0) {
        resolve(NextResponse.json({ error: stderr || 'Python error' }, { status: 500 }));
        return;
      }
      try {
        const data = JSON.parse(stdout.trim());
        resolve(NextResponse.json(data));
      } catch {
        resolve(NextResponse.json({ error: 'JSON parse error', raw: stdout }, { status: 500 }));
      }
    });

    // Increase timeout for single tournament queries (they return large phase_details)
    const timeoutMs = tournamentId ? 30000 : 10000;
    setTimeout(() => {
      proc.kill();
      resolve(NextResponse.json({ error: 'Timeout' }, { status: 504 }));
    }, timeoutMs);
  });
}


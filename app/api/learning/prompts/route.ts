/**
 * Prompts API - Returns available prompts from analyzer_prompt.py file
 * Only returns actual function names that exist in the codebase
 */

import { NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function GET(): Promise<Response> {
  const pythonDir = path.join(process.cwd(), 'python');

  // Get actual prompt functions from analyzer_prompt.py
  const script = `
import sys
import json
import inspect
sys.path.insert(0, '${pythonDir}')

from trading_bot.core.prompts import analyzer_prompt as ap

# Get all functions that match the prompt pattern
funcs = [
    name for name, fn in inspect.getmembers(ap, inspect.isfunction)
    if name.startswith('get_analyzer_prompt') and not name.startswith('_')
]

print(json.dumps({'prompts': sorted(funcs)}))
`;

  return new Promise<Response>((resolve) => {
    const proc = spawn('python3', ['-c', script], { cwd: pythonDir });
    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      if (code !== 0) {
        console.error('Prompts API Python error:', stderr);
        resolve(NextResponse.json({ error: stderr || 'Failed to get prompts' }, { status: 500 }));
        return;
      }
      try {
        const data = JSON.parse(stdout.trim());
        resolve(NextResponse.json({ success: true, ...data }));
      } catch {
        resolve(NextResponse.json({ error: 'JSON parse error', raw: stdout }, { status: 500 }));
      }
    });

    setTimeout(() => {
      proc.kill();
      resolve(NextResponse.json({ error: 'Timeout' }, { status: 504 }));
    }, 5000);
  });
}


/**
 * Tournament API - Find Best Prompt
 * POST: Start a new tournament
 * GET: Get tournament status
 * DELETE: Cancel tournament
 */

import { NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

interface TournamentState {
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  currentPhase: number;
  activePrompts: string[];
  rankings: Array<{ prompt: string; win_rate: number; avg_pnl: number }>;
  logs: string[];
  result: unknown | null;
  config: unknown;
  startedAt: number;
  process?: ChildProcess;
}

// Active tournaments - use globalThis to persist across hot reloads in dev
declare global {
  // eslint-disable-next-line no-var
  var _runningTournaments: Map<string, TournamentState> | undefined;
}

const runningTournaments = globalThis._runningTournaments ?? new Map<string, TournamentState>();
globalThis._runningTournaments = runningTournaments;

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      prompts = [],
      symbols = ['BTCUSDT', 'ETHUSDT'],
      timeframes = ['1h'],
      model = 'gpt-4o',
      eliminationPct = 50,
      imagesPhase1 = 10,
      imagesPhase2 = 25,
      imagesPhase3 = 50,
      imageOffset = 100,
      selectionStrategy = 'random',
      rankingStrategy = 'wilson',
      randomSymbols = false,
      randomTimeframes = false,
      minTradesForSurvival = 1,  // Require at least 1 trade to survive (0 = disabled)
      holdPenalty = -0.1,        // Penalty per HOLD (opportunity cost)
    } = body;

    const tournamentId = `tournament_${Date.now()}`;
    const pythonDir = path.join(process.cwd(), 'python');
    // Resolve charts path - convert relative path to absolute
    const rawChartsPath = process.env.PYTHON_CHARTS_PATH || '../../data/charts/.backup';
    const chartsDir = path.isAbsolute(rawChartsPath) ? rawChartsPath : path.resolve(process.cwd(), rawChartsPath);
    const dbPath = path.join(process.cwd(), 'data', 'bot.db');

    const state: TournamentState = {
      status: 'running',
      progress: 0,
      currentPhase: 0,
      activePrompts: prompts,
      rankings: [],
      logs: [],
      result: null,
      config: body,
      startedAt: Date.now(),
    };
    runningTournaments.set(tournamentId, state);

    // Python code to run tournament
    const pythonCode = `
import sys
sys.path.insert(0, '${pythonDir}')
import json
from prompt_performance.tournament import PromptTournament, TournamentConfig

def progress(data):
    event = data.get('type', 'info')
    if event == 'phase_start':
        print(f"PROGRESS:{10 + data.get('phase', 0) * 20}:Phase {data.get('phase')} starting - {data.get('prompts')} prompts, {data.get('images')} images", flush=True)
    elif event == 'prompt_complete':
        print(f"PROGRESS:{15 + data.get('phase', 0) * 20}:{data.get('prompt')}: {data.get('win_rate', 0):.1f}% WR, {data.get('avg_pnl', 0):.2f}% PnL", flush=True)
    elif event == 'elimination':
        print(f"PROGRESS:{25 + data.get('phase', 0) * 20}:Eliminated: {', '.join(data.get('eliminated', []))}", flush=True)
        print(f"RANKINGS:" + json.dumps(data.get('rankings', [])), flush=True)
    elif event == 'complete':
        print(f"PROGRESS:95:Tournament complete!", flush=True)
    elif event == 'error':
        print(f"ERROR:{data.get('message', 'Unknown error')}", flush=True)
    elif event == 'info':
        print(f"INFO:{data.get('message', '')}", flush=True)

config = TournamentConfig(
    model='${model}',
    elimination_pct=${eliminationPct},
    images_phase_1=${imagesPhase1},
    images_phase_2=${imagesPhase2},
    images_phase_3=${imagesPhase3},
    image_offset=${imageOffset},
    selection_strategy='${selectionStrategy}',
    ranking_strategy='${rankingStrategy}',
    symbols=${JSON.stringify(symbols)},
    timeframes=${JSON.stringify(timeframes)},
    random_symbols=${randomSymbols ? 'True' : 'False'},
    random_timeframes=${randomTimeframes ? 'True' : 'False'},
    max_workers=5,  # Parallel API calls - respect rate limits
    min_trades_for_survival=${minTradesForSurvival},
    hold_penalty=${holdPenalty}
)

try:
    print("PROGRESS:5:Initializing tournament...", flush=True)
    print(f"INFO:Config: model={config.model}, symbols={config.symbols}, timeframes={config.timeframes}", flush=True)
    print(f"INFO:Random: symbols={config.random_symbols}, timeframes={config.random_timeframes}", flush=True)
    print(f"INFO:Selection: {config.selection_strategy}, Ranking: {config.ranking_strategy}", flush=True)

    tournament = PromptTournament(
        config=config,
        charts_dir='${chartsDir}',
        db_path='${dbPath}',
        progress_callback=progress
    )

    print(f"INFO:Random seed: {tournament._random_seed} (for reproducibility)", flush=True)

    prompts = ${JSON.stringify(prompts)} or None
    print(f"PROGRESS:10:Starting tournament with {len(prompts) if prompts else 'all'} prompts", flush=True)

    result = tournament.run_tournament(prompts)
    print("PROGRESS:100:Complete", flush=True)
    print("RESULT:" + json.dumps(result, default=str), flush=True)
except Exception as e:
    import traceback
    print(f"ERROR:{str(e)}", flush=True)
    print(f"ERROR:Traceback: {traceback.format_exc()}", flush=True)
    sys.exit(1)
`;

    const python = spawn('python3', ['-c', pythonCode], { cwd: pythonDir });
    state.process = python;

    python.stdout.on('data', (data) => {
      const lines = data.toString().split('\n').filter(Boolean);
      for (const line of lines) {
        if (line.startsWith('PROGRESS:')) {
          const parts = line.split(':');
          state.progress = parseInt(parts[1]) || state.progress;
          const msg = parts.slice(2).join(':');
          if (msg) {
            state.logs.push(`[${state.progress}%] ${msg}`);
            if (state.logs.length > 100) state.logs.shift();
          }
        } else if (line.startsWith('RANKINGS:')) {
          try { state.rankings = JSON.parse(line.slice(9)); } catch {}
        } else if (line.startsWith('RESULT:')) {
          try { state.result = JSON.parse(line.slice(7)); state.progress = 100; } catch {}
        } else if (line.startsWith('ERROR:') || line.startsWith('INFO:')) {
          state.logs.push(line);
          if (state.logs.length > 100) state.logs.shift();
        }
      }
    });

    python.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      // Capture all stderr lines for debugging
      for (const line of msg.split('\n')) {
        if (line.trim()) {
          // Mark errors clearly
          if (line.includes('Error') || line.includes('error') || line.includes('Traceback') || line.includes('Exception')) {
            state.logs.push(`❌ ERROR: ${line}`);
          } else if (line.includes('WARNING') || line.includes('Warning')) {
            state.logs.push(`⚠️ ${line}`);
          } else {
            state.logs.push(`[stderr] ${line}`);
          }
          if (state.logs.length > 100) state.logs.shift();
        }
      }
    });

    python.on('close', (code) => {
      state.status = code === 0 ? 'completed' : 'failed';
      if (code !== 0) {
        // Find error messages in logs
        const errorLogs = state.logs.filter(l => l.includes('ERROR') || l.includes('Traceback') || l.includes('Exception'));
        state.logs.push(`❌ Process exited with code ${code}`);
        if (!state.result) {
          state.result = {
            error: errorLogs.length > 0 ? errorLogs.join('\n') : state.logs.slice(-10).join('\n') || 'Unknown error'
          };
        }
      }
    });

    return NextResponse.json({ success: true, tournamentId, message: 'Tournament started' });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Failed to start' }, { status: 500 });
  }
}

// GET - Check tournament status
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const tournamentId = searchParams.get('tournamentId');

  if (!tournamentId) {
    const all: Record<string, { status: string; progress: number }> = {};
    runningTournaments.forEach((state, id) => {
      all[id] = { status: state.status, progress: state.progress };
    });
    return NextResponse.json({ tournaments: all });
  }

  const state = runningTournaments.get(tournamentId);
  if (!state) {
    return NextResponse.json({ error: 'Tournament not found' }, { status: 404 });
  }

  return NextResponse.json({
    tournamentId,
    status: state.status,
    progress: state.progress,
    currentPhase: state.currentPhase,
    activePrompts: state.activePrompts,
    rankings: state.rankings,
    logs: state.logs.slice(-30),
    result: state.result,
    config: state.config,
    startedAt: state.startedAt,
  });
}

// DELETE - Cancel tournament
export async function DELETE(request: Request) {
  const { searchParams } = new URL(request.url);
  const tournamentId = searchParams.get('tournamentId');

  if (!tournamentId) {
    return NextResponse.json({ error: 'Missing tournamentId' }, { status: 400 });
  }

  const state = runningTournaments.get(tournamentId);
  if (!state) {
    return NextResponse.json({ error: 'Tournament not found' }, { status: 404 });
  }

  if (state.process) {
    state.process.kill('SIGTERM');
  }
  state.status = 'cancelled';

  return NextResponse.json({ success: true, message: 'Tournament cancelled' });
}


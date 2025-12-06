/**
 * Bot Control API - POST start/stop/kill commands
 *
 * This spawns/kills the Python trading bot process
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { processMonitor } from '@/lib/ws/process-monitor';
import { emitLog } from '@/lib/ws/socket-server';
import {
  saveProcessState,
  removeProcessState,
  getAllProcessStates,
  restoreProcessStates,
  isProcessAlive
} from '@/lib/process-state';

// Store running bot process (global for this instance)
// Note: This is in-memory and will be lost on server restart
// We use process-state.ts for persistence
let botProcess: ChildProcess | null = null;
let botStartedAt: number | null = null;
let botLogs: string[] = [];
let botPid: number | null = null;

export interface ControlRequest {
  action: 'start' | 'stop' | 'kill' | 'status';
  paper_trading?: boolean;
  testnet?: boolean;
  instance_id?: string;
}

export interface ControlResponse {
  success: boolean;
  running: boolean;
  message: string;
  uptime_seconds?: number;
  logs?: string[];
  pid?: number | null;
  instance_id?: string;
}

// Track which instance is currently running
let currentInstanceId: string | null = null;

// Restore process states on module load (server startup)
let restoredOnStartup = false;
function restoreOnStartup() {
  if (restoredOnStartup) return;
  restoredOnStartup = true;

  console.log('[BOT CONTROL] Restoring process states from disk...');
  const restored = restoreProcessStates();

  if (restored.length > 0) {
    console.log(`[BOT CONTROL] Found ${restored.length} running process(es)`);
    // Register with process monitor
    for (const state of restored) {
      processMonitor.registerProcess(state.instanceId, state.pid);
      console.log(`[BOT CONTROL] Restored: instance=${state.instanceId}, PID=${state.pid}`);
    }
  } else {
    console.log('[BOT CONTROL] No running processes to restore');
  }
}

/**
 * GET /api/bot/control - Get bot running status
 */
export async function GET() {
  restoreOnStartup();
  return getBotStatus();
}

/**
 * POST /api/bot/control - Start, stop, or kill the bot
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json() as ControlRequest;
    const { action, paper_trading = true, testnet = false, instance_id } = body;

    console.log(`[BOT CONTROL] Action: ${action}, paper_trading: ${paper_trading}, testnet: ${testnet}, instance_id: ${instance_id}`);

    switch (action) {
      case 'start':
        return startBot(paper_trading, testnet, instance_id);
      case 'stop':
        return stopBot();
      case 'kill':
        return killBot();
      case 'status':
        return getBotStatus();
      default:
        return NextResponse.json(
          { error: `Invalid action: ${action}. Use 'start', 'stop', 'kill', or 'status'` },
          { status: 400 }
        );
    }
  } catch (error) {
    console.error('Control POST error:', error);
    return NextResponse.json(
      { error: 'Failed to execute control command' },
      { status: 500 }
    );
  }
}

function startBot(paperTrading: boolean, testnet: boolean, instanceId?: string): Response {
  // Instance ID is now required
  if (!instanceId) {
    return NextResponse.json({
      success: false,
      running: false,
      message: 'instance_id is required. Select an instance first.',
    }, { status: 400 });
  }

  // Check if process is actually running
  const isActuallyRunning = botProcess !== null && !botProcess.killed && botProcess.pid;

  if (isActuallyRunning) {
    return NextResponse.json({
      success: false,
      running: true,
      message: 'Bot is already running',
      uptime_seconds: botStartedAt ? Math.floor((Date.now() - botStartedAt) / 1000) : 0,
      pid: botPid,
      instance_id: currentInstanceId,
    });
  }

  const pythonDir = path.join(process.cwd(), 'python');
  const args = ['run_bot.py', '--instance', instanceId];
  currentInstanceId = instanceId;

  if (!paperTrading) {
    args.push('--live');
  }
  if (testnet) {
    args.push('--testnet');
  }

  console.log(`[BOT CONTROL] Starting bot in ${pythonDir} with args: ${args.join(' ')}`);

  botLogs = [];
  botLogs.push(`[${new Date().toISOString()}] Starting bot...`);
  botStartedAt = Date.now();

  try {
    botProcess = spawn('python3', args, {
      cwd: pythonDir,
      env: { ...process.env },
      detached: false,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    botPid = botProcess.pid || null;
    console.log(`[BOT CONTROL] Bot process started with PID: ${botPid}`);
    botLogs.push(`[${new Date().toISOString()}] Bot process started with PID: ${botPid}`);

    // Register with process monitor for status tracking
    if (botPid && instanceId) {
      processMonitor.registerProcess(instanceId, botPid);

      // Save to persistent state
      saveProcessState(instanceId, {
        pid: botPid,
        instanceId,
        startedAt: botStartedAt,
        paperTrading,
        testnet
      });
    }

    botProcess.stdout?.on('data', (data) => {
      const lines: string[] = data.toString().split('\n').filter((l: string) => l.trim());
      console.log('[BOT STDOUT]', lines.join('\n'));
      botLogs.push(...lines);
      // Emit logs to connected clients in real-time
      lines.forEach((line: string) => emitLog(line, instanceId));
      // Keep only last 500 log lines
      if (botLogs.length > 500) {
        botLogs = botLogs.slice(-500);
      }
    });

    // Note: Python logging outputs to stderr by default, so don't prefix with [ERR]
    botProcess.stderr?.on('data', (data) => {
      const lines: string[] = data.toString().split('\n').filter((l: string) => l.trim());
      console.log('[BOT STDERR]', lines.join('\n'));
      // Don't prefix - the log level is already in the message (| INFO |, | WARNING |, etc)
      botLogs.push(...lines);
      // Emit logs to connected clients in real-time
      lines.forEach((line: string) => emitLog(line, instanceId));
      if (botLogs.length > 500) {
        botLogs = botLogs.slice(-500);
      }
    });

    botProcess.on('error', (err) => {
      console.error('[BOT CONTROL] Process error:', err);
      botLogs.push(`[ERROR] Process error: ${err.message}`);
    });

    botProcess.on('close', (code, signal) => {
      const timestamp = new Date().toISOString();
      const msg = `[${timestamp}] Bot process exited with code ${code}, signal ${signal}`;
      console.log('[BOT CONTROL]', msg);
      botLogs.push(msg);

      // Remove from persistent state
      if (currentInstanceId) {
        removeProcessState(currentInstanceId);
      }

      // Note: Don't unregister here - the process monitor will detect the dead process
      // and emit the status update. This ensures consistent handling.

      botProcess = null;
      botStartedAt = null;
      botPid = null;
      currentInstanceId = null;
    });

    return NextResponse.json({
      success: true,
      running: true,
      message: `Bot started in ${paperTrading ? 'paper' : 'live'} trading mode on ${testnet ? 'testnet' : 'mainnet'}`,
      pid: botPid,
      logs: botLogs.slice(-20),
    });
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error('[BOT CONTROL] Failed to start bot:', errorMsg);
    botLogs.push(`[ERROR] Failed to start: ${errorMsg}`);
    return NextResponse.json({
      success: false,
      running: false,
      message: `Failed to start bot: ${errorMsg}`,
      logs: botLogs.slice(-20),
    }, { status: 500 });
  }
}

function stopBot(): Response {
  if (!botProcess || botProcess.killed) {
    // Clean up state if somehow stale
    botProcess = null;
    botStartedAt = null;
    botPid = null;
    currentInstanceId = null;

    return NextResponse.json({
      success: true,
      running: false,
      message: 'Bot is not running',
      logs: botLogs.slice(-20),
    });
  }

  console.log(`[BOT CONTROL] Sending SIGTERM to bot (PID: ${botPid})`);
  botLogs.push(`[${new Date().toISOString()}] Stopping bot gracefully (SIGTERM)...`);

  // Unregister from process monitor (graceful stop)
  if (currentInstanceId) {
    processMonitor.unregisterProcess(currentInstanceId, 'stopped');
    // Remove from persistent state
    removeProcessState(currentInstanceId);
  }

  const stoppedInstanceId = currentInstanceId;

  botProcess.kill('SIGTERM');

  // Clean up state immediately so UI updates
  const processRef = botProcess;
  botProcess = null;
  botStartedAt = null;
  botPid = null;
  currentInstanceId = null;

  // Force kill after 10 seconds if process still running
  setTimeout(() => {
    if (processRef && !processRef.killed) {
      console.log('[BOT CONTROL] Force killing bot with SIGKILL');
      botLogs.push(`[${new Date().toISOString()}] Force killing bot (SIGKILL)...`);
      processRef.kill('SIGKILL');
    }
  }, 10000);

  return NextResponse.json({
    success: true,
    running: false,
    message: 'Stop signal sent to bot (graceful shutdown)',
    logs: botLogs.slice(-20),
    instance_id: stoppedInstanceId,
  });
}

function killBot(): Response {
  if (!botProcess || botProcess.killed) {
    return NextResponse.json({
      success: true,
      running: false,
      message: 'Bot is not running',
      logs: botLogs.slice(-20),
    });
  }

  console.log(`[BOT CONTROL] KILL SWITCH - Sending SIGKILL to bot (PID: ${botPid})`);
  botLogs.push(`[${new Date().toISOString()}] ⚠️ KILL SWITCH - Immediate termination (SIGKILL)!`);

  // Unregister from process monitor (kill)
  if (currentInstanceId) {
    processMonitor.unregisterProcess(currentInstanceId, 'killed');
    // Remove from persistent state
    removeProcessState(currentInstanceId);
  }

  // Immediately kill with SIGKILL
  botProcess.kill('SIGKILL');

  // Clean up state immediately
  botProcess = null;
  botStartedAt = null;
  botPid = null;
  currentInstanceId = null;

  return NextResponse.json({
    success: true,
    running: false,
    message: '⚠️ Bot killed immediately (SIGKILL)',
    logs: botLogs.slice(-20),
  });
}

function getBotStatus(): Response {
  // Check in-memory state first
  let running = botProcess !== null && !botProcess.killed;
  let pid = botPid;
  let instanceId = currentInstanceId;
  let startedAt = botStartedAt;

  // If no in-memory state, check persistent state (handles server restart)
  if (!running) {
    const allStates = getAllProcessStates();
    if (allStates.length > 0) {
      // Take the first running process (in future we'll support multiple)
      const state = allStates[0];
      if (isProcessAlive(state.pid)) {
        running = true;
        pid = state.pid;
        instanceId = state.instanceId;
        startedAt = state.startedAt;
        console.log(`[BOT CONTROL] Detected running process from persistent state: instance=${instanceId}, PID=${pid}`);
      }
    }
  }

  return NextResponse.json({
    success: true,
    running,
    message: running ? 'Bot is running' : 'Bot is not running',
    uptime_seconds: running && startedAt ? Math.floor((Date.now() - startedAt) / 1000) : undefined,
    logs: botLogs.slice(-50),
    pid,
    instance_id: running ? instanceId : undefined,
  });
}


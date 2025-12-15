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
  getProcessState,
  restoreProcessStates,
  isProcessAlive
} from '@/lib/process-state';
import { updateRunStatusByInstanceId } from '@/lib/db/trading-db';

// MULTI-INSTANCE SUPPORT: Store running bot processes by instance_id
// Note: This is in-memory and will be lost on server restart
// We use process-state.ts for persistence
const botProcesses: Map<string, ChildProcess> = new Map();
const botStartTimes: Map<string, number> = new Map();
const botLogs: Map<string, string[]> = new Map();
const botPids: Map<string, number> = new Map();
const forceKillTimeouts: Map<string, NodeJS.Timeout> = new Map();

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

// Helper function to get logs for an instance (initialize if needed)
function getInstanceLogs(instanceId: string): string[] {
  if (!botLogs.has(instanceId)) {
    botLogs.set(instanceId, []);
  }
  return botLogs.get(instanceId)!;
}

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
 * Query params: instance_id (optional) - if provided, returns status for that instance
 */
export async function GET(request: NextRequest) {
  restoreOnStartup();
  const { searchParams } = new URL(request.url);
  const instanceId = searchParams.get('instance_id');
  return getBotStatus(instanceId || undefined);
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
        return stopBot(instance_id);
      case 'kill':
        return killBot(instance_id);
      case 'status':
        return getBotStatus(instance_id);
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

  // MULTI-INSTANCE: Check if THIS specific instance is already running
  const existingProcess = botProcesses.get(instanceId);
  const isActuallyRunning = existingProcess && !existingProcess.killed && existingProcess.pid;

  if (isActuallyRunning) {
    const startedAt = botStartTimes.get(instanceId);
    const pid = botPids.get(instanceId);
    return NextResponse.json({
      success: false,
      running: true,
      message: `Instance '${instanceId}' is already running`,
      uptime_seconds: startedAt ? Math.floor((Date.now() - startedAt) / 1000) : 0,
      pid: pid,
      instance_id: instanceId,
    });
  }

  const pythonDir = path.join(process.cwd(), 'python');
  const args = ['run_bot.py', '--instance', instanceId];

  if (!paperTrading) {
    args.push('--live');
  }
  if (testnet) {
    args.push('--testnet');
  }

  console.log(`[BOT CONTROL] Starting bot in ${pythonDir} with args: ${args.join(' ')}`);

  // MULTI-INSTANCE: Initialize logs for this instance
  const logs = getInstanceLogs(instanceId);
  logs.length = 0; // Clear previous logs
  logs.push(`[${new Date().toISOString()}] Starting bot...`);
  const startedAt = Date.now();
  botStartTimes.set(instanceId, startedAt);

  try {
    // Log the command being executed for debugging
    console.log(`[BOT CONTROL] Starting bot with command: python3 ${args.join(' ')}`);
    console.log(`[BOT CONTROL] Working directory: ${pythonDir}`);

    const botProcess = spawn('python3', args, {
      cwd: pythonDir,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',  // Force unbuffered output for real-time logs
      },
      detached: false,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const pid = botProcess.pid || null;
    const startMessage = `Bot process started with PID: ${pid}`;
    console.log(`[BOT CONTROL] ${startMessage}`);
    logs.push(`[${new Date().toISOString()}] ${startMessage}`);

    // MULTI-INSTANCE: Store process info
    botProcesses.set(instanceId, botProcess);
    if (pid) botPids.set(instanceId, pid);

    // Register with process monitor for status tracking
    if (pid && instanceId) {
      processMonitor.registerProcess(instanceId, pid);

      // Save to persistent state
      saveProcessState(instanceId, {
        pid: pid,
        instanceId,
        startedAt: startedAt,
        paperTrading,
        testnet
      });
    }

    botProcess.stdout?.on('data', (data) => {
      const lines: string[] = data.toString().split('\n').filter((l: string) => l.trim());
      // Log each line individually to Railway logs for better visibility
      lines.forEach((line: string) => {
        console.log(`[BOT STDOUT] [${instanceId}] ${line}`);
      });
      logs.push(...lines);
      // Emit logs to connected clients in real-time
      lines.forEach((line: string) => emitLog(line, instanceId));
      // Keep only last 2000 log lines (increased from 500 to preserve STEP_0-3 logs)
      if (logs.length > 2000) {
        const trimmed = logs.slice(-2000);
        logs.length = 0;
        logs.push(...trimmed);
      }
    });

    // Note: Python logging outputs to stderr by default, so don't prefix with [ERR]
    botProcess.stderr?.on('data', (data) => {
      const lines: string[] = data.toString().split('\n').filter((l: string) => l.trim());
      // Log each line individually to Railway logs for better visibility
      lines.forEach((line: string) => {
        console.log(`[BOT STDERR] [${instanceId}] ${line}`);
      });
      // Don't prefix - the log level is already in the message (| INFO |, | WARNING |, etc)
      logs.push(...lines);
      // Emit logs to connected clients in real-time
      lines.forEach((line: string) => emitLog(line, instanceId));
      // Keep only last 2000 log lines (increased from 500 to preserve STEP_0-3 logs)
      if (logs.length > 2000) {
        const trimmed = logs.slice(-2000);
        logs.length = 0;
        logs.push(...trimmed);
      }
    });

    botProcess.on('error', (err) => {
      const errorMsg = `Process error: ${err.message}`;
      console.error(`[BOT CONTROL] [${instanceId}] ${errorMsg}`);
      logs.push(`[ERROR] ${errorMsg}`);
    });

    botProcess.on('close', (code, signal) => {
      const timestamp = new Date().toISOString();
      const msg = `Bot process exited with code ${code}, signal ${signal}`;
      console.log(`[BOT CONTROL] [${instanceId}] [${timestamp}] ${msg}`);
      logs.push(`[${timestamp}] ${msg}`);

      // MULTI-INSTANCE: Remove this instance's state
      console.log(`[BOT CONTROL] Removing process state for instance: ${instanceId}`);
      removeProcessState(instanceId);

      // Note: Don't unregister here - the process monitor will detect the dead process
      // and emit the status update. This ensures consistent handling.

      // MULTI-INSTANCE: Clean up this instance's data
      botProcesses.delete(instanceId);
      botStartTimes.delete(instanceId);
      botPids.delete(instanceId);
    });

    return NextResponse.json({
      success: true,
      running: true,
      message: `Bot started in ${paperTrading ? 'paper' : 'live'} trading mode on ${testnet ? 'testnet' : 'mainnet'}`,
      pid: pid,
      instance_id: instanceId,
      logs: logs.slice(-20),
    });
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error(`[BOT CONTROL] [${instanceId}] Failed to start bot:`, errorMsg);
    logs.push(`[ERROR] Failed to start: ${errorMsg}`);
    return NextResponse.json({
      success: false,
      running: false,
      message: `Failed to start bot: ${errorMsg}`,
      logs: logs.slice(-20),
    }, { status: 500 });
  }
}

function stopBot(instanceId?: string): Response {
  // MULTI-INSTANCE: Instance ID is required
  if (!instanceId) {
    return NextResponse.json({
      success: false,
      running: false,
      message: 'instance_id is required to stop a bot',
    }, { status: 400 });
  }

  const botProcess = botProcesses.get(instanceId);
  const logs = getInstanceLogs(instanceId);

  // If no in-memory reference, check persistent state (handles server restart case)
  if (!botProcess || botProcess.killed) {
    const persistentState = getProcessState(instanceId);

    if (persistentState && isProcessAlive(persistentState.pid)) {
      // Process is running but we lost the reference after server restart
      // Kill by PID directly
      const pid = persistentState.pid;
      console.log(`[BOT CONTROL] [${instanceId}] Stopping orphaned process by PID: ${pid}`);
      logs.push(`[${new Date().toISOString()}] Stopping orphaned bot process (SIGTERM to PID ${pid})...`);

      try {
        process.kill(pid, 'SIGTERM');

        // Set up force kill after 10 seconds
        setTimeout(() => {
          if (isProcessAlive(pid)) {
            console.log(`[BOT CONTROL] [${instanceId}] Force killing orphaned process: ${pid}`);
            try {
              process.kill(pid, 'SIGKILL');
            } catch (e) {
              // Process may have already exited
            }
          }
        }, 10000);
      } catch (e) {
        console.error(`[BOT CONTROL] Failed to stop process ${pid}:`, e);
      }

      // Unregister and clean up
      processMonitor.unregisterProcess(instanceId, 'stopped');
      removeProcessState(instanceId);
      updateRunStatusByInstanceId(instanceId, 'stopped', 'user_stop')
        .catch(err => console.error(`[BOT CONTROL] Failed to update run status: ${err.message}`));

      return NextResponse.json({
        success: true,
        running: false,
        message: `Stop signal sent to orphaned bot (PID: ${pid})`,
        logs: logs.slice(-20),
        instance_id: instanceId,
      });
    }

    // Clean up state if somehow stale
    botProcesses.delete(instanceId);
    botStartTimes.delete(instanceId);
    botPids.delete(instanceId);

    // Clear any pending force kill timeout
    const timeout = forceKillTimeouts.get(instanceId);
    if (timeout) {
      clearTimeout(timeout);
      forceKillTimeouts.delete(instanceId);
    }

    return NextResponse.json({
      success: true,
      running: false,
      message: `Instance '${instanceId}' is not running`,
      logs: logs.slice(-20),
    });
  }

  const pid = botPids.get(instanceId);
  console.log(`[BOT CONTROL] [${instanceId}] Sending SIGTERM to bot (PID: ${pid})`);
  logs.push(`[${new Date().toISOString()}] Stopping bot gracefully (SIGTERM)...`);

  // Unregister from process monitor (graceful stop)
  processMonitor.unregisterProcess(instanceId, 'stopped');
  // Remove from persistent state
  removeProcessState(instanceId);

  // Update run status in database
  updateRunStatusByInstanceId(instanceId, 'stopped', 'user_stop')
    .catch(err => console.error(`[BOT CONTROL] Failed to update run status: ${err.message}`));

  botProcess.kill('SIGTERM');

  // Clean up state immediately so UI updates
  const processRef = botProcess;
  botProcesses.delete(instanceId);
  botStartTimes.delete(instanceId);
  botPids.delete(instanceId);

  // Clear any existing force kill timeout
  const existingTimeout = forceKillTimeouts.get(instanceId);
  if (existingTimeout) {
    clearTimeout(existingTimeout);
    forceKillTimeouts.delete(instanceId);
  }

  // Set up cleanup handler for graceful exit
  const exitHandler = () => {
    const timeout = forceKillTimeouts.get(instanceId);
    if (timeout) {
      clearTimeout(timeout);
      forceKillTimeouts.delete(instanceId);
    }
  };
  processRef.once('exit', exitHandler);

  // Force kill after 10 seconds if process still running
  const timeout = setTimeout(() => {
    if (processRef && !processRef.killed) {
      console.log(`[BOT CONTROL] [${instanceId}] Force killing bot with SIGKILL`);
      logs.push(`[${new Date().toISOString()}] Force killing bot (SIGKILL)...`);
      processRef.kill('SIGKILL');
    }
    forceKillTimeouts.delete(instanceId);
  }, 10000);
  forceKillTimeouts.set(instanceId, timeout);

  return NextResponse.json({
    success: true,
    running: false,
    message: 'Stop signal sent to bot (graceful shutdown)',
    logs: logs.slice(-20),
    instance_id: instanceId,
  });
}

function killBot(instanceId?: string): Response {
  // MULTI-INSTANCE: Instance ID is required
  if (!instanceId) {
    return NextResponse.json({
      success: false,
      running: false,
      message: 'instance_id is required to kill a bot',
    }, { status: 400 });
  }

  const botProcess = botProcesses.get(instanceId);
  const logs = getInstanceLogs(instanceId);

  // If no in-memory reference, check persistent state (handles server restart case)
  if (!botProcess || botProcess.killed) {
    const persistentState = getProcessState(instanceId);

    if (persistentState && isProcessAlive(persistentState.pid)) {
      // Process is running but we lost the reference after server restart
      // Kill by PID directly with SIGKILL
      const pid = persistentState.pid;
      console.log(`[BOT CONTROL] [${instanceId}] KILL SWITCH - Killing orphaned process by PID: ${pid}`);
      logs.push(`[${new Date().toISOString()}] ⚠️ KILL SWITCH - Immediate termination of orphaned process (PID ${pid})!`);

      try {
        process.kill(pid, 'SIGKILL');
      } catch (e) {
        console.error(`[BOT CONTROL] Failed to kill process ${pid}:`, e);
      }

      // Unregister and clean up
      processMonitor.unregisterProcess(instanceId, 'killed');
      removeProcessState(instanceId);
      updateRunStatusByInstanceId(instanceId, 'crashed', 'user_kill')
        .catch(err => console.error(`[BOT CONTROL] Failed to update run status: ${err.message}`));

      return NextResponse.json({
        success: true,
        running: false,
        message: `⚠️ Orphaned bot killed immediately (PID: ${pid})`,
        instance_id: instanceId,
        logs: logs.slice(-20),
      });
    }

    // Clear any pending force kill timeout
    const timeout = forceKillTimeouts.get(instanceId);
    if (timeout) {
      clearTimeout(timeout);
      forceKillTimeouts.delete(instanceId);
    }

    return NextResponse.json({
      success: true,
      running: false,
      message: `Instance '${instanceId}' is not running`,
      logs: logs.slice(-20),
    });
  }

  const pid = botPids.get(instanceId);
  console.log(`[BOT CONTROL] [${instanceId}] KILL SWITCH - Sending SIGKILL to bot (PID: ${pid})`);
  logs.push(`[${new Date().toISOString()}] ⚠️ KILL SWITCH - Immediate termination (SIGKILL)!`);

  // Unregister from process monitor (kill)
  processMonitor.unregisterProcess(instanceId, 'killed');
  // Remove from persistent state
  removeProcessState(instanceId);

  // Update run status in database
  updateRunStatusByInstanceId(instanceId, 'crashed', 'user_kill')
    .catch(err => console.error(`[BOT CONTROL] Failed to update run status: ${err.message}`));

  // Immediately kill with SIGKILL
  botProcess.kill('SIGKILL');

  // Clean up state immediately
  botProcesses.delete(instanceId);
  botStartTimes.delete(instanceId);
  botPids.delete(instanceId);

  // Clear any pending force kill timeout
  const timeout = forceKillTimeouts.get(instanceId);
  if (timeout) {
    clearTimeout(timeout);
    forceKillTimeouts.delete(instanceId);
  }

  return NextResponse.json({
    success: true,
    running: false,
    message: '⚠️ Bot killed immediately (SIGKILL)',
    instance_id: instanceId,
    logs: logs.slice(-20),
  });
}

function getBotStatus(instanceId?: string): Response {
  // MULTI-INSTANCE: If instanceId provided, return status for that instance
  if (instanceId) {
    return getSingleInstanceStatus(instanceId);
  }

  // MULTI-INSTANCE: Return status for all instances
  return getAllInstancesStatus();
}

function getSingleInstanceStatus(instanceId: string): Response {
  // Check in-memory state first
  const botProcess = botProcesses.get(instanceId);
  let running = botProcess !== undefined && botProcess !== null && !botProcess.killed;
  let pid = botPids.get(instanceId);
  let startedAt = botStartTimes.get(instanceId);
  const logs = getInstanceLogs(instanceId);

  // If no in-memory state, check persistent state (handles server restart)
  if (!running) {
    const allStates = getAllProcessStates();
    const state = allStates.find(s => s.instanceId === instanceId);

    if (state && isProcessAlive(state.pid)) {
      running = true;
      pid = state.pid;
      startedAt = state.startedAt;
      console.log(`[BOT CONTROL] Detected running process from persistent state: instance=${instanceId}, PID=${pid}`);

      // Add a note to logs that we recovered the process
      if (logs.length === 0) {
        logs.push(`[${new Date().toISOString()}] ℹ️ Bot process recovered after server restart (PID: ${pid})`);
        logs.push(`[${new Date().toISOString()}] ℹ️ Previous logs are not available. New logs will appear as the bot runs.`);
      }
    }
  }

  return NextResponse.json({
    success: true,
    running,
    message: running ? `Instance '${instanceId}' is running` : `Instance '${instanceId}' is not running`,
    uptime_seconds: running && startedAt ? Math.floor((Date.now() - startedAt) / 1000) : undefined,
    logs: logs.slice(-2000),
    pid,
    instance_id: instanceId,
  });
}

function getAllInstancesStatus(): Response {
  // MULTI-INSTANCE: Collect status for all instances
  const instances: Array<{
    instance_id: string;
    running: boolean;
    pid?: number;
    uptime_seconds?: number;
  }> = [];

  // Check in-memory processes
  for (const [instanceId, process] of botProcesses.entries()) {
    const running = process && !process.killed;
    const pid = botPids.get(instanceId);
    const startedAt = botStartTimes.get(instanceId);

    instances.push({
      instance_id: instanceId,
      running,
      pid,
      uptime_seconds: running && startedAt ? Math.floor((Date.now() - startedAt) / 1000) : undefined,
    });
  }

  // Check persistent state for instances not in memory (after server restart)
  const allStates = getAllProcessStates();
  for (const state of allStates) {
    // Skip if already in memory
    if (botProcesses.has(state.instanceId)) continue;

    if (isProcessAlive(state.pid)) {
      instances.push({
        instance_id: state.instanceId,
        running: true,
        pid: state.pid,
        uptime_seconds: Math.floor((Date.now() - state.startedAt) / 1000),
      });
    }
  }

  const runningCount = instances.filter(i => i.running).length;

  return NextResponse.json({
    success: true,
    running: runningCount > 0,
    message: runningCount > 0
      ? `${runningCount} instance(s) running`
      : 'No instances running',
    instances,
  });
}


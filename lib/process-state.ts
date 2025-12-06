/**
 * Persistent Process State Manager
 * 
 * Stores bot process state (PID, instance_id) in a JSON file
 * so it survives Next.js server restarts.
 */

import fs from 'fs';
import path from 'path';

const STATE_FILE = path.join(process.cwd(), 'data', 'process_state.json');

export interface ProcessState {
  pid: number;
  instanceId: string;
  startedAt: number;
  paperTrading: boolean;
  testnet: boolean;
}

interface StateFile {
  processes: Record<string, ProcessState>; // keyed by instanceId
  lastUpdated: string;
}

/**
 * Ensure the state file directory exists
 */
function ensureStateDir(): void {
  const dir = path.dirname(STATE_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

/**
 * Read state from file
 */
function readState(): StateFile {
  try {
    ensureStateDir();
    if (fs.existsSync(STATE_FILE)) {
      const content = fs.readFileSync(STATE_FILE, 'utf-8');
      return JSON.parse(content);
    }
  } catch (error) {
    console.error('[ProcessState] Error reading state file:', error);
  }
  return { processes: {}, lastUpdated: new Date().toISOString() };
}

/**
 * Write state to file
 */
function writeState(state: StateFile): void {
  try {
    ensureStateDir();
    state.lastUpdated = new Date().toISOString();
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  } catch (error) {
    console.error('[ProcessState] Error writing state file:', error);
  }
}

/**
 * Check if a process is alive
 */
export function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Save process state
 */
export function saveProcessState(instanceId: string, processState: ProcessState): void {
  const state = readState();
  state.processes[instanceId] = processState;
  writeState(state);
  console.log(`[ProcessState] Saved state for instance ${instanceId}, PID ${processState.pid}`);
}

/**
 * Remove process state
 */
export function removeProcessState(instanceId: string): void {
  const state = readState();
  delete state.processes[instanceId];
  writeState(state);
  console.log(`[ProcessState] Removed state for instance ${instanceId}`);
}

/**
 * Get process state for a specific instance
 */
export function getProcessState(instanceId: string): ProcessState | null {
  const state = readState();
  return state.processes[instanceId] || null;
}

/**
 * Get all process states
 */
export function getAllProcessStates(): ProcessState[] {
  const state = readState();
  return Object.values(state.processes);
}

/**
 * Restore process states on server startup
 * Returns only processes that are still alive
 */
export function restoreProcessStates(): ProcessState[] {
  const state = readState();
  const alive: ProcessState[] = [];
  const dead: string[] = [];

  for (const [instanceId, processState] of Object.entries(state.processes)) {
    if (isProcessAlive(processState.pid)) {
      alive.push(processState);
      console.log(`[ProcessState] Restored running process: instance=${instanceId}, PID=${processState.pid}`);
    } else {
      dead.push(instanceId);
      console.log(`[ProcessState] Process no longer alive: instance=${instanceId}, PID=${processState.pid}`);
    }
  }

  // Clean up dead processes
  if (dead.length > 0) {
    for (const instanceId of dead) {
      delete state.processes[instanceId];
    }
    writeState(state);
  }

  return alive;
}

/**
 * Clear all process states (for cleanup/reset)
 */
export function clearAllProcessStates(): void {
  writeState({ processes: {}, lastUpdated: new Date().toISOString() });
  console.log('[ProcessState] Cleared all process states');
}


/**
 * Process Monitor Service
 *
 * Tracks running bot processes by PID and instance_id.
 * Periodically checks if processes are alive using OS-level process checking.
 * Updates database and emits WebSocket events when process status changes.
 * Supports multiple parallel running instances.
 */

import { EventEmitter } from 'events';

export interface TrackedProcess {
  pid: number;
  instanceId: string;
  startedAt: number;
  lastCheck: number;
  isAlive: boolean;
}

export interface ProcessStatusUpdate {
  instanceId: string;
  pid: number;
  isAlive: boolean;
  reason?: 'crashed' | 'stopped' | 'killed';
}

class ProcessMonitor extends EventEmitter {
  private processes: Map<string, TrackedProcess> = new Map(); // keyed by instanceId
  private checkInterval: NodeJS.Timeout | null = null;
  private readonly CHECK_INTERVAL_MS = 2000; // Check every 2 seconds

  constructor() {
    super();
  }

  /**
   * Start monitoring processes
   */
  start(): void {
    if (this.checkInterval) return;

    console.log('[ProcessMonitor] Starting process monitor service');
    this.checkInterval = setInterval(() => this.checkAllProcesses(), this.CHECK_INTERVAL_MS);
  }

  /**
   * Stop monitoring
   */
  stop(): void {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
      this.checkInterval = null;
      console.log('[ProcessMonitor] Stopped process monitor service');
    }
  }

  /**
   * Register a new process to track (run_id will be looked up from DB when needed)
   */
  registerProcess(instanceId: string, pid: number): void {
    const tracked: TrackedProcess = {
      pid,
      instanceId,
      startedAt: Date.now(),
      lastCheck: Date.now(),
      isAlive: true
    };

    this.processes.set(instanceId, tracked);
    console.log(`[ProcessMonitor] Registered process: instance=${instanceId}, pid=${pid}`);

    // Emit status update
    this.emit('status', {
      instanceId,
      pid,
      isAlive: true
    } as ProcessStatusUpdate);
  }

  /**
   * Unregister a process (when cleanly stopped)
   */
  unregisterProcess(instanceId: string, reason: 'stopped' | 'killed' = 'stopped'): void {
    const tracked = this.processes.get(instanceId);
    if (tracked) {
      console.log(`[ProcessMonitor] Unregistered process: instance=${instanceId}, reason=${reason}`);
      this.emit('status', {
        instanceId: tracked.instanceId,
        pid: tracked.pid,
        isAlive: false,
        reason
      } as ProcessStatusUpdate);
      this.processes.delete(instanceId);
    }
  }

  /**
   * Check if a PID is alive (Linux/Unix)
   */
  private isProcessAlive(pid: number): boolean {
    try {
      // Send signal 0 - doesn't kill the process, just checks if it exists
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Check all tracked processes
   */
  private checkAllProcesses(): void {
    for (const [instanceId, tracked] of this.processes.entries()) {
      const wasAlive = tracked.isAlive;
      tracked.isAlive = this.isProcessAlive(tracked.pid);
      tracked.lastCheck = Date.now();

      // Process died unexpectedly
      if (wasAlive && !tracked.isAlive) {
        console.log(`[ProcessMonitor] Process died: instance=${instanceId}, pid=${tracked.pid}`);

        this.emit('status', {
          instanceId: tracked.instanceId,
          pid: tracked.pid,
          isAlive: false,
          reason: 'crashed'
        } as ProcessStatusUpdate);

        // Remove from tracking
        this.processes.delete(instanceId);
      }
    }
  }

  /**
   * Get status of a specific instance
   */
  getStatus(instanceId: string): TrackedProcess | null {
    return this.processes.get(instanceId) || null;
  }

  /**
   * Get all tracked processes
   */
  getAllProcesses(): TrackedProcess[] {
    return Array.from(this.processes.values());
  }

  /**
   * Get running instance IDs
   */
  getRunningInstanceIds(): string[] {
    return Array.from(this.processes.keys());
  }

  /**
   * Check if a specific instance is actually running (process alive)
   */
  isInstanceRunning(instanceId: string): boolean {
    const tracked = this.processes.get(instanceId);
    if (!tracked) return false;
    return this.isProcessAlive(tracked.pid);
  }
}

// Singleton instance
export const processMonitor = new ProcessMonitor();


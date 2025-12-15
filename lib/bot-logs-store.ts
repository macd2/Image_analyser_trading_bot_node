/**
 * Shared bot logs store module
 * 
 * This module provides access to the in-memory bot logs that are maintained
 * in the control/route.ts file. It allows other API routes to access logs
 * from running bot processes.
 */

// In-memory storage for bot logs per instance
// This is shared across all API routes in the same Node.js process
const botLogs: Map<string, string[]> = new Map();

/**
 * Get logs for a specific instance
 * Initializes empty array if instance doesn't exist yet
 */
export function getInstanceLogs(instanceId: string): string[] {
  if (!botLogs.has(instanceId)) {
    botLogs.set(instanceId, []);
  }
  return botLogs.get(instanceId)!;
}

/**
 * Add logs to a specific instance
 */
export function addInstanceLogs(instanceId: string, logs: string[]): void {
  const existing = getInstanceLogs(instanceId);
  existing.push(...logs);
  
  // Keep only last 2000 log lines to prevent memory issues
  if (existing.length > 2000) {
    const trimmed = existing.slice(-2000);
    existing.length = 0;
    existing.push(...trimmed);
  }
}

/**
 * Clear logs for a specific instance
 */
export function clearInstanceLogs(instanceId: string): void {
  botLogs.delete(instanceId);
}

/**
 * Get the botLogs map for direct access (used by control/route.ts)
 */
export function getBotLogsMap(): Map<string, string[]> {
  return botLogs;
}


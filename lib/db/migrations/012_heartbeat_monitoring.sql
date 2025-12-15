-- Migration: 012_heartbeat_monitoring
-- Created: 2024-12-15
-- Description: Add heartbeat_at column to runs table for reliable process monitoring
-- 
-- Instead of relying on unreliable PID checks, we now use database heartbeats
-- to determine if a bot process is alive. The Python bot updates heartbeat_at
-- after each trading cycle step.

-- Add heartbeat_at column to runs table
ALTER TABLE runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;

-- Create index for efficient heartbeat timeout checks
CREATE INDEX IF NOT EXISTS idx_runs_heartbeat ON runs(heartbeat_at) WHERE status = 'running';

-- Add comment explaining the column
COMMENT ON COLUMN runs.heartbeat_at IS 'Last time the bot updated its heartbeat. Used to detect if process is alive. Timeout: 3 minutes.';


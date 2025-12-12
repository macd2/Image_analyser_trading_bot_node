/**
 * API endpoint for fetching position monitor activity
 * Returns real-time information about what the monitor is doing
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery } from '@/lib/db/trading-db';

export const dynamic = 'force-dynamic';

interface MonitorActivity {
  id: string;
  timestamp: string;
  symbol: string;
  event: string;
  message: string;
  trade_id: string | null;
  run_id: string | null;
}

interface PositionSnapshot {
  symbol: string;
  snapshot_reason: string;
  snapshot_time: string;
  stop_loss: number | null;
  take_profit: number | null;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id');
    const limit = parseInt(searchParams.get('limit') || '20', 10);

    // Get recent monitor activity from error_logs (INFO level)
    // Filter by instance_id via run_id join (proper instance-aware filtering)
    const query = instanceId
      ? `
        SELECT
          el.id,
          el.timestamp,
          el.symbol,
          el.event,
          el.message,
          el.trade_id,
          el.run_id
        FROM error_logs el
        LEFT JOIN runs r ON el.run_id = r.id
        WHERE el.component = 'position_monitor'
          AND el.level = 'INFO'
          AND (r.instance_id = ? OR el.run_id IS NULL)
        ORDER BY el.timestamp DESC
        LIMIT ?
      `
      : `
        SELECT
          id,
          timestamp,
          symbol,
          event,
          message,
          trade_id,
          run_id
        FROM error_logs
        WHERE component = 'position_monitor'
          AND level = 'INFO'
        ORDER BY timestamp DESC
        LIMIT ?
      `;

    const params = instanceId
      ? [instanceId, limit]
      : [limit];

    const activities = await dbQuery<MonitorActivity>(query, params);

    // Get position snapshots for additional context
    const snapshots = await dbQuery<PositionSnapshot>(`
      SELECT
        symbol,
        snapshot_reason,
        snapshot_time,
        stop_loss,
        take_profit
      FROM position_snapshots
      ORDER BY snapshot_time DESC
      LIMIT ?
    `, [limit]);

    return NextResponse.json({
      activities,
      snapshots,
      count: activities.length,
    });
  } catch (error) {
    console.error('Failed to fetch monitor activity:', error);
    return NextResponse.json(
      { error: 'Failed to fetch monitor activity' },
      { status: 500 }
    );
  }
}


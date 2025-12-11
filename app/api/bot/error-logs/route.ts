/**
 * Error Logs API - GET error logs from the database
 */

import { NextRequest, NextResponse } from 'next/server';
import { isTradingDbAvailable, getErrorLogs, getErrorLogsGroupedByRun } from '@/lib/db/trading-db';

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id') || undefined;
    const limit = parseInt(searchParams.get('limit') || '100');
    const groupByRun = searchParams.get('group_by_run') === 'true';

    if (groupByRun) {
      const runs = await getErrorLogsGroupedByRun(limit, instanceId);
      return NextResponse.json({
        runs,
        run_count: runs.length
      });
    }

    const logs = await getErrorLogs(limit, instanceId);

    return NextResponse.json({
      logs,
      count: logs.length
    });
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error('[Error Logs API] Failed to fetch logs:', errorMsg);

    // Return graceful error response with empty logs instead of 500
    // This prevents frontend from breaking when database is temporarily unavailable
    return NextResponse.json({
      logs: [],
      runs: [],
      count: 0,
      run_count: 0,
      error: 'Database temporarily unavailable, showing cached logs',
      status: 'degraded'
    }, { status: 200 });
  }
}


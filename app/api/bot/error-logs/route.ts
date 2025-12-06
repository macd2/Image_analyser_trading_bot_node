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
    console.error('Error logs GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get error logs' },
      { status: 500 }
    );
  }
}


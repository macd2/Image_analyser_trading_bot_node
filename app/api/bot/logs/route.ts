/**
 * Log Trail API - Unified view of all bot activity
 * Supports both flat and hierarchical (instance/run-grouped) views
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getLogTrail,
  getStats,
  getRecentCycles,
  getRecentRecommendations,
  getRecentTrades,
  getRecentExecutions,
  getRuns,
  getRunsWithHierarchy,
  getInstancesWithHierarchy,
  getRunById,
  getCyclesByRunId,
  isTradingDbAvailable
} from '@/lib/db/trading-db';

export async function GET(req: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 });
    }

    const { searchParams } = new URL(req.url);
    const type = searchParams.get('type'); // 'all', 'runs', 'hierarchy', 'instances', 'cycles', 'recommendations', 'trades', 'executions'
    const limit = parseInt(searchParams.get('limit') || '100');
    const runId = searchParams.get('runId'); // Filter by specific run

    // If specific type requested
    if (type && type !== 'all') {
      switch (type) {
        case 'runs':
          // Get list of runs
          return NextResponse.json({
            type: 'runs',
            data: await getRuns(limit),
            stats: await getStats(),
          });
        case 'hierarchy':
          // Get full hierarchical data with instances at Level 0
          // Instance → Runs → Cycles → Recommendations → Trades → Executions
          return NextResponse.json({
            type: 'hierarchy',
            data: await getInstancesWithHierarchy(limit),
            stats: await getStats(),
          });
        case 'instances':
          // Alias for hierarchy (instance-based view)
          return NextResponse.json({
            type: 'instances',
            data: await getInstancesWithHierarchy(limit),
            stats: await getStats(),
          });
        case 'runs_only':
          // Legacy: Get runs without instance grouping
          return NextResponse.json({
            type: 'runs_only',
            data: await getRunsWithHierarchy(limit),
            stats: await getStats(),
          });
        case 'run':
          // Get specific run with its cycles
          if (!runId) {
            return NextResponse.json({ error: 'runId required for type=run' }, { status: 400 });
          }
          const run = await getRunById(runId);
          if (!run) {
            return NextResponse.json({ error: 'Run not found' }, { status: 404 });
          }
          return NextResponse.json({
            type: 'run',
            data: {
              ...run,
              cycles: await getCyclesByRunId(runId),
            },
            stats: await getStats(),
          });
        case 'cycles':
          return NextResponse.json({
            type: 'cycles',
            data: await getRecentCycles(limit),
            stats: await getStats(),
          });
        case 'recommendations':
          return NextResponse.json({
            type: 'recommendations',
            data: await getRecentRecommendations(limit),
            stats: await getStats(),
          });
        case 'trades':
          return NextResponse.json({
            type: 'trades',
            data: await getRecentTrades(limit),
            stats: await getStats(),
          });
        case 'executions':
          return NextResponse.json({
            type: 'executions',
            data: await getRecentExecutions(limit),
            stats: await getStats(),
          });
        default:
          return NextResponse.json({ error: 'Invalid type' }, { status: 400 });
      }
    }

    // Return unified log trail (flat view for backward compatibility)
    return NextResponse.json({
      type: 'all',
      data: await getLogTrail(limit),
      stats: await getStats(),
    });

  } catch (error) {
    console.error('Log trail error:', error);
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}

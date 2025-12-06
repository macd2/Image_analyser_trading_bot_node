/**
 * Paper Trade Simulator API
 * GET /api/bot/simulator - Get simulator stats
 * POST /api/bot/simulator/run - Run simulator on paper trades
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getRecentTrades,
  isTradingDbAvailable
} from '@/lib/db/trading-db';

export interface SimulatorStats {
  total_paper_trades: number;
  pending_fill: number;
  filled: number;
  closed: number;
  total_pnl: number;
  win_rate: number;
  by_instance: Record<string, {
    total: number;
    closed: number;
    pnl: number;
  }>;
}

/**
 * GET /api/bot/simulator - Get simulator statistics
 */
export async function GET(_request: NextRequest) {
  // const { searchParams } = new URL(request.url);
  // const instanceId = searchParams.get('instance_id'); // TODO: filter by instance

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const allTrades = await getRecentTrades(500);

    // Paper trades are those with status in paper_trade, pending_fill, filled (simulation statuses)
    // NOT just dry_run=1, as live instances can also have paper trades
    const paperTrades = allTrades.filter(t =>
      t.status === 'paper_trade' || t.status === 'pending_fill' || t.status === 'filled'
    );

    // Open trades (not yet closed - no pnl)
    const openTrades = paperTrades.filter(t => t.pnl === null);

    // Closed trades (have pnl)
    const closedTrades = allTrades.filter(t =>
      t.pnl !== null && (t.status === 'closed' || t.exit_reason)
    );

    // Calculate stats
    const winning = closedTrades.filter(t => (t.pnl ?? 0) > 0);
    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);

    const stats: SimulatorStats = {
      total_paper_trades: openTrades.length, // Only open paper trades
      pending_fill: openTrades.filter(t => t.status === 'paper_trade' || t.status === 'pending_fill').length,
      filled: openTrades.filter(t => t.status === 'filled').length,
      closed: closedTrades.length,
      total_pnl: Math.round(totalPnl * 100) / 100,
      win_rate: closedTrades.length > 0 ? (winning.length / closedTrades.length) * 100 : 0,
      by_instance: {}
    };

    return NextResponse.json(stats);
  } catch (error) {
    console.error('Simulator stats error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/bot/simulator/run - Trigger simulator run
 */
export async function POST(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const body = await request.json();
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { trade_id: _tradeId, instance_id: _instanceId } = body;

    // TODO: Implement simulator logic
    // This will be called by a background process to simulate paper trades

    return NextResponse.json({
      success: true,
      message: 'Simulator run initiated',
      trades_processed: 0
    });
  } catch (error) {
    console.error('Simulator run error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}


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
  cancelled: number;
  total_pnl: number;
  win_rate: number;
  win_count: number;
  loss_count: number;
  total_trades: number;
  avg_bars_open: number;
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

    // Cancelled trades
    const cancelledTrades = allTrades.filter(t => t.status === 'cancelled');

    // Calculate bars open for each closed trade
    const timeframeMins: Record<string, number> = {
      '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
      '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440, '1D': 1440
    };

    const barsOpenList = closedTrades.map(t => {
      // Use filled_at if available, otherwise use fill_time
      const fillTimestamp = t.filled_at || t.fill_time;
      if (fillTimestamp && t.closed_at && t.timeframe) {
        const filledTime = new Date(fillTimestamp).getTime();
        const closedTime = new Date(t.closed_at).getTime();
        const minutesPerBar = timeframeMins[t.timeframe] || 1;
        const timeDiff = closedTime - filledTime;
        // Only calculate if closed_at is after filled_at
        if (timeDiff > 0) {
          return Math.ceil(timeDiff / (minutesPerBar * 60 * 1000));
        }
      }
      return 0;
    });

    const avgBarsOpen = closedTrades.length > 0
      ? barsOpenList.reduce((sum, bars) => sum + bars, 0) / closedTrades.length
      : 0;

    // Calculate stats
    const winning = closedTrades.filter(t => (t.pnl ?? 0) > 0);
    const losing = closedTrades.filter(t => (t.pnl ?? 0) < 0);
    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);

    const stats: SimulatorStats = {
      total_paper_trades: openTrades.length, // Only open paper trades
      pending_fill: openTrades.filter(t => t.status === 'paper_trade' || t.status === 'pending_fill').length,
      filled: openTrades.filter(t => t.status === 'filled').length,
      closed: closedTrades.length,
      cancelled: cancelledTrades.length,
      total_pnl: Math.round(totalPnl * 100) / 100,
      win_rate: closedTrades.length > 0 ? (winning.length / closedTrades.length) * 100 : 0,
      win_count: winning.length,
      loss_count: losing.length,
      total_trades: closedTrades.length,
      avg_bars_open: Math.round(avgBarsOpen * 100) / 100,
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


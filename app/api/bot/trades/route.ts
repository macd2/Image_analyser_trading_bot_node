/**
 * Bot Trades API - GET trade history
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getRecentTrades,
  getTradesByStatus,
  getTradesGroupedByRun,
  isTradingDbAvailable,
  dbQuery,
  type TradeRow
} from '@/lib/db/trading-db';

export interface TradesResponse {
  trades: TradeRow[];
  stats: {
    total: number;
    winning: number;
    losing: number;
    win_rate: number;
    total_pnl: number;
    avg_pnl_percent: number;
  };
}

/**
 * GET /api/bot/trades - Get trade history
 * Query params:
 *   - limit: number (default: 50)
 *   - status: string (filter by status)
 *   - instance_id: string (filter by instance)
 *   - group_by_run: boolean (group by run and cycle)
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = parseInt(searchParams.get('limit') || '50', 10);
  const status = searchParams.get('status');
  const instanceId = searchParams.get('instance_id');
  const groupByRun = searchParams.get('group_by_run') === 'true';

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Grouped mode - returns trades organized by run > cycle
    if (groupByRun) {
      const runs = await getTradesGroupedByRun(instanceId || undefined, limit);
      const allTrades = runs.flatMap(r => r.cycles.flatMap(c => c.trades));

      const closedTrades = allTrades.filter(t => t.pnl !== null);
      const winning = closedTrades.filter(t => (t.pnl ?? 0) > 0);
      const losing = closedTrades.filter(t => (t.pnl ?? 0) < 0);
      const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);

      return NextResponse.json({
        runs,
        stats: {
          total: allTrades.length,
          winning: winning.length,
          losing: losing.length,
          win_rate: closedTrades.length > 0 ? (winning.length / closedTrades.length) * 100 : 0,
          total_pnl_usd: Math.round(totalPnl * 100) / 100,
        }
      });
    }

    let trades: TradeRow[];

    // Filter by instance if specified
    if (instanceId) {
      trades = await dbQuery<TradeRow>(`
        SELECT
          t.*,
          COALESCE(t.timeframe, r.timeframe) as timeframe,
          COALESCE(t.entry_price, r.entry_price) as entry_price,
          COALESCE(t.stop_loss, r.stop_loss) as stop_loss,
          COALESCE(t.take_profit, r.take_profit) as take_profit
        FROM trades t
        LEFT JOIN recommendations r ON t.recommendation_id = r.id
        JOIN cycles c ON t.cycle_id = c.id
        JOIN runs run ON c.run_id = run.id
        WHERE run.instance_id = ?
        ORDER BY t.created_at DESC
        LIMIT ?
      `, [instanceId, limit]);
    } else if (status) {
      trades = await getTradesByStatus(status);
    } else {
      trades = await getRecentTrades(limit);
    }

    // Calculate stats from closed trades
    const closedTrades = trades.filter(t => t.pnl !== null);
    const winning = closedTrades.filter(t => (t.pnl ?? 0) > 0);
    const losing = closedTrades.filter(t => (t.pnl ?? 0) < 0);

    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl ?? 0), 0);
    const avgPnlPercent = closedTrades.length > 0
      ? closedTrades.reduce((sum, t) => sum + (t.pnl_percent ?? 0), 0) / closedTrades.length
      : 0;

    const stats = {
      total: trades.length,
      winning: winning.length,
      losing: losing.length,
      win_rate: closedTrades.length > 0 ? (winning.length / closedTrades.length) * 100 : 0,
      total_pnl_usd: Math.round(totalPnl * 100) / 100,
      avg_pnl_percent: Math.round(avgPnlPercent * 1000) / 1000,
    };

    return NextResponse.json({ trades, stats });
  } catch (error) {
    console.error('Trades GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get trades' },
      { status: 500 }
    );
  }
}


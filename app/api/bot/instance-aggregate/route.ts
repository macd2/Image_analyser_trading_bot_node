import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db/client';

export interface InstanceAggregateResponse {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
  running_since: string;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id');

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id is required' },
        { status: 400 }
      );
    }

    // Get aggregated stats across all runs for this instance
    // Count actual trades from trades table (more reliable than run aggregates)
    const aggregateResult = await query<{
      total_pnl: number;
      total_wins: number;
      total_losses: number;
      first_run_date: string;
    }>(`
      SELECT
        COALESCE(SUM(t.pnl), 0) as total_pnl,
        COALESCE(SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END), 0) as total_wins,
        COALESCE(SUM(CASE WHEN t.pnl < 0 THEN 1 ELSE 0 END), 0) as total_losses,
        MIN(r.started_at) as first_run_date
      FROM runs r
      LEFT JOIN cycles c ON c.run_id = r.id
      LEFT JOIN trades t ON t.cycle_id = c.id AND t.status NOT IN ('rejected', 'cancelled', 'error')
      WHERE r.instance_id = ?
    `, [instanceId]);

    if (!aggregateResult || aggregateResult.length === 0) {
      return NextResponse.json({
        total_pnl: 0,
        win_rate: 0,
        total_trades: 0,
        running_since: new Date().toISOString(),
      });
    }

    const result = aggregateResult[0];
    const totalWins = Number(result.total_wins) || 0;
    const totalLosses = Number(result.total_losses) || 0;
    const totalTrades = totalWins + totalLosses;
    const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;

    const response: InstanceAggregateResponse = {
      total_pnl: Number(result.total_pnl) || 0,
      win_rate: parseFloat(winRate.toFixed(1)),
      total_trades: totalTrades,
      running_since: result.first_run_date || new Date().toISOString(),
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('[instance-aggregate] Error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch instance aggregate stats' },
      { status: 500 }
    );
  }
}


import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db/trading-db'

interface ClosedTrade {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  take_profit: number;
  quantity: number;
  pnl: number;
  pnl_percent: number;
  exit_reason: string;
  created_at: string;
  filled_at: string | null;
  fill_time: string | null;
  fill_price: number | null;
  closed_at: string;
  timeframe: string;
  instance_name: string;
  run_id: string;
}

export async function GET() {
  try {
    // Get closed paper trades with instance info
    const closedTrades = await dbQuery<ClosedTrade>(`
      SELECT
        t.id,
        t.symbol,
        t.side,
        t.entry_price,
        t.exit_price,
        t.stop_loss,
        t.take_profit,
        t.quantity,
        t.pnl,
        t.pnl_percent,
        t.exit_reason,
        t.created_at,
        t.filled_at,
        t.fill_time,
        t.fill_price,
        t.closed_at,
        COALESCE(t.timeframe, rec.timeframe) as timeframe,
        i.name as instance_name,
        r.id as run_id
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      LEFT JOIN cycles c ON t.cycle_id = c.id
      LEFT JOIN runs r ON c.run_id = r.id
      LEFT JOIN instances i ON r.instance_id = i.id
      WHERE t.status = 'closed'
        AND t.pnl IS NOT NULL
        AND t.exit_reason IN ('tp_hit', 'sl_hit')
      ORDER BY t.closed_at DESC
      LIMIT 50
    `);

    // Calculate summary stats
    const wins = closedTrades.filter((t) => t.pnl > 0).length
    const losses = closedTrades.filter((t) => t.pnl < 0).length
    const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const avgWin = wins > 0
      ? closedTrades.filter((t) => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / wins
      : 0
    const avgLoss = losses > 0
      ? closedTrades.filter((t) => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0) / losses
      : 0

    return NextResponse.json({
      trades: closedTrades,
      stats: {
        total: closedTrades.length,
        wins,
        losses,
        win_rate: closedTrades.length > 0 ? (wins / closedTrades.length * 100) : 0,
        total_pnl: Math.round(totalPnl * 100) / 100,
        avg_win: Math.round(avgWin * 100) / 100,
        avg_loss: Math.round(avgLoss * 100) / 100,
        profit_factor: avgLoss !== 0 ? Math.abs(avgWin / avgLoss) : 0
      }
    })
  } catch (error) {
    console.error('Error fetching closed trades:', error)
    return NextResponse.json(
      { error: 'Failed to fetch closed trades', details: String(error) },
      { status: 500 }
    )
  }
}


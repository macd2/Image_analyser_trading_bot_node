import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db/trading-db'

interface CancelledTrade {
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
    // Get cancelled paper trades (max_bars_exceeded)
    const cancelledTrades = await dbQuery<CancelledTrade>(`
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
      WHERE t.status = 'cancelled'
        AND t.exit_reason = 'max_bars_exceeded'
      ORDER BY t.closed_at DESC
      LIMIT 50
    `);

    // Calculate summary stats
    const wins = cancelledTrades.filter((t) => t.pnl > 0).length
    const losses = cancelledTrades.filter((t) => t.pnl < 0).length
    const totalPnl = cancelledTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)

    return NextResponse.json({
      trades: cancelledTrades,
      stats: {
        total: cancelledTrades.length,
        wins,
        losses,
        total_pnl: Math.round(totalPnl * 100) / 100,
      }
    })
  } catch (error) {
    console.error('Error fetching cancelled trades:', error)
    return NextResponse.json(
      { error: 'Failed to fetch cancelled trades', details: String(error) },
      { status: 500 }
    )
  }
}


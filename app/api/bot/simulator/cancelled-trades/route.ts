import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db/trading-db'

interface CancelledTrade {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number;
  take_profit: number;
  quantity: number;
  pnl: number | null;
  pnl_percent: number | null;
  exit_reason: string;
  created_at: string;
  filled_at: string | null;
  fill_time: string | null;
  fill_price: number | null;
  closed_at: string | null;
  cancelled_at: string | null;
  timeframe: string;
  instance_name: string;
  run_id: string;
  instance_id?: string;
  bars_open?: number;
  dry_run?: number | null;
  position_size_usd?: number;
  risk_amount_usd?: number;
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
        t.cancelled_at,
        COALESCE(t.timeframe, rec.timeframe) as timeframe,
        i.name as instance_name,
        r.id as run_id,
        r.instance_id,
        t.dry_run,
        t.position_size_usd,
        t.risk_amount_usd
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      LEFT JOIN cycles c ON t.cycle_id = c.id
      LEFT JOIN runs r ON c.run_id = r.id
      LEFT JOIN instances i ON r.instance_id = i.id
      WHERE t.status = 'cancelled'
        AND t.exit_reason = 'max_bars_exceeded'
      ORDER BY t.created_at DESC
      LIMIT 50
    `);

    // Calculate bars open for each trade
    const tradesWithBars = cancelledTrades.map((t) => {
      let barsOpen = 0
      const cancelTime = t.cancelled_at || t.closed_at
      if (t.created_at && cancelTime && t.timeframe) {
        const createdTime = new Date(t.created_at).getTime()
        const cancelledTime = new Date(cancelTime).getTime()
        const timeframeMins: Record<string, number> = {
          '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
          '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440, '1D': 1440
        }
        const mins = timeframeMins[t.timeframe] || 60
        const diffMs = cancelledTime - createdTime
        barsOpen = Math.ceil(diffMs / (mins * 60 * 1000))
      }
      return { ...t, bars_open: barsOpen }
    })

    // Calculate summary stats
    const wins = tradesWithBars.filter((t) => t.pnl !== null && t.pnl > 0).length
    const losses = tradesWithBars.filter((t) => t.pnl !== null && t.pnl < 0).length
    const totalPnl = tradesWithBars.reduce((sum, t) => sum + (t.pnl || 0), 0)

    return NextResponse.json({
      trades: tradesWithBars,
      stats: {
        total: tradesWithBars.length,
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


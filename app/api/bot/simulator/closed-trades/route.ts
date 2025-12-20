import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/db/trading-db'

/**
 * Extract strategy name from instance settings JSON
 */
function getStrategyNameFromSettings(settingsJson: unknown): string | undefined {
  try {
    if (!settingsJson) return undefined;
    const settings = typeof settingsJson === 'string' ? JSON.parse(settingsJson) : settingsJson;
    return settings?.strategy || undefined;
  } catch {
    return undefined;
  }
}

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
  cancelled_at?: string | null;
  timeframe: string;
  instance_name: string;
  strategy_name?: string;
  run_id: string;
  bars_open?: number;
  // Position sizing metrics
  position_size_usd?: number;
  risk_amount_usd?: number;
  risk_percentage?: number;
  confidence_weight?: number;
  risk_per_unit?: number;
  sizing_method?: string;
  risk_pct_used?: number;
  // Strategy information
  strategy_type?: string | null;
  strategy_metadata?: any;
}

export async function GET() {
  try {
    // Get closed paper trades with instance info
    const closedTrades = await dbQuery<ClosedTrade & { instance_settings?: string | null }>(`
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
        i.settings as instance_settings,
        r.id as run_id,
        t.position_size_usd,
        t.risk_amount_usd,
        t.risk_percentage,
        t.confidence_weight,
        t.risk_per_unit,
        t.sizing_method,
        t.risk_pct_used,
        t.strategy_type,
        COALESCE(t.strategy_metadata, rec.strategy_metadata) as strategy_metadata
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      LEFT JOIN cycles c ON t.cycle_id = c.id
      LEFT JOIN runs r ON c.run_id = r.id
      LEFT JOIN instances i ON r.instance_id = i.id
      WHERE t.status = 'closed'
        AND t.pnl IS NOT NULL
        AND t.exit_reason IN ('tp_hit', 'sl_hit')
      ORDER BY t.created_at DESC
      LIMIT 50
    `);

    // Calculate bars open for each trade and extract strategy name
    const tradesWithBars = closedTrades.map((t) => {
      let barsOpen = 0
      // Use filled_at if available, otherwise use fill_time
      const fillTimestamp = t.filled_at || t.fill_time
      if (fillTimestamp && t.closed_at && t.timeframe) {
        const filledTime = new Date(fillTimestamp).getTime()
        const closedTime = new Date(t.closed_at).getTime()
        const timeframeMins: Record<string, number> = {
          '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
          '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720, '1d': 1440, '1D': 1440
        }
        const minutesPerBar = timeframeMins[t.timeframe] || 1
        const timeDiff = closedTime - filledTime
        // Only calculate if closed_at is after filled_at
        if (timeDiff > 0) {
          barsOpen = Math.ceil(timeDiff / (minutesPerBar * 60 * 1000))
        }
      }
      const strategyName = getStrategyNameFromSettings((t as any).instance_settings)
      const { instance_settings, ...tradeWithoutSettings } = t as any
      return { ...tradeWithoutSettings, bars_open: barsOpen, strategy_name: strategyName }
    })

    // Calculate summary stats
    const wins = tradesWithBars.filter((t) => t.pnl > 0).length
    const losses = tradesWithBars.filter((t) => t.pnl < 0).length
    const totalPnl = tradesWithBars.reduce((sum, t) => sum + (t.pnl || 0), 0)
    const avgBarsOpen = tradesWithBars.length > 0
      ? tradesWithBars.reduce((sum, t) => sum + (t.bars_open || 0), 0) / tradesWithBars.length
      : 0
    const avgWin = wins > 0
      ? tradesWithBars.filter((t) => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / wins
      : 0
    const avgLoss = losses > 0
      ? tradesWithBars.filter((t) => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0) / losses
      : 0

    return NextResponse.json({
      trades: tradesWithBars,
      stats: {
        total: tradesWithBars.length,
        wins,
        losses,
        win_rate: tradesWithBars.length > 0 ? (wins / tradesWithBars.length * 100) : 0,
        total_pnl: Math.round(totalPnl * 100) / 100,
        avg_win: Math.round(avgWin * 100) / 100,
        avg_loss: Math.round(avgLoss * 100) / 100,
        avg_bars_open: Math.round(avgBarsOpen * 100) / 100,
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


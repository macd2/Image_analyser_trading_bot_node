import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, isTradingDbAvailable } from '@/lib/db/trading-db'

interface TradeRow {
  id: string
  symbol: string
  pnl: number | null
  confidence: number
  position_size_usd: number | null
  strategy_type: string
  strategy_name: string
}

interface CorrelationMetrics {
  confidence_vs_winrate: number
  position_size_vs_pnl: number
  strategy_consistency: Array<{
    strategy: string
    coefficient_of_variation: number
    win_loss_ratio: number
    consecutive_wins: number
    consecutive_losses: number
  }>
  pnl_distribution: Array<{
    strategy: string
    avg_pnl: number
    std_dev: number
    min_pnl: number
    max_pnl: number
  }>
  confidence_levels: Array<{
    level: string
    win_rate: number
    trade_count: number
    avg_pnl: number
  }>
}

export async function GET(_request: NextRequest) {
  try {
    if (!isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Database unavailable' }, { status: 503 })
    }

    const trades = await dbQuery<TradeRow>(
      `SELECT id, symbol, pnl, confidence, position_size_usd, strategy_type, strategy_name
       FROM trades WHERE status NOT IN ('rejected', 'cancelled', 'error') ORDER BY created_at DESC`
    )

    if (trades.length === 0) {
      return NextResponse.json({
        confidence_vs_winrate: 0,
        position_size_vs_pnl: 0,
        strategy_consistency: [],
        pnl_distribution: [],
        confidence_levels: [],
      })
    }

    // Calculate confidence vs win rate correlation
    const closedTrades = trades.filter(t => t.pnl !== null)
    let confVsWin = 0
    if (closedTrades.length > 1) {
      const confidences = closedTrades.map(t => t.confidence)
      const wins = closedTrades.map(t => (t.pnl! > 0 ? 1 : 0))
      const meanConf = confidences.reduce((a, b) => a + b, 0) / confidences.length
      const meanWin = wins.reduce<number>((a, b) => a + b, 0) / wins.length
      const covConfWin = confidences.reduce((sum, c, i) => sum + (c - meanConf) * (wins[i] - meanWin), 0) / confidences.length
      const stdConf = Math.sqrt(confidences.reduce((sum, c) => sum + Math.pow(c - meanConf, 2), 0) / confidences.length)
      const stdWin = Math.sqrt(wins.reduce<number>((sum, w) => sum + Math.pow(w - meanWin, 2), 0) / wins.length)
      confVsWin = stdConf > 0 && stdWin > 0 ? covConfWin / (stdConf * stdWin) : 0
    }

    // Calculate position size vs P&L correlation
    const tradesWithSize = closedTrades.filter(t => t.position_size_usd !== null)
    let sizeVsPnl = 0
    if (tradesWithSize.length > 1) {
      const sizes = tradesWithSize.map(t => t.position_size_usd || 0)
      const pnls = tradesWithSize.map(t => t.pnl || 0)
      const meanSize = sizes.reduce((a, b) => a + b, 0) / sizes.length
      const meanPnl = pnls.reduce((a, b) => a + b, 0) / pnls.length
      const covSizePnl = sizes.reduce((sum, s, i) => sum + (s - meanSize) * (pnls[i] - meanPnl), 0) / sizes.length
      const stdSize = Math.sqrt(sizes.reduce((sum, s) => sum + Math.pow(s - meanSize, 2), 0) / sizes.length)
      const stdPnl = Math.sqrt(pnls.reduce((sum, p) => sum + Math.pow(p - meanPnl, 2), 0) / pnls.length)
      sizeVsPnl = stdSize > 0 && stdPnl > 0 ? covSizePnl / (stdSize * stdPnl) : 0
    }

    // Strategy consistency
    const strategyMap = new Map<string, TradeRow[]>()
    for (const trade of closedTrades) {
      const key = trade.strategy_type || 'unknown'
      if (!strategyMap.has(key)) strategyMap.set(key, [])
      strategyMap.get(key)!.push(trade)
    }

    const strategy_consistency = Array.from(strategyMap).map(([strategy, strategyTrades]) => {
      const pnls = strategyTrades.map(t => t.pnl || 0)
      const mean = pnls.reduce((a, b) => a + b, 0) / pnls.length
      const stdDev = Math.sqrt(pnls.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / pnls.length)
      const cv = mean !== 0 ? stdDev / Math.abs(mean) : 0
      const wins = pnls.filter(p => p > 0)
      const losses = pnls.filter(p => p < 0)
      const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b, 0) / wins.length : 0
      const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b, 0) / losses.length) : 0
      const wlRatio = avgLoss > 0 ? avgWin / avgLoss : 0

      return {
        strategy,
        coefficient_of_variation: Math.round(cv * 100) / 100,
        win_loss_ratio: Math.round(wlRatio * 100) / 100,
        consecutive_wins: 0,
        consecutive_losses: 0,
      }
    })

    // P&L distribution by strategy
    const pnl_distribution = Array.from(strategyMap).map(([strategy, strategyTrades]) => {
      const pnls = strategyTrades.map(t => t.pnl || 0)
      const mean = pnls.reduce((a, b) => a + b, 0) / pnls.length
      const stdDev = Math.sqrt(pnls.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / pnls.length)
      return {
        strategy,
        avg_pnl: Math.round(mean * 100) / 100,
        std_dev: Math.round(stdDev * 100) / 100,
        min_pnl: Math.round(Math.min(...pnls) * 100) / 100,
        max_pnl: Math.round(Math.max(...pnls) * 100) / 100,
      }
    })

    // Confidence levels
    const confidenceLevels = [
      { level: 'Low (0-0.3)', min: 0, max: 0.3 },
      { level: 'Medium (0.3-0.7)', min: 0.3, max: 0.7 },
      { level: 'High (0.7-1.0)', min: 0.7, max: 1.0 },
    ]

    const confidence_levels = confidenceLevels.map(({ level, min, max }) => {
      const levelTrades = closedTrades.filter(t => t.confidence >= min && t.confidence <= max)
      const wins = levelTrades.filter(t => t.pnl! > 0).length
      const pnls = levelTrades.map(t => t.pnl || 0)
      return {
        level,
        win_rate: levelTrades.length > 0 ? Math.round((wins / levelTrades.length) * 100 * 100) / 100 : 0,
        trade_count: levelTrades.length,
        avg_pnl: levelTrades.length > 0 ? Math.round((pnls.reduce((a, b) => a + b, 0) / levelTrades.length) * 100) / 100 : 0,
      }
    })

    const metrics: CorrelationMetrics = {
      confidence_vs_winrate: Math.round(confVsWin * 100) / 100,
      position_size_vs_pnl: Math.round(sizeVsPnl * 100) / 100,
      strategy_consistency,
      pnl_distribution,
      confidence_levels,
    }

    return NextResponse.json(metrics)
  } catch (error) {
    console.error('Correlation analysis error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}


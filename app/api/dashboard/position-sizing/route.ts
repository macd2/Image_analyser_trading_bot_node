/**
 * Dashboard Position Sizing API - Position size distribution and risk metrics
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, isTradingDbAvailable, type TradeRow } from '@/lib/db/trading-db';

export interface PositionSizingMetrics {
  avg_position_size: number;
  min_position_size: number;
  max_position_size: number;
  median_position_size: number;
  avg_risk_amount: number;
  avg_risk_percentage: number;
  distribution: Array<{
    bucket: string;
    count: number;
    percentage: number;
  }>;
  correlation: {
    position_size_vs_pnl: number;
    position_size_vs_win_rate: number;
  };
  by_strategy: Array<{
    strategy: string;
    avg_position_size: number;
    avg_risk_amount: number;
    trade_count: number;
  }>;
}

export async function GET(_request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 });
    }

    const trades = await dbQuery<TradeRow>(`
      SELECT t.*
      FROM trades t
      WHERE t.status NOT IN ('rejected', 'cancelled', 'error')
      AND t.position_size_usd IS NOT NULL
      ORDER BY t.created_at DESC
    `);

    if (trades.length === 0) {
      return NextResponse.json({
        avg_position_size: 0,
        min_position_size: 0,
        max_position_size: 0,
        median_position_size: 0,
        avg_risk_amount: 0,
        avg_risk_percentage: 0,
        distribution: [],
        correlation: { position_size_vs_pnl: 0, position_size_vs_win_rate: 0 },
        by_strategy: [],
      });
    }

    const positionSizes = trades.map(t => t.position_size_usd || 0).filter(p => p > 0);
    const riskAmounts = trades.map(t => t.risk_amount_usd || 0);
    const riskPercentages = trades.map(t => t.risk_percentage || 0);

    // Basic stats
    const avgPositionSize = positionSizes.reduce((a, b) => a + b, 0) / positionSizes.length;
    const minPositionSize = Math.min(...positionSizes);
    const maxPositionSize = Math.max(...positionSizes);
    const sortedSizes = [...positionSizes].sort((a, b) => a - b);
    const medianPositionSize = sortedSizes[Math.floor(sortedSizes.length / 2)];

    const avgRiskAmount = riskAmounts.reduce((a, b) => a + b, 0) / riskAmounts.length;
    const avgRiskPercentage = riskPercentages.reduce((a, b) => a + b, 0) / riskPercentages.length;

    // Distribution buckets
    const bucketSize = (maxPositionSize - minPositionSize) / 5 || 1;
    const buckets = [
      { min: minPositionSize, max: minPositionSize + bucketSize, label: `$${Math.round(minPositionSize)}-${Math.round(minPositionSize + bucketSize)}` },
      { min: minPositionSize + bucketSize, max: minPositionSize + bucketSize * 2, label: `$${Math.round(minPositionSize + bucketSize)}-${Math.round(minPositionSize + bucketSize * 2)}` },
      { min: minPositionSize + bucketSize * 2, max: minPositionSize + bucketSize * 3, label: `$${Math.round(minPositionSize + bucketSize * 2)}-${Math.round(minPositionSize + bucketSize * 3)}` },
      { min: minPositionSize + bucketSize * 3, max: minPositionSize + bucketSize * 4, label: `$${Math.round(minPositionSize + bucketSize * 3)}-${Math.round(minPositionSize + bucketSize * 4)}` },
      { min: minPositionSize + bucketSize * 4, max: maxPositionSize + 1, label: `$${Math.round(minPositionSize + bucketSize * 4)}+` },
    ];

    const distribution = buckets.map(bucket => {
      const count = positionSizes.filter(p => p >= bucket.min && p < bucket.max).length;
      return {
        bucket: bucket.label,
        count,
        percentage: Math.round((count / positionSizes.length) * 100),
      };
    });

    // Correlation: position size vs P&L
    const closedTrades = trades.filter(t => t.pnl !== null);
    let positionSizeVsPnl = 0;
    let positionSizeVsWinRate = 0;

    if (closedTrades.length > 1) {
      const sizes = closedTrades.map(t => t.position_size_usd || 0);
      const pnls = closedTrades.map(t => t.pnl || 0);
      const wins = closedTrades.map(t => (t.pnl || 0) > 0 ? 1 : 0);

      const meanSize = sizes.reduce<number>((a, b) => a + b, 0) / sizes.length;
      const meanPnl = pnls.reduce<number>((a, b) => a + b, 0) / pnls.length;
      const meanWin = wins.reduce<number>((a, b) => a + b, 0) / wins.length;

      const covSizePnl = sizes.reduce<number>((sum, s, i) => sum + (s - meanSize) * (pnls[i] - meanPnl), 0) / sizes.length;
      const covSizeWin = sizes.reduce<number>((sum, s, i) => sum + (s - meanSize) * (wins[i] - meanWin), 0) / sizes.length;

      const stdSize = Math.sqrt(sizes.reduce<number>((sum, s) => sum + Math.pow(s - meanSize, 2), 0) / sizes.length);
      const stdPnl = Math.sqrt(pnls.reduce<number>((sum, p) => sum + Math.pow(p - meanPnl, 2), 0) / pnls.length);
      const stdWin = Math.sqrt(wins.reduce<number>((sum, w) => sum + Math.pow(w - meanWin, 2), 0) / wins.length);

      positionSizeVsPnl = stdSize > 0 && stdPnl > 0 ? covSizePnl / (stdSize * stdPnl) : 0;
      positionSizeVsWinRate = stdSize > 0 && stdWin > 0 ? covSizeWin / (stdSize * stdWin) : 0;
    }

    // Group by strategy
    const strategyMap = new Map<string, TradeRow[]>();
    for (const trade of trades) {
      const strategy = trade.strategy_type || 'unknown';
      if (!strategyMap.has(strategy)) strategyMap.set(strategy, []);
      strategyMap.get(strategy)!.push(trade);
    }

    const by_strategy = Array.from(strategyMap).map(([strategy, strategyTrades]) => {
      const sizes = strategyTrades
        .filter(t => t.position_size_usd !== null)
        .map(t => t.position_size_usd || 0);
      const risks = strategyTrades
        .filter(t => t.risk_amount_usd !== null)
        .map(t => t.risk_amount_usd || 0);

      return {
        strategy,
        avg_position_size: sizes.length > 0 ? Math.round((sizes.reduce((a, b) => a + b, 0) / sizes.length) * 100) / 100 : 0,
        avg_risk_amount: risks.length > 0 ? Math.round((risks.reduce((a, b) => a + b, 0) / risks.length) * 100) / 100 : 0,
        trade_count: strategyTrades.length,
      };
    });

    const metrics: PositionSizingMetrics = {
      avg_position_size: Math.round(avgPositionSize * 100) / 100,
      min_position_size: Math.round(minPositionSize * 100) / 100,
      max_position_size: Math.round(maxPositionSize * 100) / 100,
      median_position_size: Math.round(medianPositionSize * 100) / 100,
      avg_risk_amount: Math.round(avgRiskAmount * 100) / 100,
      avg_risk_percentage: Math.round(avgRiskPercentage * 100) / 100,
      distribution,
      correlation: {
        position_size_vs_pnl: Math.round(positionSizeVsPnl * 100) / 100,
        position_size_vs_win_rate: Math.round(positionSizeVsWinRate * 100) / 100,
      },
      by_strategy,
    };

    return NextResponse.json(metrics);
  } catch (error) {
    console.error('Position sizing error:', error);
    return NextResponse.json({ error: 'Failed to get position sizing metrics' }, { status: 500 });
  }
}


/**
 * Dashboard Strategy Performance API - Per strategy-timeframe metrics with advanced calculations
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, isTradingDbAvailable, type TradeRow } from '@/lib/db/trading-db';

export interface StrategyMetrics {
  strategy_name: string;
  timeframe: string;
  trade_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  avg_confidence: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  expectancy: number;
  profit_factor: number;
  max_drawdown: number;
  recovery_factor: number;
  coefficient_of_variation: number;
  win_loss_ratio: number;
}

function calculateMetrics(trades: TradeRow[]): Partial<StrategyMetrics> {
  const closedTrades = trades.filter(t => t.pnl !== null);
  if (closedTrades.length === 0) return {};

  const pnls = closedTrades.map(t => t.pnl || 0);
  const wins = closedTrades.filter(t => (t.pnl || 0) > 0);
  const losses = closedTrades.filter(t => (t.pnl || 0) < 0);

  // Basic stats
  const totalPnl = pnls.reduce((a, b) => a + b, 0);
  const avgPnl = totalPnl / closedTrades.length;
  const winRate = (wins.length / closedTrades.length) * 100;

  // Sharpe Ratio: (avg return - risk-free rate) / std dev
  const mean = avgPnl;
  const variance = pnls.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / closedTrades.length;
  const stdDev = Math.sqrt(variance);
  const sharpeRatio = stdDev > 0 ? (mean - 0) / stdDev : 0;

  // Sortino Ratio: return / downside deviation
  const downside = pnls.filter(p => p < 0).map(p => Math.pow(p, 2));
  const downsideVariance = downside.length > 0 ? downside.reduce((a, b) => a + b, 0) / closedTrades.length : 0;
  const downsideStdDev = Math.sqrt(downsideVariance);
  const sortinoRatio = downsideStdDev > 0 ? mean / downsideStdDev : 0;

  // Expectancy: (win% * avg_win) - (loss% * avg_loss)
  const avgWin = wins.length > 0 ? wins.reduce((sum, t) => sum + (t.pnl || 0), 0) / wins.length : 0;
  const avgLoss = losses.length > 0 ? losses.reduce((sum, t) => sum + (t.pnl || 0), 0) / losses.length : 0;
  const expectancy = (winRate / 100 * avgWin) - ((100 - winRate) / 100 * Math.abs(avgLoss));

  // Profit Factor: gross profit / gross loss
  const grossProfit = wins.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const grossLoss = Math.abs(losses.reduce((sum, t) => sum + (t.pnl || 0), 0));
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 999 : 0);

  // Max Drawdown: largest peak-to-trough decline
  let maxDrawdown = 0;
  let peak = 0;
  let cumulative = 0;
  for (const pnl of pnls) {
    cumulative += pnl;
    if (cumulative > peak) peak = cumulative;
    const drawdown = peak - cumulative;
    if (drawdown > maxDrawdown) maxDrawdown = drawdown;
  }

  // Recovery Factor: total profit / max drawdown
  const recoveryFactor = maxDrawdown > 0 ? totalPnl / maxDrawdown : (totalPnl > 0 ? 999 : 0);

  // Coefficient of Variation: std dev / mean
  const coefficientOfVariation = Math.abs(mean) > 0 ? stdDev / Math.abs(mean) : 0;

  // Win/Loss Ratio: avg win / avg loss
  const winLossRatio = Math.abs(avgLoss) > 0 ? avgWin / Math.abs(avgLoss) : (avgWin > 0 ? 999 : 0);

  return {
    total_pnl: Math.round(totalPnl * 100) / 100,
    avg_pnl: Math.round(avgPnl * 100) / 100,
    win_rate: Math.round(winRate * 100) / 100,
    sharpe_ratio: Math.round(sharpeRatio * 100) / 100,
    sortino_ratio: Math.round(sortinoRatio * 100) / 100,
    expectancy: Math.round(expectancy * 100) / 100,
    profit_factor: Math.round(profitFactor * 100) / 100,
    max_drawdown: Math.round(maxDrawdown * 100) / 100,
    recovery_factor: Math.round(recoveryFactor * 100) / 100,
    coefficient_of_variation: Math.round(coefficientOfVariation * 100) / 100,
    win_loss_ratio: Math.round(winLossRatio * 100) / 100,
  };
}

export async function GET(_request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 });
    }

    const trades = await dbQuery<TradeRow>(`
      SELECT t.*, COALESCE(t.timeframe, r.timeframe) as timeframe
      FROM trades t
      LEFT JOIN recommendations r ON t.recommendation_id = r.id
      WHERE t.status NOT IN ('rejected', 'cancelled', 'error')
      ORDER BY t.created_at DESC
    `);

    // Group by strategy_type and timeframe
    const grouped = new Map<string, TradeRow[]>();
    for (const trade of trades) {
      const key = `${trade.strategy_type || 'unknown'}|${trade.timeframe || 'unknown'}`;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key)!.push(trade);
    }

    const strategies: StrategyMetrics[] = [];
    for (const [key, groupTrades] of grouped) {
      const [strategyType, timeframe] = key.split('|');
      const metrics = calculateMetrics(groupTrades);
      const avgConfidence = groupTrades.length > 0
        ? groupTrades.reduce((sum, t) => sum + (t.confidence || 0), 0) / groupTrades.length
        : 0;

      strategies.push({
        strategy_name: strategyType,
        timeframe,
        trade_count: groupTrades.length,
        avg_confidence: Math.round(avgConfidence * 100) / 100,
        ...metrics,
      } as StrategyMetrics);
    }

    // Sort by Sharpe Ratio descending
    strategies.sort((a, b) => (b.sharpe_ratio || 0) - (a.sharpe_ratio || 0));

    return NextResponse.json({ strategies });
  } catch (error) {
    console.error('Strategy performance error:', error);
    return NextResponse.json({ error: 'Failed to get strategy performance' }, { status: 500 });
  }
}


/**
 * Dashboard Symbol Performance API - Per symbol metrics
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, isTradingDbAvailable, type TradeRow } from '@/lib/db/trading-db';

export interface SymbolMetrics {
  symbol: string;
  trade_count: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  avg_confidence: number;
  best_trade: number;
  worst_trade: number;
  winning_trades: number;
  losing_trades: number;
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

    // Group by symbol
    const grouped = new Map<string, TradeRow[]>();
    for (const trade of trades) {
      const symbol = trade.symbol || 'unknown';
      if (!grouped.has(symbol)) grouped.set(symbol, []);
      grouped.get(symbol)!.push(trade);
    }

    const symbols: SymbolMetrics[] = [];
    for (const [symbol, symbolTrades] of grouped) {
      const closedTrades = symbolTrades.filter(t => t.pnl !== null);
      if (closedTrades.length === 0) continue;

      const pnls = closedTrades.map(t => t.pnl || 0);
      const wins = closedTrades.filter(t => (t.pnl || 0) > 0);
      const losses = closedTrades.filter(t => (t.pnl || 0) < 0);

      const totalPnl = pnls.reduce((a, b) => a + b, 0);
      const avgPnl = totalPnl / closedTrades.length;
      const winRate = (wins.length / closedTrades.length) * 100;
      const avgConfidence = symbolTrades.length > 0
        ? symbolTrades.reduce((sum, t) => sum + (t.confidence || 0), 0) / symbolTrades.length
        : 0;

      const bestTrade = Math.max(...pnls);
      const worstTrade = Math.min(...pnls);

      symbols.push({
        symbol,
        trade_count: symbolTrades.length,
        win_rate: Math.round(winRate * 100) / 100,
        total_pnl: Math.round(totalPnl * 100) / 100,
        avg_pnl: Math.round(avgPnl * 100) / 100,
        avg_confidence: Math.round(avgConfidence * 100) / 100,
        best_trade: Math.round(bestTrade * 100) / 100,
        worst_trade: Math.round(worstTrade * 100) / 100,
        winning_trades: wins.length,
        losing_trades: losses.length,
      });
    }

    // Sort by win rate descending
    symbols.sort((a, b) => b.win_rate - a.win_rate);

    return NextResponse.json({ symbols });
  } catch (error) {
    console.error('Symbol performance error:', error);
    return NextResponse.json({ error: 'Failed to get symbol performance' }, { status: 500 });
  }
}


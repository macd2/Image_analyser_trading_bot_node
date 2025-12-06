/**
 * Bot Positions API - GET open positions and monitoring data
 */

import { NextRequest, NextResponse } from 'next/server';
import { 
  getRecentTrades,
  isTradingDbAvailable,
  type TradeRow,
} from '@/lib/db/trading-db';

export interface OpenPosition {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entry_price: number;
  current_price: number | null;
  quantity: number;
  stop_loss: number;
  take_profit: number;
  pnl_percent: number;
  pnl_usd: number;
  duration: string;
  confidence: number | null;
  filled_at: string;
}

export interface ClosedTrade {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  result: 'TP Hit' | 'SL Hit' | 'Manual Close';
  pnl_percent: number;
  closed_at: string;
}

export interface PositionsResponse {
  open_positions: OpenPosition[];
  closed_today: ClosedTrade[];
  stats: {
    open_count: number;
    unrealized_pnl: number;
    closed_today_count: number;
    win_rate_today: number;
    total_pnl_today: number;
  };
}

/**
 * Calculate duration string from timestamp
 */
function getDuration(filledAt: string): string {
  const filled = new Date(filledAt);
  const now = new Date();
  const diffMs = now.getTime() - filled.getTime();
  
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  const minutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

/**
 * Determine exit reason from trade data
 */
function getExitResult(trade: TradeRow): 'TP Hit' | 'SL Hit' | 'Manual Close' {
  if (trade.exit_reason) {
    if (trade.exit_reason.toLowerCase().includes('tp') || trade.exit_reason.toLowerCase().includes('take_profit')) {
      return 'TP Hit';
    }
    if (trade.exit_reason.toLowerCase().includes('sl') || trade.exit_reason.toLowerCase().includes('stop_loss')) {
      return 'SL Hit';
    }
  }
  // Infer from P&L
  if (trade.pnl !== null && trade.pnl > 0) return 'TP Hit';
  if (trade.pnl !== null && trade.pnl < 0) return 'SL Hit';
  return 'Manual Close';
}

/**
 * GET /api/bot/positions - Get open positions and today's closed trades
 */
export async function GET(_request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const allTrades = await getRecentTrades(200);
    
    // Open positions: filled but not closed
    const openStatuses = ['filled', 'partially_filled'];
    const openTrades = allTrades.filter(t => openStatuses.includes(t.status));
    
    // Closed today
    const today = new Date().toISOString().split('T')[0];
    const closedToday = allTrades.filter(t => {
      if (t.status !== 'closed' || !t.closed_at) return false;
      // Handle both string and Date object (PostgreSQL returns Date)
      const closedAtStr = typeof t.closed_at === 'string'
        ? t.closed_at
        : (t.closed_at as unknown as Date).toISOString();
      return closedAtStr.startsWith(today);
    });

    // Build open positions response
    const openPositions: OpenPosition[] = openTrades.map(t => ({
      id: t.id,
      symbol: t.symbol,
      side: t.side === 'Buy' ? 'LONG' : 'SHORT',
      entry_price: t.fill_price || t.entry_price,
      current_price: null, // Would need real-time price feed
      quantity: t.fill_quantity || t.quantity,
      stop_loss: t.stop_loss,
      take_profit: t.take_profit,
      pnl_percent: t.pnl_percent || 0,
      pnl_usd: t.pnl || 0,
      duration: t.filled_at ? getDuration(t.filled_at) : '0m',
      confidence: t.confidence,
      filled_at: t.filled_at || t.created_at,
    }));

    // Build closed trades response
    const closedTradesResponse: ClosedTrade[] = closedToday.map(t => {
      // Handle both string and Date object (PostgreSQL returns Date)
      const closedAtStr = typeof t.closed_at === 'string'
        ? t.closed_at
        : (t.closed_at as unknown as Date)?.toISOString() || '';
      return {
        id: t.id,
        symbol: t.symbol,
        side: t.side === 'Buy' ? 'LONG' : 'SHORT',
        result: getExitResult(t),
        pnl_percent: t.pnl_percent || 0,
        closed_at: closedAtStr,
      };
    });

    // Calculate stats
    const wins = closedToday.filter(t => (t.pnl || 0) > 0);
    const unrealizedPnl = openPositions.reduce((sum, p) => sum + p.pnl_percent, 0);
    const totalPnlToday = closedToday.reduce((sum, t) => sum + (t.pnl_percent || 0), 0);

    const response: PositionsResponse = {
      open_positions: openPositions,
      closed_today: closedTradesResponse,
      stats: {
        open_count: openPositions.length,
        unrealized_pnl: Math.round(unrealizedPnl * 100) / 100,
        closed_today_count: closedToday.length,
        win_rate_today: closedToday.length > 0 ? Math.round((wins.length / closedToday.length) * 100) : 0,
        total_pnl_today: Math.round(totalPnlToday * 100) / 100,
      },
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Positions GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get positions' },
      { status: 500 }
    );
  }
}


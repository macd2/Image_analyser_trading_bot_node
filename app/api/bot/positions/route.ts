/**
 * Bot Positions API - GET open positions and monitoring data
 * Now includes dry run (paper trading) positions
 */

import { NextRequest, NextResponse } from 'next/server';
import { 
  getRecentTrades,
  isTradingDbAvailable,
  type TradeRow,
} from '@/lib/db/trading-db';
import { query } from '@/lib/db/client';

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
  dry_run: boolean; // Added to distinguish dry run positions
}

export interface ClosedTrade {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  result: 'TP Hit' | 'SL Hit' | 'Manual Close';
  pnl_percent: number;
  closed_at: string;
  dry_run: boolean; // Added to distinguish dry run trades
}

export interface PositionsResponse {
  open_positions: OpenPosition[];
  closed_today: ClosedTrade[];
  stats: {
    open_count: number;
    open_dry_run_count: number;
    open_live_count: number;
    unrealized_pnl: number;
    unrealized_pnl_dry_run: number;
    unrealized_pnl_live: number;
    closed_today_count: number;
    closed_today_dry_run_count: number;
    closed_today_live_count: number;
    win_rate_today: number;
    win_rate_today_dry_run: number;
    win_rate_today_live: number;
    total_pnl_today: number;
    total_pnl_today_dry_run: number;
    total_pnl_today_live: number;
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
 * Now includes dry run positions
 */
export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const { searchParams } = new URL(request.url);
    const includeDryRun = searchParams.get('include_dry_run') !== 'false'; // Default to true
    const instanceId = searchParams.get('instance_id');

    // Get all trades including dry run
    const allTrades = await getRecentTrades(200);
    
    // Filter by instance if instance_id is provided
    let filteredTrades = allTrades;
    if (instanceId) {
      // We need to get trades for this instance by joining with runs table
      const instanceTrades = await query<TradeRow>(`
        SELECT t.* 
        FROM trades t
        JOIN runs r ON t.run_id = r.id
        WHERE r.instance_id = ?
        ORDER BY t.created_at DESC
        LIMIT 200
      `, [instanceId]);
      filteredTrades = instanceTrades;
    }
    
    // Open positions: filled but not closed
    const openStatuses = ['filled', 'partially_filled', 'paper_trade'];
    const openTrades = filteredTrades.filter(t => 
      openStatuses.includes(t.status) && 
      (includeDryRun || !t.dry_run) // Include dry run only if requested
    );
    
    // Closed today
    const today = new Date().toISOString().split('T')[0];
    const closedToday = filteredTrades.filter(t => {
      if (t.status !== 'closed' || !t.closed_at) return false;
      if (!includeDryRun && t.dry_run) return false; // Skip dry run if not requested
      
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
      dry_run: Boolean(t.dry_run),
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
        dry_run: Boolean(t.dry_run),
      };
    });

    // Calculate stats - separate for live and dry run
    const liveOpenPositions = openPositions.filter(p => !p.dry_run);
    const dryRunOpenPositions = openPositions.filter(p => p.dry_run);
    
    const liveClosedToday = closedToday.filter(t => !t.dry_run);
    const dryRunClosedToday = closedToday.filter(t => t.dry_run);
    
    const liveWins = liveClosedToday.filter(t => (t.pnl || 0) > 0);
    const dryRunWins = dryRunClosedToday.filter(t => (t.pnl || 0) > 0);
    
    const unrealizedPnlLive = liveOpenPositions.reduce((sum, p) => sum + p.pnl_percent, 0);
    const unrealizedPnlDryRun = dryRunOpenPositions.reduce((sum, p) => sum + p.pnl_percent, 0);
    
    const totalPnlTodayLive = liveClosedToday.reduce((sum, t) => sum + (t.pnl_percent || 0), 0);
    const totalPnlTodayDryRun = dryRunClosedToday.reduce((sum, t) => sum + (t.pnl_percent || 0), 0);

    const response: PositionsResponse = {
      open_positions: openPositions,
      closed_today: closedTradesResponse,
      stats: {
        open_count: openPositions.length,
        open_dry_run_count: dryRunOpenPositions.length,
        open_live_count: liveOpenPositions.length,
        unrealized_pnl: Math.round((unrealizedPnlLive + unrealizedPnlDryRun) * 100) / 100,
        unrealized_pnl_dry_run: Math.round(unrealizedPnlDryRun * 100) / 100,
        unrealized_pnl_live: Math.round(unrealizedPnlLive * 100) / 100,
        closed_today_count: closedToday.length,
        closed_today_dry_run_count: dryRunClosedToday.length,
        closed_today_live_count: liveClosedToday.length,
        win_rate_today: closedToday.length > 0 ? Math.round(((liveWins.length + dryRunWins.length) / closedToday.length) * 100) : 0,
        win_rate_today_dry_run: dryRunClosedToday.length > 0 ? Math.round((dryRunWins.length / dryRunClosedToday.length) * 100) : 0,
        win_rate_today_live: liveClosedToday.length > 0 ? Math.round((liveWins.length / liveClosedToday.length) * 100) : 0,
        total_pnl_today: Math.round((totalPnlTodayLive + totalPnlTodayDryRun) * 100) / 100,
        total_pnl_today_dry_run: Math.round(totalPnlTodayDryRun * 100) / 100,
        total_pnl_today_live: Math.round(totalPnlTodayLive * 100) / 100,
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

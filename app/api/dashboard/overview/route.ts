/**
 * Dashboard Overview API - System health and key metrics
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getGlobalStats,
  getInstancesWithStatus,
  getRecentTrades,
  isTradingDbAvailable,
  type InstanceRow,
} from '@/lib/db/trading-db';

export interface DashboardOverview {
  system_health: {
    active_instances: number;
    total_instances: number;
    instance_status: Array<{
      id: string;
      name: string;
      status: string;
      is_active: boolean;
    }>;
  };
  performance: {
    total_pnl: number;
    win_rate: number;
    total_trades: number;
    winning_trades: number;
    losing_trades: number;
    avg_confidence: number;
  };
  positions: {
    open_count: number;
    closed_today_count: number;
    unrealized_pnl: number;
  };
  timestamp: string;
}

export async function GET(_request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const [globalStats, instances, recentTrades] = await Promise.all([
      getGlobalStats(),
      getInstancesWithStatus(),
      getRecentTrades(200),
    ]);

    // Count active instances
    const activeInstances = (instances as InstanceRow[]).filter(i => i.is_active).length;
    const totalInstances = (instances as InstanceRow[]).length;

    // Get position stats from recent trades
    const openTrades = recentTrades.filter(t =>
      ['filled', 'partially_filled', 'paper_trade'].includes(t.status)
    );
    const today = new Date().toISOString().split('T')[0];
    const closedToday = recentTrades.filter(t => {
      if (t.status !== 'closed' || !t.closed_at) return false;
      const closedAtStr = typeof t.closed_at === 'string'
        ? t.closed_at
        : (t.closed_at as unknown as Date).toISOString();
      return closedAtStr.startsWith(today);
    });

    // Calculate performance metrics from closed trades
    const closedTrades = recentTrades.filter(t => t.status === 'closed' && t.pnl !== null);
    const winningTrades = closedTrades.filter(t => (t.pnl || 0) > 0).length;
    const losingTrades = closedTrades.filter(t => (t.pnl || 0) < 0).length;
    const winRate = closedTrades.length > 0 ? (winningTrades / closedTrades.length) * 100 : 0;
    const avgConfidence = closedTrades.length > 0
      ? closedTrades.reduce((sum, t) => sum + (t.confidence || 0), 0) / closedTrades.length
      : 0;

    const overview: DashboardOverview = {
      system_health: {
        active_instances: activeInstances,
        total_instances: totalInstances,
        instance_status: (instances as InstanceRow[]).map(i => ({
          id: i.id,
          name: i.name,
          status: i.is_active ? 'active' : 'inactive',
          is_active: Boolean(i.is_active),
        })),
      },
      performance: {
        total_pnl: globalStats.total_pnl || 0,
        win_rate: Math.round(winRate * 100) / 100,
        total_trades: closedTrades.length,
        winning_trades: winningTrades,
        losing_trades: losingTrades,
        avg_confidence: Math.round(avgConfidence * 100) / 100,
      },
      positions: {
        open_count: openTrades.length,
        closed_today_count: closedToday.length,
        unrealized_pnl: openTrades.reduce((sum, t) => sum + (t.pnl_percent || 0), 0),
      },
      timestamp: new Date().toISOString(),
    };

    return NextResponse.json(overview);
  } catch (error) {
    console.error('Dashboard overview error:', error);
    return NextResponse.json(
      { error: 'Failed to get dashboard overview' },
      { status: 500 }
    );
  }
}


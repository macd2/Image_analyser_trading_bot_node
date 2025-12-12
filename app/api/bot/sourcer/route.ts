/**
 * Bot Sourcer Status API - GET chart capture status for CaptureView
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getRecentCycles,
  getRecentRecommendations,
  isTradingDbAvailable,
  getInstanceConfigAsRows,
} from '@/lib/db/trading-db';

export interface SourcerStatusResponse {
  next_capture: {
    time: string;
    seconds_remaining: number;
  };
  timeframe: string;
  watchlist: string[];
  current_cycle: {
    id: string | null;
    started_at: string | null;
    charts_captured: number;
    status: string;
  };
  recent_captures: {
    symbol: string;
    timeframe: string;
    timestamp: string;
    chart_path: string | null;
    status: 'success' | 'failed';
  }[];
  stats: {
    captured_today: number;
    failed_today: number;
    symbols_count: number;
  };
}

/**
 * Calculate next cycle boundary based on timeframe
 */
function getNextBoundary(timeframe: string): { time: Date; seconds: number } {
  const now = new Date();
  const minutes = now.getUTCMinutes();
  const hours = now.getUTCHours();
  
  let nextBoundary: Date;
  
  switch (timeframe) {
    case '15m':
      const next15 = Math.ceil((minutes + 1) / 15) * 15;
      nextBoundary = new Date(now);
      nextBoundary.setUTCMinutes(next15, 0, 0);
      if (next15 >= 60) {
        nextBoundary.setUTCHours(hours + 1);
        nextBoundary.setUTCMinutes(0);
      }
      break;
    case '30m':
      const next30 = Math.ceil((minutes + 1) / 30) * 30;
      nextBoundary = new Date(now);
      nextBoundary.setUTCMinutes(next30, 0, 0);
      if (next30 >= 60) {
        nextBoundary.setUTCHours(hours + 1);
        nextBoundary.setUTCMinutes(0);
      }
      break;
    case '4h':
      const next4h = Math.ceil((hours + 1) / 4) * 4;
      nextBoundary = new Date(now);
      nextBoundary.setUTCHours(next4h, 0, 0, 0);
      break;
    case '1h':
    default:
      nextBoundary = new Date(now);
      nextBoundary.setUTCHours(hours + 1, 0, 0, 0);
      break;
  }
  
  const seconds = Math.max(0, Math.floor((nextBoundary.getTime() - now.getTime()) / 1000));
  return { time: nextBoundary, seconds };
}

/**
 * GET /api/bot/sourcer - Get sourcer/capture status
 * Query params:
 *   - instance_id: string (optional) - Get timeframe from specific instance
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const instanceId = searchParams.get('instance_id');

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Get timeframe from instance config (or use default)
    const config = instanceId ? await getInstanceConfigAsRows(instanceId) : [];
    const timeframeConfig = config.find(c => c.key === 'trading.timeframe');
    const timeframe = timeframeConfig?.value || '1h';

    // Calculate next boundary
    const { time: nextTime, seconds } = getNextBoundary(timeframe);

    // Get most recent cycle (instance-aware if instanceId provided)
    const cycles = await getRecentCycles(1, instanceId || undefined);
    const currentCycle = cycles[0] || null;

    // Get recent recommendations for capture info (instance-aware if instanceId provided)
    const recommendations = await getRecentRecommendations(50, instanceId || undefined);
    
    // Extract unique symbols from recent recommendations
    const watchlist = [...new Set(recommendations.map(r => r.symbol))];

    // Get today's captures
    const today = new Date().toISOString().split('T')[0];
    const todayRecs = recommendations.filter(r => {
      if (!r.analyzed_at) return false;
      // Handle both string and Date object (PostgreSQL returns Date)
      const analyzedAtStr = typeof r.analyzed_at === 'string'
        ? r.analyzed_at
        : (r.analyzed_at as unknown as Date).toISOString();
      return analyzedAtStr.startsWith(today);
    });
    const capturedToday = todayRecs.length;

    // Build recent captures list from recommendations
    const recentCaptures = recommendations.slice(0, 10).map(r => ({
      symbol: r.symbol,
      timeframe: r.timeframe,
      timestamp: r.analyzed_at,
      chart_path: r.chart_path,
      status: 'success' as const,
    }));

    const response: SourcerStatusResponse = {
      next_capture: {
        time: nextTime.toISOString(),
        seconds_remaining: seconds,
      },
      timeframe,
      watchlist,
      current_cycle: {
        id: currentCycle?.id || null,
        started_at: currentCycle?.started_at || null,
        charts_captured: currentCycle?.charts_captured || 0,
        status: currentCycle?.status || 'idle',
      },
      recent_captures: recentCaptures,
      stats: {
        captured_today: capturedToday,
        failed_today: 0, // Would need error tracking
        symbols_count: watchlist.length,
      },
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Sourcer status GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get sourcer status' },
      { status: 500 }
    );
  }
}


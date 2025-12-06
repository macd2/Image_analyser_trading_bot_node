/**
 * Open Paper Trades API for Simulator
 * GET /api/bot/simulator/open-trades - Get all open paper trades organized by instance/run/cycle
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, isTradingDbAvailable } from '@/lib/db/trading-db';

export interface OpenPaperTrade {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  quantity: number;
  status: string;
  created_at: string;
  filled_at: string | null;
  submitted_at: string | null;
  timeframe: string | null;
  confidence: number | null;
  rr_ratio: number | null;
  cycle_id: string;
  run_id: string;
}

export interface CycleWithTrades {
  cycle_id: string;
  boundary_time: string;
  status: string;
  trades: OpenPaperTrade[];
}

export interface RunWithCycles {
  run_id: string;
  instance_id: string;
  started_at: string;
  status: string;
  cycles: CycleWithTrades[];
}

export interface InstanceWithRuns {
  instance_id: string;
  instance_name: string;
  runs: RunWithCycles[];
}

interface OpenTradeRow {
  id: string;
  symbol: string;
  side: 'Buy' | 'Sell';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  quantity: number;
  status: string;
  created_at: string;
  filled_at: string | null;
  submitted_at: string | null;
  timeframe: string | null;
  confidence: number | null;
  rr_ratio: number | null;
  cycle_id: string;
  run_id: string;
  boundary_time: string;
  cycle_status: string;
  instance_id: string;
  run_started_at: string;
  run_status: string;
  instance_name: string;
}

/**
 * GET /api/bot/simulator/open-trades
 * Returns open paper trades organized by instance → run → cycle
 */
export async function GET(_request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Get all open paper trades - trades that need simulation
    // A paper trade is one with status in (paper_trade, pending_fill, filled) AND pnl IS NULL
    // This includes BOTH dry_run=1 (paper mode instance) AND dry_run=0 (live instance in paper execution)
    // Exclude rejected, cancelled, and error trades
    const openTrades = await dbQuery<OpenTradeRow>(`
      SELECT
        t.*,
        COALESCE(t.timeframe, rec.timeframe) as timeframe,
        COALESCE(t.entry_price, rec.entry_price) as entry_price,
        COALESCE(t.stop_loss, rec.stop_loss) as stop_loss,
        COALESCE(t.take_profit, rec.take_profit) as take_profit,
        c.boundary_time,
        c.status as cycle_status,
        r.instance_id,
        r.started_at as run_started_at,
        r.status as run_status,
        i.name as instance_name
      FROM trades t
      LEFT JOIN recommendations rec ON t.recommendation_id = rec.id
      JOIN cycles c ON t.cycle_id = c.id
      JOIN runs r ON c.run_id = r.id
      JOIN instances i ON r.instance_id = i.id
      WHERE t.pnl IS NULL
        AND t.status IN ('paper_trade', 'pending_fill', 'filled')
      ORDER BY i.name, r.started_at DESC, c.boundary_time DESC, t.created_at DESC
    `);

    // Organize by hierarchy: instance → run → cycle → trades
    const instanceMap = new Map<string, InstanceWithRuns>();

    for (const trade of openTrades) {
      const instanceId = trade.instance_id;
      const runId = trade.run_id;
      const cycleId = trade.cycle_id;

      // Get or create instance
      if (!instanceMap.has(instanceId)) {
        instanceMap.set(instanceId, {
          instance_id: instanceId,
          instance_name: trade.instance_name || instanceId,
          runs: []
        });
      }
      const instance = instanceMap.get(instanceId)!;

      // Get or create run
      let run = instance.runs.find(r => r.run_id === runId);
      if (!run) {
        run = {
          run_id: runId,
          instance_id: instanceId,
          started_at: trade.run_started_at,
          status: trade.run_status,
          cycles: []
        };
        instance.runs.push(run);
      }

      // Get or create cycle
      let cycle = run.cycles.find(c => c.cycle_id === cycleId);
      if (!cycle) {
        cycle = {
          cycle_id: cycleId,
          boundary_time: trade.boundary_time,
          status: trade.cycle_status,
          trades: []
        };
        run.cycles.push(cycle);
      }

      // Add trade to cycle
      cycle.trades.push({
        id: trade.id,
        symbol: trade.symbol,
        side: trade.side,
        entry_price: trade.entry_price,
        stop_loss: trade.stop_loss,
        take_profit: trade.take_profit,
        quantity: trade.quantity,
        status: trade.status,
        created_at: trade.created_at,
        filled_at: trade.filled_at,
        submitted_at: trade.submitted_at,
        timeframe: trade.timeframe,
        confidence: trade.confidence,
        rr_ratio: trade.rr_ratio,
        cycle_id: cycleId,
        run_id: runId
      });
    }

    const instances = Array.from(instanceMap.values());

    return NextResponse.json({
      instances,
      total_open_trades: openTrades.length
    });
  } catch (error) {
    console.error('Open trades API error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}


import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db/client';

export interface BotStatsResponse {
  instance_info: {
    id: string;
    name: string;
    mode: 'paper' | 'live';
    timeframe: string;
    prompt_name: string;
    is_active: boolean;
  };
  runtime_stats: {
    cycle_count: number;
    running_duration_hours: number;
    start_time: string;
    current_run_id: string;
    total_trades: number;
    win_rate: number;
    total_pnl: number;
    avg_confidence: number;
  };
  performance_metrics: {
    charts_captured: number;
    analyses_completed: number;
    recommendations_generated: number;
    trades_executed: number;
    slots_used: number;
    slots_available: number;
  };
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id');

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id is required' },
        { status: 400 }
      );
    }

    // Get instance information
    const instances = await query<{
      id: string;
      name: string;
      timeframe: string;
      prompt_name: string;
      is_active: boolean;
      settings: any;
    }>(`
      SELECT id, name, timeframe, prompt_name, is_active, settings
      FROM instances
      WHERE id = ?
    `, [instanceId]);

    if (instances.length === 0) {
      return NextResponse.json(
        { error: 'Instance not found' },
        { status: 404 }
      );
    }

    const instance = instances[0];
    // Safely parse settings (could be string, object, or null)
    let settings: Record<string, unknown> = {};
    if (instance.settings) {
      if (typeof instance.settings === 'string') {
        try {
          settings = JSON.parse(instance.settings);
        } catch (e) {
          console.warn('Failed to parse settings string:', e);
        }
      } else if (typeof instance.settings === 'object') {
        settings = instance.settings as Record<string, unknown>;
      }
    }
    const mode = settings.paper_trading === false ? 'live' : 'paper';

    // Get current run
    const runs = await query<{
      id: string;
      started_at: string;
      paper_trading: boolean;
      total_cycles: number;
      total_trades: number;
      total_pnl: number;
      win_count: number;
      loss_count: number;
    }>(`
      SELECT 
        id, started_at, paper_trading,
        total_cycles, total_trades, total_pnl,
        win_count, loss_count
      FROM runs 
      WHERE instance_id = ? AND status = 'running'
      ORDER BY started_at DESC 
      LIMIT 1
    `, [instanceId]);

    let runtimeStats = {
      cycle_count: 0,
      running_duration_hours: 0,
      start_time: '',
      current_run_id: '',
      total_trades: 0,
      win_rate: 0,
      total_pnl: 0,
      avg_confidence: 0
    };

    let performanceMetrics = {
      charts_captured: 0,
      analyses_completed: 0,
      recommendations_generated: 0,
      trades_executed: 0,
      slots_used: 0,
      slots_available: 5 // default
    };

    if (runs.length > 0) {
      const run = runs[0];
      const startTime = new Date(run.started_at);
      const now = new Date();
      const runningDurationMs = now.getTime() - startTime.getTime();
      const runningDurationHours = runningDurationMs / (1000 * 60 * 60);

      // Calculate win rate
      const totalClosedTrades = run.win_count + run.loss_count;
      const winRate = totalClosedTrades > 0 ? (run.win_count / totalClosedTrades) * 100 : 0;

      // Get current cycle stats
      const cycles = await query<{
        charts_captured: number;
        analyses_completed: number;
        recommendations_generated: number;
        trades_executed: number;
        available_slots: number;
        open_positions: number;
      }>(`
        SELECT 
          charts_captured, analyses_completed, 
          recommendations_generated, trades_executed,
          available_slots, open_positions
        FROM cycles 
        WHERE run_id = ? 
        ORDER BY cycle_number DESC 
        LIMIT 1
      `, [run.id]);

      if (cycles.length > 0) {
        const cycle = cycles[0];
        performanceMetrics = {
          charts_captured: cycle.charts_captured,
          analyses_completed: cycle.analyses_completed,
          recommendations_generated: cycle.recommendations_generated,
          trades_executed: cycle.trades_executed,
          slots_used: cycle.open_positions || 0,
          slots_available: cycle.available_slots || 5
        };
      }

      // Get average confidence from recent recommendations
      const confidenceResult = await query<{ avg_confidence: number }>(`
        SELECT AVG(confidence) as avg_confidence
        FROM recommendations 
        WHERE cycle_id IN (
          SELECT id FROM cycles WHERE run_id = ?
        )
      `, [run.id]);

      runtimeStats = {
        cycle_count: run.total_cycles,
        running_duration_hours: parseFloat(runningDurationHours.toFixed(1)),
        start_time: run.started_at,
        current_run_id: run.id,
        total_trades: run.total_trades,
        win_rate: parseFloat(winRate.toFixed(1)),
        total_pnl: run.total_pnl || 0,
        avg_confidence: confidenceResult[0]?.avg_confidence ? parseFloat(confidenceResult[0].avg_confidence.toFixed(3)) : 0
      };
    }

    const response: BotStatsResponse = {
      instance_info: {
        id: instance.id,
        name: instance.name,
        mode,
        timeframe: instance.timeframe || '1h',
        prompt_name: instance.prompt_name || 'analyzer_v2',
        is_active: instance.is_active
      },
      runtime_stats: runtimeStats,
      performance_metrics: performanceMetrics
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Bot stats GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get bot stats' },
      { status: 500 }
    );
  }
}
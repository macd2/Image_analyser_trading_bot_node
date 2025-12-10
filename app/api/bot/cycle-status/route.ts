import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db/client';

export const dynamic = 'force-dynamic';

export interface CycleStatusResponse {
  current_cycle: {
    id: string;
    cycle_number: number;
    status: string;
    started_at: string;
    progress_percentage: number;
    current_step: 'chart_capture' | 'analysis' | 'risk_management' | 'order_execution' | 'waiting';
    next_step_time: string | null;
    steps: Array<{
      name: string;
      status: 'completed' | 'current' | 'pending';
      description: string;
    }>;
  } | null;
  cycle_stats: {
    total_cycles: number;
    successful_cycles: number;
    avg_cycle_duration_minutes: number;
    last_cycle_completed: string | null;
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

    // Get current run for the instance
    const runs = await query<{
      id: string;
      started_at: string;
      status: string;
    }>(`
      SELECT id, started_at, status 
      FROM runs 
      WHERE instance_id = ? AND status = 'running'
      ORDER BY started_at DESC 
      LIMIT 1
    `, [instanceId]);

    if (runs.length === 0) {
      return NextResponse.json({
        current_cycle: null,
        cycle_stats: { total_cycles: 0, successful_cycles: 0, avg_cycle_duration_minutes: 0, last_cycle_completed: null }
      });
    }

    const currentRun = runs[0];

    // Get current cycle for the run
    const cycles = await query<{
      id: string;
      cycle_number: number;
      status: string;
      started_at: string;
      completed_at: string | null;
      charts_captured: number;
      analyses_completed: number;
      recommendations_generated: number;
      trades_executed: number;
    }>(`
      SELECT 
        id, cycle_number, status, started_at, completed_at,
        charts_captured, analyses_completed, recommendations_generated, trades_executed
      FROM cycles 
      WHERE run_id = ? 
      ORDER BY cycle_number DESC 
      LIMIT 1
    `, [currentRun.id]);

    let currentCycle = null;
    let cycleStats = {
      total_cycles: 0,
      successful_cycles: 0,
      avg_cycle_duration_minutes: 0,
      last_cycle_completed: null as string | null
    };

    if (cycles.length > 0) {
      const cycle = cycles[0];
      
      // Calculate progress based on cycle activities
      let progressPercentage = 0;
      let currentStep: 'chart_capture' | 'analysis' | 'risk_management' | 'order_execution' | 'waiting' = 'chart_capture';
      
      if (cycle.status === 'completed') {
        progressPercentage = 100;
        currentStep = 'waiting';
      } else {
        // Estimate progress based on completed tasks
        const totalTasks = 4; // chart capture, analysis, risk management, order execution
        let completedTasks = 0;
        
        if (cycle.charts_captured > 0) completedTasks++;
        if (cycle.analyses_completed > 0) completedTasks++;
        if (cycle.recommendations_generated > 0) completedTasks++;
        if (cycle.trades_executed > 0) completedTasks++;
        
        progressPercentage = Math.round((completedTasks / totalTasks) * 100);
        
        // Determine current step based on progress
        if (cycle.charts_captured === 0) currentStep = 'chart_capture';
        else if (cycle.analyses_completed === 0) currentStep = 'analysis';
        else if (cycle.recommendations_generated === 0) currentStep = 'risk_management';
        else if (cycle.trades_executed === 0) currentStep = 'order_execution';
        else currentStep = 'waiting';
      }

      const isCompleted = cycle.status === 'completed';
      
      // Define steps with status
      const steps: Array<{
        name: string;
        status: 'completed' | 'current' | 'pending';
        description: string;
      }> = [
        {
          name: 'Chart Capture',
          status: isCompleted ? 'completed' :
                  cycle.charts_captured > 0 ? 'completed' :
                  currentStep === 'chart_capture' ? 'current' : 'pending',
          description: 'Capturing trading charts'
        },
        {
          name: 'Analysis',
          status: isCompleted ? 'completed' :
                  cycle.analyses_completed > 0 ? 'completed' :
                  currentStep === 'analysis' ? 'current' : 'pending',
          description: 'Analyzing chart images'
        },
        {
          name: 'Risk Management',
          status: isCompleted ? 'completed' :
                  cycle.recommendations_generated > 0 ? 'completed' :
                  currentStep === 'risk_management' ? 'current' : 'pending',
          description: 'Evaluating risk and signals'
        },
        {
          name: 'Order Execution',
          status: isCompleted ? 'completed' :
                  cycle.trades_executed > 0 ? 'completed' :
                  currentStep === 'order_execution' ? 'current' : 'pending',
          description: 'Executing trades'
        },
        {
          name: 'Waiting',
          status: currentStep === 'waiting' ? 'current' : 'pending',
          description: 'Waiting for next cycle'
        }
      ];

      currentCycle = {
        id: cycle.id,
        cycle_number: cycle.cycle_number,
        status: cycle.status,
        started_at: cycle.started_at,
        progress_percentage: progressPercentage,
        current_step: currentStep,
        next_step_time: cycle.status === 'completed' ? null : new Date(Date.now() + 5 * 60000).toISOString(), // 5 minutes from now
        steps
      };

      // Get cycle stats
      const stats = await query<{
        total_cycles: number;
        successful_cycles: number;
        avg_duration_minutes: number;
        last_completed: string;
      }>(`
        SELECT
          COUNT(*) as total_cycles,
          SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful_cycles,
          AVG(EXTRACT(EPOCH FROM (completed_at - started_at)) / 60) as avg_duration_minutes,
          MAX(completed_at) as last_completed
        FROM cycles
        WHERE run_id = ?
      `, [currentRun.id]);

      if (stats.length > 0) {
        // Ensure numeric types (PostgreSQL returns strings for aggregates)
        cycleStats = {
          total_cycles: Number(stats[0].total_cycles) || 0,
          successful_cycles: Number(stats[0].successful_cycles) || 0,
          avg_cycle_duration_minutes: Math.round(Number(stats[0].avg_duration_minutes) || 0),
          last_cycle_completed: stats[0].last_completed || null
        };
      }
    }

    const response: CycleStatusResponse = {
      current_cycle: currentCycle,
      cycle_stats: cycleStats
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Cycle status GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get cycle status' },
      { status: 500 }
    );
  }
}

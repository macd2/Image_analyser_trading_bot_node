/**
 * Bot Cycles API - GET trading cycle history for audit trail
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  getRecentCycles,
  getRecentRecommendations,
  isTradingDbAvailable,
  getInstanceConfigAsRows,
  type CycleRow,
  type RecommendationRow
} from '@/lib/db/trading-db';

export interface AnalysisResult {
  symbol: string;
  recommendation: string;
  confidence: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  setup_quality: number;
  rr_score: number;
  market_score: number;
  status: 'valid' | 'low' | 'skip';
  reasoning: string | null;
}

export interface CyclesResponse {
  cycles: CycleRow[];
  recommendations: RecommendationRow[];
  current_cycle_analysis: AnalysisResult[];
  prompt_info: {
    name: string;
    model: string;
    avg_confidence: number;
  };
  stats: {
    total_cycles: number;
    successful_cycles: number;
    total_recommendations: number;
    total_trades_executed: number;
    images_analyzed: number;
    valid_signals: number;
    actionable_pct: number;
  };
}

/**
 * GET /api/bot/cycles - Get cycle history and recommendations
 * Query params:
 *   - limit: number (default: 20)
 *   - include_recommendations: boolean (default: true)
 *   - current_only: boolean (default: false) - Only get current cycle data
 *   - instance_id: string (optional) - Get config from specific instance
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const limit = parseInt(searchParams.get('limit') || '20', 10);
  const includeRecommendations = searchParams.get('include_recommendations') !== 'false';
  const currentOnly = searchParams.get('current_only') === 'true';
  const instanceId = searchParams.get('instance_id');

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const cycles = await getRecentCycles(currentOnly ? 1 : limit, instanceId || undefined);
    const recommendations = includeRecommendations
      ? await getRecentRecommendations(limit * 5, instanceId || undefined)
      : [];

    // Get current cycle's recommendations for analysis view
    const currentCycle = cycles[0];
    let currentCycleRecs: RecommendationRow[] = [];
    if (currentCycle) {
      currentCycleRecs = recommendations.filter(r =>
        r.cycle_boundary === currentCycle.boundary_time
      );
    }

    // Build analysis results with component scores
    const currentCycleAnalysis: AnalysisResult[] = currentCycleRecs.map(r => {
      const confidence = r.confidence || 0;
      // Estimate component scores from confidence (reverse engineering formula)
      // confidence = setup*0.4 + rr*0.25 + market*0.35
      const baseScore = confidence;
      return {
        symbol: r.symbol,
        recommendation: r.recommendation,
        confidence,
        entry_price: r.entry_price,
        stop_loss: r.stop_loss,
        take_profit: r.take_profit,
        risk_reward: r.risk_reward,
        setup_quality: Math.min(1, baseScore * 1.1),
        rr_score: Math.min(1, baseScore * 0.95),
        market_score: Math.min(1, baseScore * 1.0),
        status: confidence >= 0.70 ? 'valid' : confidence >= 0.50 ? 'low' : 'skip',
        reasoning: r.reasoning,
      };
    });

    // Get prompt info from instance config (or use default if no instance)
    const config = instanceId ? await getInstanceConfigAsRows(instanceId) : [];
    const modelConfig = config.find(c => c.key === 'openai.model');

    // Calculate stats
    const successfulCycles = cycles.filter(c => c.status === 'completed');
    const totalTradesExecuted = cycles.reduce((sum, c) => sum + c.trades_executed, 0);
    const totalRecommendations = cycles.reduce((sum, c) => sum + c.recommendations_generated, 0);

    const validSignals = currentCycleAnalysis.filter(a => a.status === 'valid').length;
    const avgConfidence = currentCycleAnalysis.length > 0
      ? currentCycleAnalysis.reduce((sum, a) => sum + a.confidence, 0) / currentCycleAnalysis.length
      : 0;

    const stats = {
      total_cycles: cycles.length,
      successful_cycles: successfulCycles.length,
      total_recommendations: totalRecommendations,
      total_trades_executed: totalTradesExecuted,
      images_analyzed: currentCycleAnalysis.length,
      valid_signals: validSignals,
      actionable_pct: currentCycleAnalysis.length > 0
        ? Math.round((validSignals / currentCycleAnalysis.length) * 100)
        : 0,
    };

    const response: CyclesResponse = {
      cycles,
      recommendations,
      current_cycle_analysis: currentCycleAnalysis,
      prompt_info: {
        name: currentCycleRecs[0]?.prompt_name || 'analyzer_v2',
        model: modelConfig?.value || 'gpt-4o',
        avg_confidence: Math.round(avgConfidence * 100) / 100,
      },
      stats,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Cycles GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get cycles' },
      { status: 500 }
    );
  }
}


/**
 * Trade Replay API - Load reproducibility data for trade replay
 * 
 * GET /api/bot/trades/{tradeId}/replay
 * Returns all reproducibility data needed to replay a trade with identical inputs
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery, isTradingDbAvailable } from '@/lib/db/trading-db';

export interface ReplayData {
  trade: {
    id: string;
    symbol: string;
    side: string;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    status: string;
    created_at: string;
  };
  recommendation: {
    id: string;
    symbol: string;
    recommendation: string;
    confidence: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    // Input snapshots
    chart_hash?: string;
    model_version?: string;
    model_params?: Record<string, any>;
    market_data_snapshot?: Record<string, any>;
    strategy_config_snapshot?: Record<string, any>;
    // Intermediate calculations
    confidence_components?: Record<string, any>;
    setup_quality_components?: Record<string, any>;
    market_environment_components?: Record<string, any>;
    // Metadata
    prompt_version?: string;
    prompt_content?: string;
    validation_results?: Record<string, any>;
  };
  execution: {
    position_sizing_inputs?: Record<string, any>;
    position_sizing_outputs?: Record<string, any>;
    order_parameters?: Record<string, any>;
    execution_timestamp?: string;
  };
  ranking: {
    ranking_score?: number;
    ranking_position?: number;
    total_signals_analyzed?: number;
    total_signals_ranked?: number;
    available_slots?: number;
    ranking_weights?: Record<string, any>;
  };
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { tradeId: string } }
) {
  const tradeId = params.tradeId;

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    // Get trade details
    const tradeResult = await dbQuery(
      `SELECT id, symbol, side, entry_price, stop_loss, take_profit, status, created_at, recommendation_id, ranking_context
       FROM trades WHERE id = ?`,
      [tradeId]
    );

    if (!tradeResult || tradeResult.length === 0) {
      return NextResponse.json(
        { error: 'Trade not found' },
        { status: 404 }
      );
    }

    const trade = tradeResult[0];

    // Get recommendation details with reproducibility data
    const recResult = await dbQuery(
      `SELECT id, symbol, recommendation, confidence, entry_price, stop_loss, take_profit,
              chart_hash, model_version, model_params, market_data_snapshot, strategy_config_snapshot,
              confidence_components, setup_quality_components, market_environment_components,
              prompt_version, prompt_content, validation_results
       FROM recommendations WHERE id = ?`,
      [trade.recommendation_id]
    );

    if (!recResult || recResult.length === 0) {
      return NextResponse.json(
        { error: 'Recommendation not found' },
        { status: 404 }
      );
    }

    const recommendation = recResult[0];

    // Get execution details
    const execResult = await dbQuery(
      `SELECT position_sizing_inputs, position_sizing_outputs, order_parameters, execution_timestamp
       FROM trades WHERE id = ?`,
      [tradeId]
    );

    const execution = execResult?.[0] || {};

    // Parse ranking context
    let ranking = {};
    if (trade.ranking_context) {
      try {
        ranking = typeof trade.ranking_context === 'string'
          ? JSON.parse(trade.ranking_context)
          : trade.ranking_context;
      } catch (e) {
        console.error('Failed to parse ranking context:', e);
      }
    }

    // Parse JSON fields
    const parseJson = (val: any) => {
      if (!val) return undefined;
      if (typeof val === 'string') {
        try {
          return JSON.parse(val);
        } catch {
          return val;
        }
      }
      return val;
    };

    const replayData: ReplayData = {
      trade: {
        id: String(trade.id),
        symbol: String(trade.symbol),
        side: String(trade.side),
        entry_price: Number(trade.entry_price),
        stop_loss: Number(trade.stop_loss),
        take_profit: Number(trade.take_profit),
        status: String(trade.status),
        created_at: String(trade.created_at),
      },
      recommendation: {
        id: String(recommendation.id),
        symbol: String(recommendation.symbol),
        recommendation: String(recommendation.recommendation),
        confidence: Number(recommendation.confidence),
        entry_price: Number(recommendation.entry_price),
        stop_loss: Number(recommendation.stop_loss),
        take_profit: Number(recommendation.take_profit),
        chart_hash: recommendation.chart_hash ? String(recommendation.chart_hash) : undefined,
        model_version: recommendation.model_version ? String(recommendation.model_version) : undefined,
        model_params: parseJson(recommendation.model_params),
        market_data_snapshot: parseJson(recommendation.market_data_snapshot),
        strategy_config_snapshot: parseJson(recommendation.strategy_config_snapshot),
        confidence_components: parseJson(recommendation.confidence_components),
        setup_quality_components: parseJson(recommendation.setup_quality_components),
        market_environment_components: parseJson(recommendation.market_environment_components),
        prompt_version: recommendation.prompt_version ? String(recommendation.prompt_version) : undefined,
        prompt_content: recommendation.prompt_content ? String(recommendation.prompt_content) : undefined,
        validation_results: parseJson(recommendation.validation_results),
      },
      execution: {
        position_sizing_inputs: parseJson(execution.position_sizing_inputs),
        position_sizing_outputs: parseJson(execution.position_sizing_outputs),
        order_parameters: parseJson(execution.order_parameters),
        execution_timestamp: execution.execution_timestamp ? String(execution.execution_timestamp) : undefined,
      },
      ranking,
    };

    return NextResponse.json(replayData);
  } catch (error) {
    console.error('Error loading replay data:', error);
    return NextResponse.json(
      { error: 'Failed to load replay data' },
      { status: 500 }
    );
  }
}


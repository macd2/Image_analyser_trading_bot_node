/**
 * Trade Replay Analysis API - Execute replay and compare results
 * 
 * POST /api/bot/trades/{tradeId}/replay-analysis
 * Loads reproducibility data, replays analysis, and returns comparison
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import { dbQuery, isTradingDbAvailable } from '@/lib/db/trading-db';

export interface ReplayAnalysisResponse {
  trade_id: string;
  is_reproducible: boolean;
  similarity_score: number;
  differences: Array<{
    field: string;
    original: any;
    replayed: any;
  }>;
  original_recommendation: Record<string, any>;
  replayed_recommendation: Record<string, any>;
  error?: string;
}

async function executeReplay(replayData: Record<string, any>): Promise<any> {
  return new Promise((resolve, reject) => {
    const pythonProcess = spawn('python', [
      '-c',
      `
import sys
import json
sys.path.insert(0, 'python')

from trading_bot.engine.replay_engine import ReplayEngine
from trading_bot.strategies.prompt.prompt_strategy import PromptStrategy

replay_data = json.loads('''${JSON.stringify(replayData)}''')

try:
  engine = ReplayEngine()
  strategy = PromptStrategy()
  
  # Replay analysis
  replayed = engine.replay_analysis(strategy, replay_data)
  
  # Compare results
  original = replay_data.get('recommendation', {})
  comparison = engine.compare_results(original, replayed)
  
  result = {
    'is_reproducible': comparison['is_reproducible'],
    'similarity_score': comparison['similarity_score'],
    'differences': comparison['differences'],
    'original_recommendation': original,
    'replayed_recommendation': replayed,
  }
  
  print(json.dumps(result))
except Exception as e:
  print(json.dumps({'error': str(e)}))
  sys.exit(1)
`,
    ]);

    let output = '';
    let errorOutput = '';

    pythonProcess.stdout?.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr?.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(`Python process failed: ${errorOutput}`));
      } else {
        try {
          const result = JSON.parse(output);
          if (result.error) {
            reject(new Error(result.error));
          } else {
            resolve(result);
          }
        } catch (e) {
          reject(new Error(`Failed to parse replay result: ${e}`));
        }
      }
    });
  });
}

export async function POST(
  request: NextRequest,
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
      `SELECT id, symbol, recommendation_id FROM trades WHERE id = ?`,
      [tradeId]
    );

    if (!tradeResult || tradeResult.length === 0) {
      return NextResponse.json(
        { error: 'Trade not found' },
        { status: 404 }
      );
    }

    const trade = tradeResult[0];

    // Get recommendation with reproducibility data
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

    const replayData = {
      recommendation: {
        symbol: recommendation.symbol,
        recommendation: recommendation.recommendation,
        confidence: recommendation.confidence,
        entry_price: recommendation.entry_price,
        stop_loss: recommendation.stop_loss,
        take_profit: recommendation.take_profit,
        market_data_snapshot: parseJson(recommendation.market_data_snapshot),
        strategy_config_snapshot: parseJson(recommendation.strategy_config_snapshot),
      },
    };

    // Execute replay
    const replayResult = await executeReplay(replayData);

    const response: ReplayAnalysisResponse = {
      trade_id: tradeId,
      is_reproducible: replayResult.is_reproducible,
      similarity_score: replayResult.similarity_score,
      differences: replayResult.differences,
      original_recommendation: replayResult.original_recommendation,
      replayed_recommendation: replayResult.replayed_recommendation,
    };

    return NextResponse.json(response);
  } catch (error) {
    console.error('Error executing replay analysis:', error);
    return NextResponse.json(
      { error: 'Failed to execute replay analysis', details: String(error) },
      { status: 500 }
    );
  }
}


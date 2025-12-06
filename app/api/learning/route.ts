/**
 * Learning API - Returns backtest/prompt performance data
 */

import { NextResponse } from 'next/server';
import { 
  getPromptStats, 
  getSymbolStats, 
  getTimeframeStats, 
  getConfidenceBuckets,
  getSummaryStats 
} from '@/lib/db/queries';
import { generateInsights } from '@/lib/db/insights';
import { getDatabaseInfo, isDatabaseAvailable } from '@/lib/db/client';
import type { LearningData } from '@/types/learning';

export async function GET() {
  try {
    // Check if database is available
    if (!isDatabaseAvailable()) {
      const dbInfo = getDatabaseInfo();
      return NextResponse.json(
        { 
          error: 'Database not available',
          dbInfo,
          message: 'Ensure backtests.db exists at the configured path'
        },
        { status: 503 }
      );
    }

    // Fetch all data in parallel
    const [prompts, symbols, timeframes, confidenceBuckets, summary] = await Promise.all([
      getPromptStats(),
      getSymbolStats(),
      getTimeframeStats(),
      getConfidenceBuckets(),
      getSummaryStats(),
    ]);

    // Generate insights from data
    const insights = generateInsights(prompts, symbols, confidenceBuckets);

    const data: LearningData = {
      prompts,
      symbols,
      timeframes,
      confidenceBuckets,
      insights,
      lastUpdated: new Date().toISOString(),
    };

    return NextResponse.json({ 
      success: true, 
      data,
      summary,
    });
  } catch (error) {
    console.error('Learning API error:', error);
    return NextResponse.json(
      { 
        error: 'Failed to fetch learning data',
        message: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    );
  }
}


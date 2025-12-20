/**
 * Bot Trade Detail API - GET a single trade by ID
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  isTradingDbAvailable,
  dbQuery,
  type TradeRow
} from '@/lib/db/trading-db';

/**
 * GET /api/bot/trades/[tradeId] - Get a single trade by ID
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: { tradeId: string } }
) {
  const { tradeId } = params;

  if (!tradeId) {
    return NextResponse.json(
      { error: 'Trade ID is required' },
      { status: 400 }
    );
  }

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const trade = await dbQuery<TradeRow>(`
      SELECT * FROM trades WHERE id = ?
    `, [tradeId]);

    if (!trade || trade.length === 0) {
      return NextResponse.json(
        { error: 'Trade not found' },
        { status: 404 }
      );
    }

    const tradeData = trade[0];

    // Parse strategy_metadata if it's a string
    if (tradeData.strategy_metadata && typeof tradeData.strategy_metadata === 'string') {
      try {
        tradeData.strategy_metadata = JSON.parse(tradeData.strategy_metadata);
      } catch (e) {
        console.error('Failed to parse strategy_metadata:', e);
      }
    }

    return NextResponse.json(tradeData);
  } catch (error) {
    console.error('Trade detail GET error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to fetch trade' },
      { status: 500 }
    );
  }
}


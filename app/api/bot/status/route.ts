/**
 * Bot Status API - GET current bot config status (mode, slots, last_cycle)
 *
 * NOTE: Wallet and positions come from WebSocket (useRealtime hook), not this API.
 * This endpoint only returns config/database info that doesn't change frequently.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getInstanceById, dbQueryOne } from '@/lib/db/trading-db';

// Helper to get instance
async function getInstance(instanceId: string) {
  return getInstanceById(instanceId);
}

// Helper to get last cycle for instance (cycles -> runs -> instance)
async function getLastCycle(instanceId: string) {
  return dbQueryOne<{ started_at: string }>(
    `SELECT c.started_at FROM cycles c
     JOIN runs r ON c.run_id = r.id
     WHERE r.instance_id = ?
     ORDER BY c.started_at DESC LIMIT 1`,
    [instanceId]
  );
}

export interface BotStatus {
  running: boolean;
  mode: 'paper' | 'live';
  network: 'testnet' | 'mainnet';
  slots: {
    used: number;
    max: number;
    available: number;
  };
  last_cycle: string | null;
  error: string | null;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id') || '';

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id is required' },
        { status: 400 }
      );
    }

    // Get instance settings from database
    const instance = await getInstance(instanceId);
    if (!instance) {
      return NextResponse.json(
        { error: 'Instance not found' },
        { status: 404 }
      );
    }

    // Parse settings
    const settings = typeof instance.settings === 'string'
      ? JSON.parse(instance.settings || '{}')
      : (instance.settings || {});

    const isPaperTrading = settings.paper_trading === true || settings.paper_trading === 'true';
    const maxTrades = parseInt(settings.max_concurrent_trades) || 3;

    // Get last cycle
    const lastCycle = await getLastCycle(instanceId);

    // Return lightweight status (wallet/positions come from WebSocket)
    const status: BotStatus = {
      running: false, // Updated by process monitor via WebSocket
      mode: isPaperTrading ? 'paper' : 'live',
      network: 'mainnet',
      slots: {
        used: 0, // Updated from WebSocket positions
        max: maxTrades,
        available: maxTrades,
      },
      last_cycle: lastCycle?.started_at || null,
      error: null,
    };

    return NextResponse.json(status);
  } catch (error) {
    console.error('[Status API] Error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}


/**
 * Bot Config API - GET/PATCH instance-specific settings
 *
 * All config operations require an instance_id:
 * - GET /api/bot/config?instance_id=xxx - Get instance config
 * - PATCH /api/bot/config with instance_id in body - Update instance config
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  isTradingDbAvailable,
  getInstanceConfigAsRows,
  updateInstanceSettings,
  type ConfigRow
} from '@/lib/db/trading-db';

export interface ConfigResponse {
  config: ConfigRow[];
  categories: string[];
  instance_id: string;
}

/**
 * GET /api/bot/config?instance_id=xxx - Get instance config
 * Query params:
 * - instance_id: REQUIRED - the instance to get config for
 * - category: optional filter by category
 */
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const category = searchParams.get('category');
  const instanceId = searchParams.get('instance_id');

  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id is required. Select an instance first.' },
        { status: 400 }
      );
    }

    let config = await getInstanceConfigAsRows(instanceId);

    if (config.length === 0) {
      return NextResponse.json(
        { error: `Instance ${instanceId} not found or has no settings` },
        { status: 404 }
      );
    }

    if (category) {
      config = config.filter(c => c.category === category);
    }

    const categories = [...new Set(config.map(c => c.category))];

    return NextResponse.json({
      config,
      categories,
      instance_id: instanceId,
    });
  } catch (error) {
    console.error('Config GET error:', error);
    return NextResponse.json(
      { error: 'Failed to get config' },
      { status: 500 }
    );
  }
}

/**
 * PATCH /api/bot/config - Update instance config values
 * Body: { updates: [{ key: string, value: string }], instance_id: string }
 * instance_id is REQUIRED
 */
export async function PATCH(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json(
        { error: 'Trading database not available' },
        { status: 503 }
      );
    }

    const body = await request.json();
    const { updates, instance_id: instanceId } = body as {
      updates: Array<{ key: string; value: string }>;
      instance_id?: string;
    };

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id is required. Select an instance first.' },
        { status: 400 }
      );
    }

    if (!updates || !Array.isArray(updates)) {
      return NextResponse.json(
        { error: 'Invalid request body. Expected { updates: [{ key, value }], instance_id }' },
        { status: 400 }
      );
    }

    let updated = 0;
    const failed: string[] = [];

    const success = await updateInstanceSettings(instanceId, updates);
    if (success) {
      updated = updates.length;
    } else {
      failed.push(...updates.map(u => u.key));
    }

    const config = await getInstanceConfigAsRows(instanceId);
    const categories = [...new Set(config.map(c => c.category))];

    return NextResponse.json({
      updated,
      failed,
      config,
      categories,
      instance_id: instanceId,
    });
  } catch (error) {
    console.error('Config PATCH error:', error);
    return NextResponse.json(
      { error: 'Failed to update config' },
      { status: 500 }
    );
  }
}


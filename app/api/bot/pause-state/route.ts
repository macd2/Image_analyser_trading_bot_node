/**
 * Bot Pause State API
 * Handles OpenAI rate limit pause state and user confirmation
 */

import { NextRequest, NextResponse } from 'next/server';
import { dbQuery } from '@/lib/db/trading-db';

interface PauseState {
  is_paused: boolean;
  pause_reason?: string;
  error_message?: string;
  user_confirmed: boolean;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id');

    if (!instanceId) {
      return NextResponse.json(
        { error: 'instance_id required' },
        { status: 400 }
      );
    }

    // Check for recent OpenAI 429 error in error_logs
    const errors = await dbQuery<any>(`
      SELECT id, message, timestamp FROM error_logs
      WHERE message LIKE '%OpenAI API rate limit exceeded (429)%'
        AND timestamp > datetime('now', '-5 minutes')
      ORDER BY timestamp DESC
      LIMIT 1
    `);

    const isPaused = errors.length > 0;
    const pauseState: PauseState = {
      is_paused: isPaused,
      user_confirmed: false,
    };

    if (isPaused) {
      pauseState.pause_reason = 'openai_rate_limit';
      pauseState.error_message = 'OpenAI API rate limit exceeded (429). Please recharge your credits and confirm.';
    }

    return NextResponse.json(pauseState);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error('[Pause State API] Error:', errorMsg);

    return NextResponse.json(
      { error: 'Failed to check pause state', is_paused: false, user_confirmed: false },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const instanceId = searchParams.get('instance_id');
    const action = searchParams.get('action'); // 'confirm' or 'clear'

    if (!instanceId || !action) {
      return NextResponse.json(
        { error: 'instance_id and action required' },
        { status: 400 }
      );
    }

    if (action === 'confirm') {
      // User confirmed that credits have been recharged
      // Log this confirmation to error_logs for audit trail
      const timestamp = new Date().toISOString();
      
      await dbQuery(`
        INSERT INTO error_logs (
          id, timestamp, level, component, message, event
        ) VALUES (?, ?, ?, ?, ?, ?)
      `, [
        Math.random().toString(36).substr(2, 9),
        timestamp,
        'INFO',
        'pause_state',
        'User confirmed OpenAI rate limit resolved - resuming bot',
        'openai_rate_limit_acknowledged'
      ]);

      return NextResponse.json({
        success: true,
        message: 'Confirmation recorded - bot will resume',
        is_paused: false,
        user_confirmed: true,
      });
    }

    return NextResponse.json(
      { error: 'Invalid action' },
      { status: 400 }
    );
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.error('[Pause State API] POST Error:', errorMsg);

    return NextResponse.json(
      { error: 'Failed to process confirmation' },
      { status: 500 }
    );
  }
}


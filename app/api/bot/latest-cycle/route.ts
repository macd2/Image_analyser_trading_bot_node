import { NextRequest, NextResponse } from 'next/server'
import { dbQueryOne, isTradingDbAvailable } from '@/lib/db/trading-db'

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const { searchParams } = new URL(request.url)
    const instanceId = searchParams.get('instance_id')

    if (!instanceId) {
      return NextResponse.json({ error: 'instance_id is required' }, { status: 400 })
    }

    // Get the latest cycle for this instance
    const latestCycle = await dbQueryOne<{ id: string }>(`
      SELECT c.id FROM cycles c
      JOIN runs r ON c.run_id = r.id
      WHERE r.instance_id = ?
      ORDER BY c.started_at DESC
      LIMIT 1
    `, [instanceId])

    if (!latestCycle) {
      return NextResponse.json({ error: 'No cycles found for this instance' }, { status: 404 })
    }

    return NextResponse.json({ cycle_id: latestCycle.id })
  } catch (error) {
    console.error('Failed to fetch latest cycle:', error)
    return NextResponse.json({ error: 'Failed to fetch latest cycle' }, { status: 500 })
  }
}


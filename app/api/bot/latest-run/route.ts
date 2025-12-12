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

    // Get the latest run for this instance
    const latestRun = await dbQueryOne<{ id: string }>(`
      SELECT id FROM runs
      WHERE instance_id = ?
      ORDER BY started_at DESC
      LIMIT 1
    `, [instanceId])

    if (!latestRun) {
      return NextResponse.json({ error: 'No runs found for this instance' }, { status: 404 })
    }

    return NextResponse.json({ run_id: latestRun.id })
  } catch (error) {
    console.error('Failed to fetch latest run:', error)
    return NextResponse.json({ error: 'Failed to fetch latest run' }, { status: 500 })
  }
}


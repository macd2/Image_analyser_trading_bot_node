import { NextRequest, NextResponse } from 'next/server'
import { getRunInstanceStats, isTradingDbAvailable } from '@/lib/db/trading-db'

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const { searchParams } = new URL(request.url)
    const runId = searchParams.get('run_id')

    if (!runId) {
      return NextResponse.json({ error: 'run_id is required' }, { status: 400 })
    }

    const stats = await getRunInstanceStats(runId)
    return NextResponse.json(stats)
  } catch (error) {
    console.error('Failed to fetch run stats:', error)
    return NextResponse.json({ error: 'Failed to fetch run stats' }, { status: 500 })
  }
}


import { NextRequest, NextResponse } from 'next/server'
import { getCycleInstanceStats, isTradingDbAvailable } from '@/lib/db/trading-db'

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const { searchParams } = new URL(request.url)
    const cycleId = searchParams.get('cycle_id')

    if (!cycleId) {
      return NextResponse.json({ error: 'cycle_id is required' }, { status: 400 })
    }

    const stats = await getCycleInstanceStats(cycleId)
    return NextResponse.json(stats)
  } catch (error) {
    console.error('Failed to fetch cycle stats:', error)
    return NextResponse.json({ error: 'Failed to fetch cycle stats' }, { status: 500 })
  }
}


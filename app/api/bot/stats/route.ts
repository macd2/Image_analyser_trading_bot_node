import { NextRequest, NextResponse } from 'next/server'
import {
  getStatsByCycleId,
  getStatsByRunId,
  getStatsByInstanceId,
  getGlobalStats,
  isTradingDbAvailable
} from '@/lib/db/trading-db'

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const { searchParams } = new URL(request.url)
    const scope = searchParams.get('scope') || 'global'
    const id = searchParams.get('id')

    let stats

    switch (scope) {
      case 'cycle':
        if (!id) {
          return NextResponse.json({ error: 'Cycle ID required' }, { status: 400 })
        }
        stats = await getStatsByCycleId(id)
        break

      case 'run':
        if (!id) {
          return NextResponse.json({ error: 'Run ID required' }, { status: 400 })
        }
        stats = await getStatsByRunId(id)
        break

      case 'instance':
        if (!id) {
          return NextResponse.json({ error: 'Instance ID required' }, { status: 400 })
        }
        stats = await getStatsByInstanceId(id)
        break

      case 'global':
      default:
        stats = await getGlobalStats()
        break
    }

    return NextResponse.json({ stats, scope, id })
  } catch (error) {
    console.error('Failed to fetch stats:', error)
    return NextResponse.json({ error: 'Failed to fetch stats' }, { status: 500 })
  }
}


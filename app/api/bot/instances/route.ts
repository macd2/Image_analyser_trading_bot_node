import { NextRequest, NextResponse } from 'next/server'
import { getInstancesWithStatus, getInstancesWithSummary, createInstance, updateInstance, isTradingDbAvailable } from '@/lib/db/trading-db'
import { v4 as uuidv4 } from 'uuid'

export async function GET(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const { searchParams } = new URL(request.url)
    const includeSummary = searchParams.get('summary') === 'true'

    // Get instances with optional summary data (stats + config)
    const instances = includeSummary
      ? await getInstancesWithSummary()
      : await getInstancesWithStatus()

    return NextResponse.json({ instances })
  } catch (error) {
    console.error('Failed to fetch instances:', error)
    return NextResponse.json({ error: 'Failed to fetch instances' }, { status: 500 })
  }
}

export async function POST(request: Request) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const body = await request.json()
    const { name, prompt_name, prompt_version, min_confidence, max_leverage, symbols, timeframe, settings } = body

    if (!name) {
      return NextResponse.json({ error: 'Instance name is required' }, { status: 400 })
    }

    const id = uuidv4()
    await createInstance({
      id,
      name,
      prompt_name: prompt_name || null,
      prompt_version: prompt_version || null,
      min_confidence: min_confidence || null,
      max_leverage: max_leverage || null,
      symbols: symbols ? JSON.stringify(symbols) : null,
      timeframe: timeframe || null,
      settings: settings ? JSON.stringify(settings) : null,
      is_active: 1,
    })

    return NextResponse.json({ id, success: true })
  } catch (error) {
    console.error('Failed to create instance:', error)
    return NextResponse.json({ error: 'Failed to create instance' }, { status: 500 })
  }
}

export async function PATCH(request: NextRequest) {
  try {
    if (!await isTradingDbAvailable()) {
      return NextResponse.json({ error: 'Trading database not available' }, { status: 503 })
    }

    const body = await request.json()
    const { id, ...updates } = body

    if (!id) {
      return NextResponse.json({ error: 'Instance ID is required' }, { status: 400 })
    }

    // Build updates object with only provided fields
    const instanceUpdates: Record<string, unknown> = {}
    if (updates.name !== undefined) instanceUpdates.name = updates.name.trim()
    if (updates.prompt_name !== undefined) instanceUpdates.prompt_name = updates.prompt_name
    if (updates.prompt_version !== undefined) instanceUpdates.prompt_version = updates.prompt_version
    if (updates.min_confidence !== undefined) instanceUpdates.min_confidence = updates.min_confidence
    if (updates.max_leverage !== undefined) instanceUpdates.max_leverage = updates.max_leverage
    if (updates.symbols !== undefined) instanceUpdates.symbols = JSON.stringify(updates.symbols)
    if (updates.timeframe !== undefined) instanceUpdates.timeframe = updates.timeframe

    if (Object.keys(instanceUpdates).length === 0) {
      return NextResponse.json({ error: 'No valid updates provided' }, { status: 400 })
    }

    await updateInstance(id, instanceUpdates)

    // Return updated instance
    const instances = await getInstancesWithStatus()
    const updated = instances.find((i: { id: string }) => i.id === id)

    return NextResponse.json({ success: true, instance: updated })
  } catch (error) {
    console.error('Failed to update instance:', error)
    return NextResponse.json({ error: 'Failed to update instance' }, { status: 500 })
  }
}


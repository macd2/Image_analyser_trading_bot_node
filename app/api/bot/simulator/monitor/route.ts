/**
 * Paper Trade Monitor Status API
 * Stores settings in database (persisted), runtime status in JSON file (ephemeral)
 */

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'
import { getSettings, saveSettings } from '@/lib/db/settings'

// JSON file for runtime status only (not persisted across restarts)
const STATUS_FILE = path.join(process.cwd(), 'data', 'simulator_status.json')

// Per-timeframe max open bars configuration
type MaxOpenBarsConfig = Record<string, number>  // e.g. { "1h": 24, "4h": 12, "1d": 5 }

// Database settings key
const SIMULATOR_SETTINGS_KEY = 'simulator'

// Settings stored in database (persisted)
interface SimulatorSettings {
  max_open_bars: MaxOpenBarsConfig
}

// Runtime status stored in file (ephemeral)
interface RuntimeStatus {
  running: boolean
  last_check: string | null
  trades_checked: number
  trades_closed: number
  trades_cancelled?: number
  next_check: number | null
  results: Array<{
    trade_id: string
    symbol: string
    action: 'checked' | 'closed' | 'cancelled'
    current_price: number
    instance_name?: string
    checked_at?: string
    exit_reason?: string
    pnl?: number
    bars_open?: number
  }>
}

// Combined status returned to frontend
interface MonitorStatus extends RuntimeStatus {
  max_open_bars?: MaxOpenBarsConfig
}

// Default per-timeframe max open bars (0 = disabled)
const DEFAULT_MAX_OPEN_BARS: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

// Get settings from database (persisted)
async function getSimulatorSettings(): Promise<SimulatorSettings> {
  try {
    const settings = await getSettings<SimulatorSettings>(SIMULATOR_SETTINGS_KEY)
    return {
      max_open_bars: { ...DEFAULT_MAX_OPEN_BARS, ...(settings?.max_open_bars || {}) }
    }
  } catch (e) {
    console.error('Failed to read simulator settings from DB:', e)
    return { max_open_bars: { ...DEFAULT_MAX_OPEN_BARS } }
  }
}

// Save settings to database (persisted)
async function saveSimulatorSettings(settings: Partial<SimulatorSettings>): Promise<void> {
  try {
    const existing = await getSimulatorSettings()
    await saveSettings(SIMULATOR_SETTINGS_KEY, { ...existing, ...settings })
  } catch (e) {
    console.error('Failed to save simulator settings to DB:', e)
    throw e
  }
}

// Get runtime status from file (ephemeral)
function getRuntimeStatus(): RuntimeStatus {
  try {
    if (fs.existsSync(STATUS_FILE)) {
      const data = JSON.parse(fs.readFileSync(STATUS_FILE, 'utf-8'))
      return {
        running: data.running ?? false,
        last_check: data.last_check ?? null,
        trades_checked: data.trades_checked ?? 0,
        trades_closed: data.trades_closed ?? 0,
        trades_cancelled: data.trades_cancelled ?? 0,
        next_check: data.next_check ?? null,
        results: data.results ?? []
      }
    }
  } catch (e) {
    console.error('Failed to read status file:', e)
  }
  return {
    running: false,
    last_check: null,
    trades_checked: 0,
    trades_closed: 0,
    trades_cancelled: 0,
    next_check: null,
    results: []
  }
}

// Save runtime status to file (ephemeral)
function saveRuntimeStatus(status: RuntimeStatus): void {
  try {
    const dir = path.dirname(STATUS_FILE)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    fs.writeFileSync(STATUS_FILE, JSON.stringify(status, null, 2))
  } catch (e) {
    console.error('Failed to save status file:', e)
  }
}

// Get combined status (settings from DB + runtime from file)
async function getStatus(): Promise<MonitorStatus> {
  const settings = await getSimulatorSettings()
  const runtime = getRuntimeStatus()
  return {
    ...runtime,
    max_open_bars: settings.max_open_bars
  }
}

export async function GET() {
  const status = await getStatus()
  return NextResponse.json(status, {
    headers: {
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      'Pragma': 'no-cache'
    }
  })
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { action, results, trades_checked, trades_closed } = body

    if (action === 'start') {
      const runtime = getRuntimeStatus()
      runtime.running = true
      saveRuntimeStatus(runtime)

      return NextResponse.json({
        success: true,
        message: 'Monitor started'
      })

    } else if (action === 'stop') {
      const runtime = getRuntimeStatus()
      runtime.running = false
      runtime.next_check = null
      saveRuntimeStatus(runtime)

      return NextResponse.json({
        success: true,
        message: 'Monitor stopped'
      })

    } else if (action === 'update') {
      // Called by the frontend to update status after an auto-close check
      const runtime = getRuntimeStatus()
      runtime.last_check = new Date().toISOString()
      runtime.trades_checked = trades_checked || 0
      runtime.trades_closed = trades_closed || 0
      runtime.results = results || []
      if (runtime.running) {
        runtime.next_check = Date.now() / 1000 + 10 // Next check in 10 seconds
      }
      saveRuntimeStatus(runtime)

      const status = await getStatus()
      return NextResponse.json({
        success: true,
        ...status
      })

    } else if (action === 'force-run') {
      // Force run auto-close immediately
      const protocol = request.headers.get('x-forwarded-proto') || 'http'
      const host = request.headers.get('host') || 'localhost:3000'
      const baseUrl = `${protocol}://${host}`

      try {
        const res = await fetch(`${baseUrl}/api/bot/simulator/auto-close`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })

        if (res.ok) {
          const data = await res.json()
          const runtime = getRuntimeStatus()
          runtime.last_check = new Date().toISOString()
          runtime.trades_checked = data.checked || 0
          runtime.trades_closed = data.closed || 0
          runtime.results = data.results || []
          runtime.next_check = Date.now() / 1000 + 30
          saveRuntimeStatus(runtime)

          return NextResponse.json({
            success: true,
            message: 'Forced auto-close run',
            ...data
          })
        }
      } catch (err) {
        return NextResponse.json({
          success: false,
          error: 'Failed to run auto-close',
          details: String(err)
        }, { status: 500 })
      }

      return NextResponse.json({
        success: false,
        error: 'Auto-close returned non-ok response'
      }, { status: 500 })

    } else if (action === 'set-max-bars') {
      // Update max_open_bars setting in DATABASE (persisted across restarts)
      // Can receive: { timeframe: "1h", max_bars: 24 } OR { max_open_bars: { "1h": 24, "4h": 12 } }
      const { max_open_bars, timeframe, max_bars } = body
      const currentSettings = await getSimulatorSettings()

      let updatedMaxBars = { ...currentSettings.max_open_bars }

      if (timeframe && typeof max_bars === 'number') {
        // Update single timeframe
        updatedMaxBars[timeframe] = max_bars
      } else if (typeof max_open_bars === 'object' && max_open_bars !== null) {
        // Update multiple timeframes at once
        updatedMaxBars = { ...updatedMaxBars, ...max_open_bars }
      }

      // Save to database (persisted)
      await saveSimulatorSettings({ max_open_bars: updatedMaxBars })

      return NextResponse.json({
        success: true,
        message: timeframe
          ? `Max open bars for ${timeframe} set to ${max_bars}`
          : 'Max open bars updated',
        max_open_bars: updatedMaxBars
      })

    } else {
      return NextResponse.json(
        { error: 'Invalid action. Use "start", "stop", "update", "force-run", or "set-max-bars"' },
        { status: 400 }
      )
    }
  } catch (error) {
    console.error('Error controlling monitor:', error)
    return NextResponse.json(
      { error: 'Failed to control monitor' },
      { status: 500 }
    )
  }
}


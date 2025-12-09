/**
 * Paper Trade Monitor Status API
 * Uses in-memory state stored in global, no Python needed
 */

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

// Store status in a JSON file since Next.js API routes are stateless
const STATUS_FILE = path.join(process.cwd(), 'data', 'simulator_status.json')

// Per-timeframe max open bars configuration
type MaxOpenBarsConfig = Record<string, number>  // e.g. { "1h": 24, "4h": 12, "1d": 5 }

interface MonitorStatus {
  running: boolean
  last_check: string | null
  trades_checked: number
  trades_closed: number
  trades_cancelled?: number
  next_check: number | null
  // Simulator settings - per-timeframe max open bars (0 = disabled for that timeframe)
  max_open_bars?: MaxOpenBarsConfig
  results: Array<{
    trade_id: string
    symbol: string
    action: 'checked' | 'closed' | 'cancelled'
    current_price: number
    checked_at?: string
    exit_reason?: string
    pnl?: number
    bars_open?: number
  }>
}

// Default per-timeframe max open bars (0 = disabled)
const DEFAULT_MAX_OPEN_BARS: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

function getStatus(): MonitorStatus {
  try {
    if (fs.existsSync(STATUS_FILE)) {
      const data = JSON.parse(fs.readFileSync(STATUS_FILE, 'utf-8'))
      // Ensure max_open_bars has default values for all timeframes
      return {
        ...data,
        max_open_bars: { ...DEFAULT_MAX_OPEN_BARS, ...(data.max_open_bars || {}) }
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
    max_open_bars: { ...DEFAULT_MAX_OPEN_BARS },
    results: []
  }
}

function saveStatus(status: MonitorStatus) {
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

export async function GET() {
  const status = getStatus()
  return NextResponse.json(status)
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { action, results, trades_checked, trades_closed } = body

    if (action === 'start') {
      const status = getStatus()
      status.running = true
      saveStatus(status)

      return NextResponse.json({
        success: true,
        message: 'Monitor started'
      })

    } else if (action === 'stop') {
      const status = getStatus()
      status.running = false
      status.next_check = null
      saveStatus(status)

      return NextResponse.json({
        success: true,
        message: 'Monitor stopped'
      })

    } else if (action === 'update') {
      // Called by the frontend to update status after an auto-close check
      const status = getStatus()
      status.last_check = new Date().toISOString()
      status.trades_checked = trades_checked || 0
      status.trades_closed = trades_closed || 0
      status.results = results || []
      if (status.running) {
        status.next_check = Date.now() / 1000 + 10 // Next check in 10 seconds
      }
      saveStatus(status)

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
          const updated = getStatus()
          updated.last_check = new Date().toISOString()
          updated.trades_checked = data.checked || 0
          updated.trades_closed = data.closed || 0
          updated.results = data.results || []
          updated.next_check = Date.now() / 1000 + 30
          saveStatus(updated)

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
      // Update max_open_bars setting - supports per-timeframe config
      // Can receive: { timeframe: "1h", max_bars: 24 } OR { max_open_bars: { "1h": 24, "4h": 12 } }
      const { max_open_bars, timeframe, max_bars } = body
      const status = getStatus()

      if (timeframe && typeof max_bars === 'number') {
        // Update single timeframe
        status.max_open_bars = {
          ...status.max_open_bars,
          [timeframe]: max_bars
        }
      } else if (typeof max_open_bars === 'object' && max_open_bars !== null) {
        // Update multiple timeframes at once
        status.max_open_bars = {
          ...status.max_open_bars,
          ...max_open_bars
        }
      }

      saveStatus(status)

      return NextResponse.json({
        success: true,
        message: timeframe
          ? `Max open bars for ${timeframe} set to ${max_bars}`
          : 'Max open bars updated',
        max_open_bars: status.max_open_bars
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


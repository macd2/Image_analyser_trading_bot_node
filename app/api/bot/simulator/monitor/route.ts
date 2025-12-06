/**
 * Paper Trade Monitor Status API
 * Uses in-memory state stored in global, no Python needed
 */

import { NextRequest, NextResponse } from 'next/server'
import fs from 'fs'
import path from 'path'

// Store status in a JSON file since Next.js API routes are stateless
const STATUS_FILE = path.join(process.cwd(), 'data', 'simulator_status.json')

interface MonitorStatus {
  running: boolean
  last_check: string | null
  trades_checked: number
  trades_closed: number
  next_check: number | null
  results: Array<{
    trade_id: string
    symbol: string
    action: 'checked' | 'closed'
    current_price: number
    checked_at?: string
    exit_reason?: string
    pnl?: number
  }>
}

function getStatus(): MonitorStatus {
  try {
    if (fs.existsSync(STATUS_FILE)) {
      return JSON.parse(fs.readFileSync(STATUS_FILE, 'utf-8'))
    }
  } catch (e) {
    console.error('Failed to read status file:', e)
  }
  return {
    running: false,
    last_check: null,
    trades_checked: 0,
    trades_closed: 0,
    next_check: null,
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

    } else {
      return NextResponse.json(
        { error: 'Invalid action. Use "start", "stop", or "update"' },
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


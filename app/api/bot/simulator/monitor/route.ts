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
  max_open_bars_before_filled: MaxOpenBarsConfig  // Max bars for pending trades (before filled) - GLOBAL FALLBACK
  max_open_bars_after_filled: MaxOpenBarsConfig   // Max bars for filled trades (before cancelled) - GLOBAL FALLBACK
  // Strategy-type-specific settings (override global if present)
  max_open_bars_before_filled_price_based?: MaxOpenBarsConfig  // Price-based strategy pending trades
  max_open_bars_after_filled_price_based?: MaxOpenBarsConfig   // Price-based strategy filled trades
  max_open_bars_before_filled_spread_based?: MaxOpenBarsConfig // Spread-based strategy pending trades
  max_open_bars_after_filled_spread_based?: MaxOpenBarsConfig  // Spread-based strategy filled trades
  use_fixed_capital?: boolean                      // Use fixed capital instead of Bybit balance
  fixed_capital_usd?: number                       // Fixed capital amount in USD
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
    strategy_name?: string
    timeframe?: string
    checked_at?: string
    exit_reason?: string
    pnl?: number
    bars_open?: number
    position_size_usd?: number
    risk_amount_usd?: number
  }>
}

// Combined status returned to frontend
interface MonitorStatus extends RuntimeStatus {
  // Global settings (fallback)
  max_open_bars_before_filled?: MaxOpenBarsConfig
  max_open_bars_after_filled?: MaxOpenBarsConfig
  // Strategy-type-specific settings
  max_open_bars_before_filled_price_based?: MaxOpenBarsConfig
  max_open_bars_after_filled_price_based?: MaxOpenBarsConfig
  max_open_bars_before_filled_spread_based?: MaxOpenBarsConfig
  max_open_bars_after_filled_spread_based?: MaxOpenBarsConfig
  // Other settings
  use_fixed_capital?: boolean
  fixed_capital_usd?: number
}

// Default per-timeframe max open bars (0 = no cancellation)
// GLOBAL DEFAULTS - used as fallback when strategy-type-specific settings not configured
const DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

const DEFAULT_MAX_OPEN_BARS_AFTER_FILLED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

// PRICE-BASED STRATEGY DEFAULTS
const DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_PRICE_BASED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

const DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_PRICE_BASED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

// SPREAD-BASED STRATEGY DEFAULTS
const DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_SPREAD_BASED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

const DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_SPREAD_BASED: MaxOpenBarsConfig = {
  '1m': 0, '3m': 0, '5m': 0, '15m': 0, '30m': 0,
  '1h': 0, '2h': 0, '4h': 0, '6h': 0, '12h': 0,
  '1d': 0, '1D': 0
}

// Get settings from database (persisted)
async function getSimulatorSettings(): Promise<SimulatorSettings> {
  try {
    const settings = await getSettings<SimulatorSettings>(SIMULATOR_SETTINGS_KEY)

    return {
      // Global settings (fallback)
      max_open_bars_before_filled: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED, ...(settings?.max_open_bars_before_filled || {}) },
      max_open_bars_after_filled: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED, ...(settings?.max_open_bars_after_filled || {}) },
      // Strategy-type-specific settings (override global if present)
      max_open_bars_before_filled_price_based: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_PRICE_BASED, ...(settings?.max_open_bars_before_filled_price_based || {}) },
      max_open_bars_after_filled_price_based: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_PRICE_BASED, ...(settings?.max_open_bars_after_filled_price_based || {}) },
      max_open_bars_before_filled_spread_based: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_SPREAD_BASED, ...(settings?.max_open_bars_before_filled_spread_based || {}) },
      max_open_bars_after_filled_spread_based: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_SPREAD_BASED, ...(settings?.max_open_bars_after_filled_spread_based || {}) },
      // Other settings
      use_fixed_capital: settings?.use_fixed_capital ?? false,
      fixed_capital_usd: settings?.fixed_capital_usd ?? 10000
    }
  } catch (e) {
    console.error('Failed to read simulator settings from DB:', e)
    return {
      // Global settings (fallback)
      max_open_bars_before_filled: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED },
      max_open_bars_after_filled: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED },
      // Strategy-type-specific settings (defaults)
      max_open_bars_before_filled_price_based: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_PRICE_BASED },
      max_open_bars_after_filled_price_based: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_PRICE_BASED },
      max_open_bars_before_filled_spread_based: { ...DEFAULT_MAX_OPEN_BARS_BEFORE_FILLED_SPREAD_BASED },
      max_open_bars_after_filled_spread_based: { ...DEFAULT_MAX_OPEN_BARS_AFTER_FILLED_SPREAD_BASED },
      // Other settings
      use_fixed_capital: false,
      fixed_capital_usd: 10000
    }
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
    // Global settings
    max_open_bars_before_filled: settings.max_open_bars_before_filled,
    max_open_bars_after_filled: settings.max_open_bars_after_filled,
    // Strategy-type-specific settings
    max_open_bars_before_filled_price_based: settings.max_open_bars_before_filled_price_based,
    max_open_bars_after_filled_price_based: settings.max_open_bars_after_filled_price_based,
    max_open_bars_before_filled_spread_based: settings.max_open_bars_before_filled_spread_based,
    max_open_bars_after_filled_spread_based: settings.max_open_bars_after_filled_spread_based,
    // Other settings
    use_fixed_capital: settings.use_fixed_capital,
    fixed_capital_usd: settings.fixed_capital_usd
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
      // Update max_open_bars settings in DATABASE (persisted across restarts)
      // Can receive:
      // { type: "before_filled", timeframe: "1h", max_bars: 24 }
      // { type: "after_filled", timeframe: "1h", max_bars: 24 }
      // { type: "before_filled", max_open_bars: { "1h": 24, "4h": 12 } }
      // { type: "before_filled", strategy_type: "price_based", timeframe: "1h", max_bars: 24 }
      // { type: "before_filled", strategy_type: "spread_based", max_open_bars: { "1h": 24 } }
      const { type, timeframe, max_bars, max_open_bars, strategy_type } = body
      const currentSettings = await getSimulatorSettings()

      // Determine which setting to update
      // If strategy_type is specified, use strategy-type-specific setting
      // Otherwise, use global setting (backward compatibility)
      let settingType: string
      if (strategy_type === 'price_based') {
        settingType = type === 'after_filled' ? 'max_open_bars_after_filled_price_based' : 'max_open_bars_before_filled_price_based'
      } else if (strategy_type === 'spread_based') {
        settingType = type === 'after_filled' ? 'max_open_bars_after_filled_spread_based' : 'max_open_bars_before_filled_spread_based'
      } else {
        // No strategy type specified - use global setting (backward compatibility)
        settingType = type === 'after_filled' ? 'max_open_bars_after_filled' : 'max_open_bars_before_filled'
      }

      const currentValue = currentSettings[settingType as keyof SimulatorSettings]
      let updatedMaxBars: MaxOpenBarsConfig = (typeof currentValue === 'object' && currentValue !== null) ? { ...currentValue } : {}

      if (timeframe && typeof max_bars === 'number') {
        // Update single timeframe
        updatedMaxBars[timeframe] = max_bars
      } else if (typeof max_open_bars === 'object' && max_open_bars !== null) {
        // Update multiple timeframes at once
        updatedMaxBars = { ...updatedMaxBars, ...max_open_bars }
      }

      // Save to database (persisted)
      const updatePayload = { [settingType]: updatedMaxBars }
      await saveSimulatorSettings(updatePayload)

      const strategyLabel = strategy_type ? ` (${strategy_type})` : ''
      return NextResponse.json({
        success: true,
        message: timeframe
          ? `Max open bars (${type || 'before_filled'}${strategyLabel}) for ${timeframe} set to ${max_bars}`
          : `Max open bars (${type || 'before_filled'}${strategyLabel}) updated`,
        [settingType]: updatedMaxBars
      })

    } else if (action === 'set-capital') {
      // Update simulator capital settings in DATABASE (persisted across restarts)
      // Can receive:
      // { use_fixed_capital: true, fixed_capital_usd: 10000 }
      const { use_fixed_capital, fixed_capital_usd } = body
      const updatePayload: Partial<SimulatorSettings> = {}

      if (typeof use_fixed_capital === 'boolean') {
        updatePayload.use_fixed_capital = use_fixed_capital
      }
      if (typeof fixed_capital_usd === 'number' && fixed_capital_usd > 0) {
        updatePayload.fixed_capital_usd = fixed_capital_usd
      }

      if (Object.keys(updatePayload).length === 0) {
        return NextResponse.json(
          { error: 'No valid capital settings provided' },
          { status: 400 }
        )
      }

      await saveSimulatorSettings(updatePayload)

      const updatedSettings = await getSimulatorSettings()
      return NextResponse.json({
        success: true,
        message: 'Simulator capital settings updated',
        use_fixed_capital: updatedSettings.use_fixed_capital,
        fixed_capital_usd: updatedSettings.fixed_capital_usd
      })

    } else {
      return NextResponse.json(
        { error: 'Invalid action. Use "start", "stop", "update", "force-run", "set-max-bars", or "set-capital"' },
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


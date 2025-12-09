'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { RefreshCw, TrendingUp, TrendingDown, Clock, CheckCircle, Target, BarChart2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LoadingState, ErrorState, TradeChartModal, TradeData } from '@/components/shared'
import { useRealtime } from '@/hooks/useRealtime'

interface SimulatorStats {
  total_paper_trades: number
  pending_fill: number
  filled: number
  closed: number
  total_pnl: number
  win_rate: number
  by_instance: Record<string, {
    total: number
    closed: number
    pnl: number
  }>
}

interface OpenPaperTrade {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  stop_loss: number
  take_profit: number
  quantity: number
  status: string
  created_at: string
  filled_at: string | null
  fill_time: string | null  // When price touched entry (simulated fill)
  fill_price: number | null // Price at which trade was filled
  submitted_at: string | null
  timeframe: string | null
  confidence: number | null
  rr_ratio: number | null
  cycle_id: string
  run_id: string
  dry_run?: number | null
  rejection_reason?: string | null
}

interface CycleWithTrades {
  cycle_id: string
  boundary_time: string
  status: string
  trades: OpenPaperTrade[]
}

interface RunWithCycles {
  run_id: string
  instance_id: string
  started_at: string
  status: string
  cycles: CycleWithTrades[]
}

interface InstanceWithRuns {
  instance_id: string
  instance_name: string
  runs: RunWithCycles[]
}

// Per-timeframe max open bars configuration
type MaxOpenBarsConfig = Record<string, number>

interface MonitorStatus {
  running: boolean
  last_check: string | null
  trades_checked: number
  trades_closed: number
  trades_cancelled?: number
  max_open_bars?: MaxOpenBarsConfig  // Per-timeframe max bars (0 = disabled for that timeframe)
  next_check: number
  results: Array<{
    trade_id: string
    symbol: string
    action: 'checked' | 'closed' | 'cancelled'
    current_price: number
    checked_at?: string
    bars_open?: number
  }>
}

interface ClosedTrade {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  exit_price: number
  stop_loss: number
  take_profit: number
  quantity: number
  pnl: number
  pnl_percent: number
  exit_reason: string
  created_at: string
  filled_at: string | null
  fill_time: string | null
  fill_price: number | null
  closed_at: string
  timeframe: string | null
  instance_name: string
  run_id: string
  dry_run?: number | null
}

// Cancelled trades have same structure as closed trades
type CancelledTrade = ClosedTrade

// Timeframes we support for max open bars config
const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d'] as const

export function SimulatorPage() {
  const [stats, setStats] = useState<SimulatorStats | null>(null)
  const [openTrades, setOpenTrades] = useState<InstanceWithRuns[]>([])
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([])
  const [cancelledTrades, setCancelledTrades] = useState<CancelledTrade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [autoClosing, setAutoClosing] = useState(false)
  const [monitorStatus, setMonitorStatus] = useState<MonitorStatus | null>(null)
  const [monitorLoading, setMonitorLoading] = useState(false)
  const [maxOpenBarsConfig, setMaxOpenBarsConfig] = useState<MaxOpenBarsConfig>({})  // Per-timeframe
  const [savingMaxBars, setSavingMaxBars] = useState(false)

  // Modal state for trade chart
  const [selectedTrade, setSelectedTrade] = useState<TradeData | null>(null)
  const [chartMode, setChartMode] = useState<'live' | 'historical'>('live')

  // Connect to real-time updates
  const { tickers } = useRealtime()

  // Track fetched prices for symbols not in WebSocket tickers
  const [fetchedPrices, setFetchedPrices] = useState<Record<string, number>>({})

  // Get current prices from real-time tickers + fetched prices
  const currentPrices = useMemo(() => {
    const prices: Record<string, number> = {}
    if (tickers) {
      Object.values(tickers).forEach(ticker => {
        prices[ticker.symbol] = parseFloat(ticker.lastPrice)
      })
    }
    // Merge in fetched prices for symbols not in WebSocket
    Object.entries(fetchedPrices).forEach(([symbol, price]) => {
      if (!prices[symbol]) {
        prices[symbol] = price
      }
    })
    return prices
  }, [tickers, fetchedPrices])

  const fetchMonitorStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/simulator/monitor')
      if (!res.ok) throw new Error('Failed to fetch monitor status')
      const data = await res.json()
      setMonitorStatus(data)
      // Sync max_open_bars config from monitor status
      if (data.max_open_bars && typeof data.max_open_bars === 'object') {
        setMaxOpenBarsConfig(data.max_open_bars)
      }
    } catch (err) {
      console.error('Failed to fetch monitor status:', err)
    }
  }, [])

  // Fetch price for a specific symbol from Bybit API
  const fetchPriceForSymbol = useCallback(async (symbol: string) => {
    try {
      const res = await fetch(`/api/bot/ticker?symbol=${symbol}`)
      if (!res.ok) return
      const data = await res.json()
      if (data.lastPrice) {
        setFetchedPrices(prev => ({
          ...prev,
          [symbol]: parseFloat(data.lastPrice)
        }))
      }
    } catch (err) {
      console.error(`Failed to fetch price for ${symbol}:`, err)
    }
  }, [])

  const toggleMonitor = useCallback(async (action: 'start' | 'stop') => {
    setMonitorLoading(true)
    try {
      const res = await fetch('/api/bot/simulator/monitor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      })
      if (!res.ok) throw new Error(`Failed to ${action} monitor`)
      await fetchMonitorStatus()
    } catch (err) {
      console.error(`Failed to ${action} monitor:`, err)
      setError(err instanceof Error ? err.message : `Failed to ${action} monitor`)
    } finally {
      setMonitorLoading(false)
    }
  }, [fetchMonitorStatus])

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/simulator')
      if (!res.ok) throw new Error('Failed to fetch simulator stats')
      const data = await res.json()
      setStats(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch stats')
    }
  }, [])

  const fetchOpenTrades = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/simulator/open-trades')
      if (!res.ok) throw new Error('Failed to fetch open trades')
      const data = await res.json()
      setOpenTrades(data.instances || [])

      // Fetch prices for symbols that don't have ticker data
      const symbolsNeedingPrices = new Set<string>()
      data.instances?.forEach((instance: InstanceWithRuns) => {
        instance.runs.forEach(run => {
          run.cycles.forEach(cycle => {
            cycle.trades.forEach(trade => {
              // Only fetch if we don't have ticker data for this symbol
              if (!tickers || !tickers[trade.symbol]) {
                symbolsNeedingPrices.add(trade.symbol)
              }
            })
          })
        })
      })

      // Fetch prices for missing symbols
      symbolsNeedingPrices.forEach(symbol => {
        fetchPriceForSymbol(symbol)
      })

      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch open trades')
    } finally {
      setLoading(false)
    }
  }, [tickers, fetchPriceForSymbol])

  const fetchClosedTrades = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/simulator/closed-trades')
      if (!res.ok) throw new Error('Failed to fetch closed trades')
      const data = await res.json()
      setClosedTrades(data.trades || [])
    } catch (err) {
      console.error('Failed to fetch closed trades:', err)
    }
  }, [])

  const fetchCancelledTrades = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/simulator/cancelled-trades')
      if (!res.ok) throw new Error('Failed to fetch cancelled trades')
      const data = await res.json()
      setCancelledTrades(data.trades || [])
    } catch (err) {
      console.error('Failed to fetch cancelled trades:', err)
    }
  }, [])

  const triggerAutoClose = useCallback(async () => {
    setAutoClosing(true)
    try {
      const res = await fetch('/api/bot/simulator/auto-close', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to auto-close trades')
      const data = await res.json()

      // Update monitor status with results
      await fetch('/api/bot/simulator/monitor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update',
          trades_checked: data.checked || 0,
          trades_closed: data.closed || 0,
          results: data.results || []
        })
      })

      // Refresh data after auto-close
      await fetchStats()
      await fetchOpenTrades()
      await fetchClosedTrades()
      await fetchCancelledTrades()
      await fetchMonitorStatus()

      // Show result
      if (data.closed > 0) {
        console.log(`Auto-closed ${data.closed} trades`)
      }
      if (data.cancelled > 0) {
        console.log(`Cancelled ${data.cancelled} trades (max bars exceeded)`)
      }
    } catch (err) {
      console.error('Auto-close error:', err)
      setError(err instanceof Error ? err.message : 'Failed to auto-close trades')
    } finally {
      setAutoClosing(false)
    }
  }, [fetchStats, fetchOpenTrades, fetchClosedTrades, fetchCancelledTrades, fetchMonitorStatus])

  // Initial fetch - load current state AND trigger fresh check on page load
  useEffect(() => {
    const initialize = async () => {
      // First fetch current data
      await Promise.all([
        fetchStats(),
        fetchOpenTrades(),
        fetchClosedTrades(),
        fetchCancelledTrades(),
        fetchMonitorStatus()
      ])

      // Then trigger a fresh auto-close check to ensure data is current
      // This ensures we don't show stale "last check" timestamps
      triggerAutoClose()
    }
    initialize()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh UI data when autoRefresh is enabled
  useEffect(() => {
    if (!autoRefresh) return

    const refreshInterval = setInterval(() => {
      fetchStats()
      fetchOpenTrades()
      fetchClosedTrades()
      fetchCancelledTrades()
      fetchMonitorStatus()
    }, 5000)

    return () => clearInterval(refreshInterval)
  }, [autoRefresh, fetchStats, fetchOpenTrades, fetchClosedTrades, fetchCancelledTrades, fetchMonitorStatus])

  // Get last checked price for a trade from monitor results
  const getLastCheckedPrice = (tradeId: string): { price: number; checkedAt: string } | null => {
    if (!monitorStatus?.results) return null
    const result = monitorStatus.results.find(r => r.trade_id === tradeId)
    if (!result) return null
    return {
      price: result.current_price,
      checkedAt: result.checked_at || monitorStatus.last_check || ''
    }
  }

  // Calculate unrealized PnL for a trade based on current price
  const calculateUnrealizedPnL = (trade: OpenPaperTrade): { pnl: number; pnlPercent: number; currentPrice: number | null } => {
    const currentPrice = currentPrices[trade.symbol]
    if (!currentPrice) return { pnl: 0, pnlPercent: 0, currentPrice: null }

    // Normalize side to handle both 'Buy'/'Sell' and 'LONG'/'SHORT' formats
    const sideUpper = trade.side?.toUpperCase() || ''
    const isLong = sideUpper === 'BUY' || sideUpper === 'LONG'
    const priceDiff = isLong ? (currentPrice - trade.entry_price) : (trade.entry_price - currentPrice)
    const pnl = priceDiff * trade.quantity
    const pnlPercent = (priceDiff / trade.entry_price) * 100

    return { pnl, pnlPercent, currentPrice }
  }

  // Check if trade should be closed based on current price
  // IMPORTANT: Only applies to FILLED trades - pending fill trades cannot hit TP/SL yet
  const shouldCloseTrade = (trade: OpenPaperTrade, currentPrice: number): { shouldClose: boolean; reason: string | null } => {
    // Trade must be filled before it can hit TP/SL
    // A trade is filled if it has fill_time, filled_at, or status === 'filled'
    const isFilled = trade.fill_time || trade.filled_at || trade.status === 'filled'
    if (!isFilled) {
      return { shouldClose: false, reason: null }
    }

    // Normalize side to handle both 'Buy'/'Sell' and 'LONG'/'SHORT' formats
    const sideUpper = trade.side?.toUpperCase() || ''
    const isLong = sideUpper === 'BUY' || sideUpper === 'LONG'

    // Check SL
    if (isLong && currentPrice <= trade.stop_loss) {
      return { shouldClose: true, reason: 'SL Hit' }
    }
    if (!isLong && currentPrice >= trade.stop_loss) {
      return { shouldClose: true, reason: 'SL Hit' }
    }

    // Check TP
    if (isLong && currentPrice >= trade.take_profit) {
      return { shouldClose: true, reason: 'TP Hit' }
    }
    if (!isLong && currentPrice <= trade.take_profit) {
      return { shouldClose: true, reason: 'TP Hit' }
    }

    return { shouldClose: false, reason: null }
  }



  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />
  if (!stats) return <ErrorState message="No data available" />

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">📊 Paper Trade Simulator</h1>
          <p className="text-slate-400 mt-1">Monitor and simulate paper trades</p>
          {monitorStatus && (
            <div className="flex items-center gap-3 mt-2 text-sm">
              <div className={`flex items-center gap-1 ${monitorStatus.running ? 'text-green-400' : 'text-slate-500'}`}>
                <div className={`w-2 h-2 rounded-full ${monitorStatus.running ? 'bg-green-400 animate-pulse' : 'bg-slate-500'}`} />
                {monitorStatus.running ? 'Auto Monitor Active' : 'Auto Monitor Stopped'}
              </div>
              {monitorStatus.last_check && (
                <div className="text-slate-400">
                  Last check: {new Date(monitorStatus.last_check).toLocaleTimeString()}
                </div>
              )}
              {monitorStatus.running && monitorStatus.next_check && (
                <div className="text-slate-500">
                  Next: {Math.max(0, Math.round((monitorStatus.next_check * 1000 - Date.now()) / 1000))}s
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            onClick={() => toggleMonitor(monitorStatus?.running ? 'stop' : 'start')}
            disabled={monitorLoading}
            size="sm"
            variant={monitorStatus?.running ? 'destructive' : 'default'}
            className={monitorStatus?.running ? '' : 'bg-green-600 hover:bg-green-700'}
          >
            {monitorLoading ? '⏳ ...' : monitorStatus?.running ? '⏹️ Stop Auto' : '▶️ Start Auto'}
          </Button>
          <Button
            onClick={triggerAutoClose}
            disabled={autoClosing}
            size="sm"
            variant="default"
            className="bg-blue-600 hover:bg-blue-700"
          >
            {autoClosing ? '⏳ Checking...' : '🔄 Manual Check'}
          </Button>
          <Button
            onClick={() => setAutoRefresh(!autoRefresh)}
            variant={autoRefresh ? 'default' : 'outline'}
            size="sm"
          >
            {autoRefresh ? '⏸️ Auto' : '▶️ Manual'}
          </Button>
          <Button onClick={() => { fetchStats(); fetchOpenTrades(); fetchMonitorStatus(); }} size="sm" variant="outline">
            <RefreshCw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-5 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Total Paper Trades</div>
            <div className="text-3xl font-bold text-white">{stats.total_paper_trades}</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2 flex items-center gap-1">
              <Clock className="w-4 h-4" /> Pending Fill
            </div>
            <div className="text-3xl font-bold text-yellow-400">{stats.pending_fill}</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2 flex items-center gap-1">
              <CheckCircle className="w-4 h-4" /> Filled
            </div>
            <div className="text-3xl font-bold text-blue-400">{stats.filled}</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Closed</div>
            <div className="text-3xl font-bold text-slate-300">{stats.closed}</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Win Rate</div>
            <div className="text-3xl font-bold text-green-400">{stats.win_rate.toFixed(1)}%</div>
          </CardContent>
        </Card>
      </div>

      {/* P&L Card */}
      <Card className={`border-2 ${stats.total_pnl >= 0 ? 'bg-green-900/20 border-green-500' : 'bg-red-900/20 border-red-500'}`}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {stats.total_pnl >= 0 ? <TrendingUp className="text-green-400" /> : <TrendingDown className="text-red-400" />}
            Total P&L
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className={`text-4xl font-bold ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            ${stats.total_pnl.toFixed(2)}
          </div>
        </CardContent>
      </Card>

      {/* Simulator Settings - Per-Timeframe Max Open Bars */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="w-4 h-4 text-orange-400" />
            Max Open Bars per Timeframe
            <span className="text-slate-500 text-xs font-normal">(0 = disabled, trade never cancelled)</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-3 mb-4">
            {TIMEFRAMES.map(tf => (
              <div key={tf} className="flex items-center gap-2">
                <label className="text-slate-400 text-xs w-8">{tf}</label>
                <input
                  type="number"
                  min="0"
                  value={maxOpenBarsConfig[tf] ?? 0}
                  onChange={(e) => {
                    const val = parseInt(e.target.value) || 0
                    setMaxOpenBarsConfig(prev => ({ ...prev, [tf]: val }))
                  }}
                  className="w-16 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-white text-sm text-center"
                />
              </div>
            ))}
          </div>
          <Button
            size="sm"
            disabled={savingMaxBars}
            onClick={async () => {
              setSavingMaxBars(true)
              try {
                const res = await fetch('/api/bot/simulator/monitor', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ action: 'set-max-bars', max_open_bars: maxOpenBarsConfig })
                })
                if (!res.ok) throw new Error('Failed to save')
                await fetchMonitorStatus()
              } catch (err) {
                console.error('Failed to save max open bars:', err)
                setError(err instanceof Error ? err.message : 'Failed to save')
              } finally {
                setSavingMaxBars(false)
              }
            }}
            variant="default"
            className="bg-orange-600 hover:bg-orange-700 disabled:opacity-50"
          >
            {savingMaxBars ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              'Save Max Bars Settings'
            )}
          </Button>
        </CardContent>
      </Card>

      {/* By Instance Stats */}
      {Object.keys(stats.by_instance).length > 0 && (
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader>
            <CardTitle>By Instance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(stats.by_instance).map(([instanceId, data]) => (
                <div key={instanceId} className="flex justify-between items-center p-3 bg-slate-700 rounded">
                  <span className="text-slate-300 font-mono text-sm">{instanceId}</span>
                  <div className="flex gap-4 text-sm">
                    <span className="text-slate-400">Total: {data.total}</span>
                    <span className="text-slate-400">Closed: {data.closed}</span>
                    <span className={data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                      ${data.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Realtime Simulator Activity */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className={`w-5 h-5 text-cyan-400 ${autoClosing ? 'animate-spin' : ''}`} />
            Simulator Activity
            {monitorStatus?.running && (
              <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded animate-pulse">LIVE</span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="bg-slate-900 rounded-lg p-3 font-mono text-xs max-h-48 overflow-y-auto">
            {monitorStatus?.results && monitorStatus.results.length > 0 ? (
              <div className="space-y-1">
                {monitorStatus.results.map((result, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <span className="text-slate-500">[{new Date(result.checked_at || Date.now()).toLocaleTimeString()}]</span>
                    <span className={
                      result.action === 'closed' ? 'text-yellow-400' :
                      result.action === 'cancelled' ? 'text-orange-400' :
                      'text-slate-400'
                    }>
                      {result.action === 'closed' ? '🔔 CLOSED' :
                       result.action === 'cancelled' ? '⏱️ CANCELLED' :
                       '✓ Checked'}
                    </span>
                    <span className="text-white">{result.symbol}</span>
                    <span className="text-blue-400">@ ${result.current_price.toFixed(4)}</span>
                    {result.bars_open !== undefined && (
                      <span className="text-slate-500">({result.bars_open} bars)</span>
                    )}
                    {result.action === 'closed' && (
                      <span className="text-yellow-300">→ Trade closed!</span>
                    )}
                    {result.action === 'cancelled' && (
                      <span className="text-orange-300">→ Max bars exceeded!</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500">
                {monitorStatus?.running ? 'Waiting for next check...' : 'Monitor not running'}
              </div>
            )}
            {monitorStatus?.last_check && (
              <div className="mt-2 pt-2 border-t border-slate-700 text-slate-500">
                Last check: {new Date(monitorStatus.last_check).toLocaleString()} |
                Checked: {monitorStatus.trades_checked} |
                Closed: {monitorStatus.trades_closed}
                {monitorStatus.trades_cancelled ? ` | Cancelled: ${monitorStatus.trades_cancelled}` : ''}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Open Trades - Full Width Vertical List */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <Target className="w-5 h-5 text-blue-400" />
            Open Paper Trades ({openTrades.reduce((sum, inst) => sum + inst.runs.reduce((rSum, run) => rSum + run.cycles.reduce((cSum, cycle) => cSum + cycle.trades.length, 0), 0), 0)})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {openTrades.length === 0 ? (
            <div className="text-center py-8 text-slate-400">
              No open paper trades
            </div>
          ) : (
            <div className="space-y-3">
              {/* Flatten the hierarchy and sort by created_at (newest first) */}
              {openTrades
                .flatMap(instance =>
                  instance.runs.flatMap(run =>
                    run.cycles.flatMap(cycle =>
                      cycle.trades.map(trade => ({
                        trade,
                        instance_name: instance.instance_name,
                        run_id: run.run_id,
                        boundary_time: cycle.boundary_time
                      }))
                    )
                  )
                )
                .sort((a, b) => new Date(b.trade.created_at).getTime() - new Date(a.trade.created_at).getTime())
                .map(({ trade, instance_name, run_id, boundary_time: _boundaryTime }) => {
                  const { pnl, pnlPercent, currentPrice } = calculateUnrealizedPnL(trade)
                  // Check if trade is filled before checking for SL/TP
                  const isFilled = trade.status === 'filled' || trade.fill_time !== null || trade.filled_at !== null
                  const closeCheck = isFilled && currentPrice ? shouldCloseTrade(trade, currentPrice) : { shouldClose: false, reason: null }
                  // Normalize side to handle both 'Buy'/'Sell' and 'LONG'/'SHORT' formats
                  const sideUpper = trade.side?.toUpperCase() || ''
                  const isLong = sideUpper === 'BUY' || sideUpper === 'LONG'
                  const lastChecked = getLastCheckedPrice(trade.id)
                  // Calculate RR ratio correctly for both LONG and SHORT
                  const rrRatio = trade.rr_ratio || (trade.take_profit && trade.stop_loss && trade.entry_price
                    ? (() => {
                        const risk = Math.abs(trade.stop_loss - trade.entry_price)
                        const reward = isLong
                          ? Math.abs(trade.take_profit - trade.entry_price)
                          : Math.abs(trade.entry_price - trade.take_profit)
                        return risk > 0 ? reward / risk : null
                      })()
                    : null)

                  return (
                    <div
                      key={trade.id}
                      className={`p-4 rounded-lg border-2 cursor-pointer hover:brightness-110 transition-all ${
                        closeCheck.shouldClose
                          ? closeCheck.reason === 'TP Hit' ? 'bg-green-900/20 border-green-500' : 'bg-red-900/20 border-red-500'
                          : 'bg-slate-700/30 border-slate-600 hover:border-blue-500'
                      }`}
                      onClick={() => {
                        setSelectedTrade({
                          ...trade,
                          stop_loss: trade.stop_loss,
                          take_profit: trade.take_profit,
                          dry_run: trade.dry_run ?? 1,  // Paper trades default to 1
                          rejection_reason: trade.rejection_reason
                        })
                        setChartMode('live')
                      }}
                    >
                      {/* Row 1: Instance info + Symbol + Side + Alert */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1 text-[10px] text-slate-500">
                            <span className="bg-slate-700 px-1.5 py-0.5 rounded">{instance_name}</span>
                            <span>›</span>
                            <span className="bg-slate-700/50 px-1 py-0.5 rounded font-mono">{run_id.slice(0, 6)}</span>
                          </div>
                          <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          <span className={`text-xs px-2 py-1 rounded font-semibold ${isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                            {trade.side}
                          </span>
                          {rrRatio && <span className="text-xs bg-blue-900/30 text-blue-300 px-2 py-1 rounded">RR: {rrRatio.toFixed(1)}</span>}
                          {trade.timeframe && <span className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">{trade.timeframe}</span>}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedTrade({
                                ...trade,
                                stop_loss: trade.stop_loss,
                                take_profit: trade.take_profit,
                                dry_run: trade.dry_run ?? 1,
                                rejection_reason: trade.rejection_reason
                              })
                              setChartMode('live')
                            }}
                            className="p-1.5 bg-blue-900/50 hover:bg-blue-800 rounded text-blue-400 transition-colors"
                            title="View Live Chart"
                          >
                            <BarChart2 className="w-4 h-4" />
                          </button>
                          {closeCheck.shouldClose && (
                            <span className={`text-sm px-3 py-1 rounded font-bold animate-pulse ${
                              closeCheck.reason === 'TP Hit' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
                            }`}>
                              {closeCheck.reason}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Row 2: Times */}
                      <div className="flex items-center gap-4 mb-2 text-[11px]">
                        <div className="flex items-center gap-1">
                          <span className="text-blue-400">📡 Signal:</span>
                          <span className="text-slate-300">{new Date(trade.created_at).toLocaleString()}</span>
                        </div>
                        {trade.fill_time && (
                          <div className="flex items-center gap-1">
                            <span className="text-orange-400">✅ Filled:</span>
                            <span className="text-slate-300">{new Date(trade.fill_time).toLocaleString()}</span>
                          </div>
                        )}
                        {!trade.fill_time && trade.filled_at && (
                          <div className="flex items-center gap-1">
                            <span className="text-orange-400">✅ Filled:</span>
                            <span className="text-slate-300">{new Date(trade.filled_at).toLocaleString()}</span>
                          </div>
                        )}
                        {!trade.fill_time && !trade.filled_at && (
                          <div className="flex items-center gap-1">
                            <span className="text-yellow-500">⏳ Pending fill</span>
                          </div>
                        )}
                      </div>

                      {/* Row 3: Prices + PnL */}
                      <div className="flex items-center gap-6 flex-wrap">
                        <div className="flex items-center gap-4 text-sm">
                          <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                          <div><span className="text-green-400">TP:</span> <span className="text-green-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                          <div><span className="text-red-400">SL:</span> <span className="text-red-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                          <div><span className="text-slate-400">Qty:</span> <span className="text-white font-mono">{trade.quantity}</span></div>
                        </div>

                        {lastChecked && (
                          <div className="flex items-center gap-2 bg-yellow-900/20 border border-yellow-700/50 rounded px-3 py-1">
                            <Clock className="w-3 h-3 text-yellow-500" />
                            <span className="text-yellow-400 font-mono">${lastChecked.price.toFixed(4)}</span>
                            <span className="text-[10px] text-yellow-600">{new Date(lastChecked.checkedAt).toLocaleTimeString()}</span>
                          </div>
                        )}

                        {currentPrice && (
                          <div className={`flex items-center gap-2 px-4 py-2 rounded ${pnl >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                            <span className="text-slate-400 text-sm">Current: <span className="text-blue-400 font-mono">${currentPrice.toFixed(4)}</span></span>
                            <span className={`text-xl font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                              {pnl >= 0 ? '+' : ''}{pnlPercent.toFixed(2)}%
                            </span>
                            <span className={`text-sm ${pnl >= 0 ? 'text-green-300' : 'text-red-300'}`}>
                              ({pnl >= 0 ? '+' : ''}${pnl.toFixed(2)})
                            </span>
                          </div>
                        )}

                        <span className="text-[10px] text-slate-600 font-mono ml-auto">{trade.id.slice(0, 8)}</span>
                      </div>
                    </div>
                  )
                })}
            </div>
          )}
        </CardContent>
      </Card>
      
      {/* Closed Trades Summary Stats */}
      {closedTrades.length > 0 && (
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="py-4">
            {(() => {
              const wins = closedTrades.filter(t => t.pnl > 0).length
              const losses = closedTrades.filter(t => t.pnl < 0).length
              const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
              const winRate = closedTrades.length > 0 ? (wins / closedTrades.length * 100) : 0
              return (
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <div className={`text-3xl font-bold ${totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Total P&L</div>
                    </div>
                    <div className="h-12 w-px bg-slate-700" />
                    <div className="text-center">
                      <div className="text-2xl font-bold text-white">{closedTrades.length}</div>
                      <div className="text-xs text-slate-400">Total Trades</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">{wins}</div>
                      <div className="text-xs text-slate-400">Wins</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-400">{losses}</div>
                      <div className="text-xs text-slate-400">Losses</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${winRate >= 50 ? 'text-green-400' : 'text-yellow-400'}`}>{winRate.toFixed(0)}%</div>
                      <div className="text-xs text-slate-400">Win Rate</div>
                    </div>
                  </div>
                </div>
              )
            })()}
          </CardContent>
        </Card>
      )}


      {/* Closed Trades Section */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            Closed Paper Trades ({closedTrades.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {closedTrades.length === 0 ? (
            <div className="text-center py-8 text-slate-400">
              No closed paper trades yet
            </div>
          ) : (
            <div className="space-y-3">
              {[...closedTrades]
                .sort((a, b) => new Date(b.closed_at).getTime() - new Date(a.closed_at).getTime())
                .map(trade => {
                  const isWin = trade.pnl > 0
                  const isLong = trade.side === 'Buy'

                  return (
                    <div
                      key={trade.id}
                      className={`p-4 rounded-lg border-2 cursor-pointer hover:brightness-110 transition-all ${
                        isWin ? 'bg-green-900/20 border-green-600 hover:border-green-400' : 'bg-red-900/20 border-red-600 hover:border-red-400'
                      }`}
                      onClick={() => {
                        setSelectedTrade({
                          id: trade.id,
                          symbol: trade.symbol,
                          side: trade.side,
                          entry_price: trade.entry_price,
                          stop_loss: trade.stop_loss,
                          take_profit: trade.take_profit,
                          exit_price: trade.exit_price,
                          status: 'closed',
                          created_at: trade.created_at,
                          filled_at: trade.filled_at,
                          fill_time: trade.fill_time,
                          fill_price: trade.fill_price,
                          closed_at: trade.closed_at,
                          timeframe: trade.timeframe,
                          dry_run: trade.dry_run ?? 1,
                          exit_reason: trade.exit_reason
                        })
                        setChartMode('historical')
                      }}
                    >
                      {/* Row 1: Instance + Symbol + Side + Result + Date */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1 text-[10px] text-slate-500">
                            <span className="bg-slate-700 px-1.5 py-0.5 rounded">{trade.instance_name}</span>
                            <span>›</span>
                            <span className="bg-slate-700/50 px-1 py-0.5 rounded font-mono">{trade.run_id?.slice(0, 6)}</span>
                          </div>
                          <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          <span className={`text-xs px-2 py-1 rounded font-semibold ${isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                            {trade.side}
                          </span>
                          <span className={`text-sm px-3 py-1 rounded font-bold ${
                            trade.exit_reason === 'tp_hit' ? 'bg-green-500 text-white' : 'bg-red-500 text-white'
                          }`}>
                            {trade.exit_reason === 'tp_hit' ? 'TP HIT' : 'SL HIT'}
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedTrade({
                                id: trade.id,
                                symbol: trade.symbol,
                                side: trade.side,
                                entry_price: trade.entry_price,
                                stop_loss: trade.stop_loss,
                                take_profit: trade.take_profit,
                                exit_price: trade.exit_price,
                                status: 'closed',
                                created_at: trade.created_at,
                                filled_at: trade.filled_at,
                                fill_time: trade.fill_time,
                                fill_price: trade.fill_price,
                                closed_at: trade.closed_at,
                                timeframe: trade.timeframe,
                                dry_run: trade.dry_run ?? 1,
                                exit_reason: trade.exit_reason
                              })
                              setChartMode('historical')
                            }}
                            className="p-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-400 transition-colors"
                            title="View Historical Chart"
                          >
                            <BarChart2 className="w-4 h-4" />
                          </button>
                          <div className={`px-4 py-2 rounded ${isWin ? 'bg-green-900/40' : 'bg-red-900/40'}`}>
                            <span className={`text-xl font-bold ${isWin ? 'text-green-400' : 'text-red-400'}`}>
                              {trade.pnl >= 0 ? '+' : ''}{trade.pnl_percent?.toFixed(2)}%
                            </span>
                            <span className={`ml-2 text-sm ${isWin ? 'text-green-300' : 'text-red-300'}`}>
                              ({trade.pnl >= 0 ? '+' : ''}${trade.pnl?.toFixed(2)})
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Row 2: Times */}
                      <div className="flex items-center gap-4 mb-2 text-[11px]">
                        <div className="flex items-center gap-1">
                          <span className="text-blue-400">📡 Signal:</span>
                          <span className="text-slate-300">{new Date(trade.created_at).toLocaleString()}</span>
                        </div>
                        {(trade.fill_time || trade.filled_at) && (
                          <div className="flex items-center gap-1">
                            <span className="text-orange-400">✅ Filled:</span>
                            <span className="text-slate-300">{new Date(trade.fill_time || trade.filled_at!).toLocaleString()}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-1">
                          <span className={trade.exit_reason === 'tp_hit' ? 'text-green-400' : 'text-red-400'}>
                            {trade.exit_reason === 'tp_hit' ? '🎯' : '🛑'} Exit:
                          </span>
                          <span className="text-slate-300">{new Date(trade.closed_at).toLocaleString()}</span>
                        </div>
                      </div>

                      {/* Row 3: Prices */}
                      <div className="flex items-center gap-6 text-sm">
                        <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-400">Exit:</span> <span className={`font-mono ${isWin ? 'text-green-400' : 'text-red-400'}`}>${trade.exit_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">TP:</span> <span className="text-slate-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">SL:</span> <span className="text-slate-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                        <span className="text-[10px] text-slate-600 font-mono ml-auto">{trade.id.slice(0, 8)}</span>
                      </div>
                    </div>
                  )
                })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cancelled Trades Section */}
      {cancelledTrades.length > 0 && (
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-orange-400" />
              Cancelled Trades ({cancelledTrades.length})
              <span className="text-xs text-slate-500 font-normal ml-2">Max bars exceeded</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[...cancelledTrades]
                .sort((a, b) => new Date(b.closed_at).getTime() - new Date(a.closed_at).getTime())
                .map(trade => {
                  const isWin = trade.pnl > 0
                  const isLong = trade.side === 'Buy'

                  return (
                    <div
                      key={trade.id}
                      className="p-4 rounded-lg border-2 bg-orange-900/20 border-orange-600 cursor-pointer hover:brightness-110 transition-all"
                      onClick={() => {
                        setSelectedTrade({
                          id: trade.id,
                          symbol: trade.symbol,
                          side: trade.side,
                          entry_price: trade.entry_price,
                          stop_loss: trade.stop_loss,
                          take_profit: trade.take_profit,
                          exit_price: trade.exit_price,
                          status: 'cancelled',
                          created_at: trade.created_at,
                          filled_at: trade.filled_at,
                          fill_time: trade.fill_time,
                          fill_price: trade.fill_price,
                          closed_at: trade.closed_at,
                          timeframe: trade.timeframe,
                          dry_run: trade.dry_run ?? 1,
                          exit_reason: trade.exit_reason
                        })
                        setChartMode('historical')
                      }}
                    >
                      {/* Row 1: Symbol + Side + Cancelled Badge + P&L */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          <span className={`text-xs px-2 py-1 rounded font-semibold ${isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                            {trade.side}
                          </span>
                          <span className="text-sm px-3 py-1 rounded font-bold bg-orange-500 text-white">
                            ⏱️ CANCELLED
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-2xl font-bold ${isWin ? 'text-green-400' : 'text-red-400'}`}>
                            {isWin ? '+' : ''}{trade.pnl?.toFixed(2)} USD
                          </span>
                          <span className={`text-sm ${isWin ? 'text-green-400' : 'text-red-400'}`}>
                            ({isWin ? '+' : ''}{trade.pnl_percent?.toFixed(2)}%)
                          </span>
                        </div>
                      </div>

                      {/* Row 2: Dates */}
                      <div className="flex items-center gap-4 text-xs mb-2">
                        <div className="flex items-center gap-1">
                          <span className="text-slate-400">Created:</span>
                          <span className="text-slate-300">{new Date(trade.created_at).toLocaleString()}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-orange-400">⏱️ Cancelled:</span>
                          <span className="text-slate-300">{new Date(trade.closed_at).toLocaleString()}</span>
                        </div>
                      </div>

                      {/* Row 3: Prices */}
                      <div className="flex items-center gap-6 text-sm">
                        <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-400">Exit:</span> <span className={`font-mono ${isWin ? 'text-green-400' : 'text-red-400'}`}>${trade.exit_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">TP:</span> <span className="text-slate-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">SL:</span> <span className="text-slate-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                      </div>
                    </div>
                  )
                })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Trade Chart Modal */}
      <TradeChartModal
        isOpen={selectedTrade !== null}
        onClose={() => setSelectedTrade(null)}
        trade={selectedTrade}
        mode={chartMode}
      />
    </div>
  )
}


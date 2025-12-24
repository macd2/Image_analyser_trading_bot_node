'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { RefreshCw, Clock, CheckCircle, Target, BarChart2, Copy, ChevronDown, Check, RotateCcw } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LoadingState, ErrorState, TradeChartModal, TradeData } from '@/components/shared'
import { useRealtime } from '@/hooks/useRealtime'

interface SimulatorStats {
  total_paper_trades: number
  pending_fill: number
  filled: number
  closed: number
  cancelled: number
  total_pnl: number
  win_rate: number
  win_count: number
  loss_count: number
  total_trades: number
  avg_bars_open: number
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
  position_size_usd?: number
  risk_amount_usd?: number
  // Strategy information
  strategy_type?: string | null
  strategy_name?: string | null
  strategy_metadata?: any
  order_id_pair?: string | null
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
  strategy_name?: string
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
  // Global settings (fallback)
  max_open_bars_before_filled?: MaxOpenBarsConfig  // Max bars for pending trades (0 = no cancellation)
  max_open_bars_after_filled?: MaxOpenBarsConfig   // Max bars for filled trades (0 = no cancellation)
  // Strategy-type-specific settings
  max_open_bars_before_filled_price_based?: MaxOpenBarsConfig
  max_open_bars_after_filled_price_based?: MaxOpenBarsConfig
  max_open_bars_before_filled_spread_based?: MaxOpenBarsConfig
  max_open_bars_after_filled_spread_based?: MaxOpenBarsConfig
  next_check: number
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
  cancelled_at?: string | null
  timeframe: string | null
  instance_name: string
  strategy_name?: string
  strategy_type?: string | null
  strategy_metadata?: any
  instance_id: string
  run_id: string
  bars_open?: number
  dry_run?: number | null
  position_size_usd?: number
  risk_amount_usd?: number
  risk_percentage?: number
  confidence_weight?: number
  risk_per_unit?: number
  sizing_method?: string
  risk_pct_used?: number
  order_id_pair?: string | null
}

// Cancelled trades have same structure as closed trades
type CancelledTrade = ClosedTrade

// Timeframes we support for max open bars config
const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1D'] as const

// Map timeframe to minutes per bar
const TIMEFRAME_MINUTES: Record<string, number> = {
  '1m': 1,
  '3m': 3,
  '5m': 5,
  '15m': 15,
  '30m': 30,
  '1h': 60,
  '2h': 120,
  '4h': 240,
  '6h': 360,
  '12h': 720,
  '1d': 1440,
  '1D': 1440,
}

// Convert bars to human-readable duration
function barsToDuration(bars: number, timeframe: string): string {
  if (bars === 0) return ''
  const minutesPerBar = TIMEFRAME_MINUTES[timeframe] || 0
  const totalMinutes = bars * minutesPerBar
  if (totalMinutes < 60) {
    return `≈ ${totalMinutes}m`
  } else if (totalMinutes < 1440) {
    const hours = totalMinutes / 60
    return `≈ ${hours.toFixed(1)}h`
  } else {
    const days = totalMinutes / 1440
    return `≈ ${days.toFixed(1)}d`
  }
}

// Helper function to get strategy type color
function getStrategyTypeColor(strategyType?: string | null): string {
  switch (strategyType) {
    case 'spread_based':
      return 'bg-purple-900/40 text-purple-300 border-purple-700/50'
    case 'price_based':
      return 'bg-blue-900/40 text-blue-300 border-blue-700/50'
    case 'momentum':
      return 'bg-orange-900/40 text-orange-300 border-orange-700/50'
    case 'mean_reversion':
      return 'bg-green-900/40 text-green-300 border-green-700/50'
    default:
      return 'bg-slate-800/40 text-slate-300 border-slate-700/50'
  }
}

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

  // Global settings (fallback)
  const [maxOpenBarsBeforeFilled, setMaxOpenBarsBeforeFilled] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsBeforeFilled, setSavedMaxOpenBarsBeforeFilled] = useState<MaxOpenBarsConfig>({})
  const [maxOpenBarsAfterFilled, setMaxOpenBarsAfterFilled] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsAfterFilled, setSavedMaxOpenBarsAfterFilled] = useState<MaxOpenBarsConfig>({})

  // Price-based strategy settings
  const [maxOpenBarsBeforeFilledPriceBased, setMaxOpenBarsBeforeFilledPriceBased] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsBeforeFilledPriceBased, setSavedMaxOpenBarsBeforeFilledPriceBased] = useState<MaxOpenBarsConfig>({})
  const [maxOpenBarsAfterFilledPriceBased, setMaxOpenBarsAfterFilledPriceBased] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsAfterFilledPriceBased, setSavedMaxOpenBarsAfterFilledPriceBased] = useState<MaxOpenBarsConfig>({})

  // Spread-based strategy settings
  const [maxOpenBarsBeforeFilledSpreadBased, setMaxOpenBarsBeforeFilledSpreadBased] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsBeforeFilledSpreadBased, setSavedMaxOpenBarsBeforeFilledSpreadBased] = useState<MaxOpenBarsConfig>({})
  const [maxOpenBarsAfterFilledSpreadBased, setMaxOpenBarsAfterFilledSpreadBased] = useState<MaxOpenBarsConfig>({})
  const [savedMaxOpenBarsAfterFilledSpreadBased, setSavedMaxOpenBarsAfterFilledSpreadBased] = useState<MaxOpenBarsConfig>({})

  const [savingMaxBars, setSavingMaxBars] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [maxBarsConfigOpen, setMaxBarsConfigOpen] = useState(false)
  const [maxBarsStrategyType, setMaxBarsStrategyType] = useState<'global' | 'price_based' | 'spread_based'>('global')

  // Check if any max bars settings have changed (for current strategy type)
  const hasMaxBarsChanges = useMemo(() => {
    if (maxBarsStrategyType === 'global') {
      const beforeChanged = TIMEFRAMES.some(tf => (maxOpenBarsBeforeFilled[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilled[tf] ?? 0))
      const afterChanged = TIMEFRAMES.some(tf => (maxOpenBarsAfterFilled[tf] ?? 0) !== (savedMaxOpenBarsAfterFilled[tf] ?? 0))
      return beforeChanged || afterChanged
    } else if (maxBarsStrategyType === 'price_based') {
      const beforeChanged = TIMEFRAMES.some(tf => (maxOpenBarsBeforeFilledPriceBased[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilledPriceBased[tf] ?? 0))
      const afterChanged = TIMEFRAMES.some(tf => (maxOpenBarsAfterFilledPriceBased[tf] ?? 0) !== (savedMaxOpenBarsAfterFilledPriceBased[tf] ?? 0))
      return beforeChanged || afterChanged
    } else {
      const beforeChanged = TIMEFRAMES.some(tf => (maxOpenBarsBeforeFilledSpreadBased[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilledSpreadBased[tf] ?? 0))
      const afterChanged = TIMEFRAMES.some(tf => (maxOpenBarsAfterFilledSpreadBased[tf] ?? 0) !== (savedMaxOpenBarsAfterFilledSpreadBased[tf] ?? 0))
      return beforeChanged || afterChanged
    }
  }, [maxBarsStrategyType, maxOpenBarsBeforeFilled, savedMaxOpenBarsBeforeFilled, maxOpenBarsAfterFilled, savedMaxOpenBarsAfterFilled, maxOpenBarsBeforeFilledPriceBased, savedMaxOpenBarsBeforeFilledPriceBased, maxOpenBarsAfterFilledPriceBased, savedMaxOpenBarsAfterFilledPriceBased, maxOpenBarsBeforeFilledSpreadBased, savedMaxOpenBarsBeforeFilledSpreadBased, maxOpenBarsAfterFilledSpreadBased, savedMaxOpenBarsAfterFilledSpreadBased])

  // Get list of changed timeframes for before filled (for current strategy type)
  const changedTimeframesBeforeFilled = useMemo(() => {
    if (maxBarsStrategyType === 'global') {
      return TIMEFRAMES.filter(tf => (maxOpenBarsBeforeFilled[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilled[tf] ?? 0))
    } else if (maxBarsStrategyType === 'price_based') {
      return TIMEFRAMES.filter(tf => (maxOpenBarsBeforeFilledPriceBased[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilledPriceBased[tf] ?? 0))
    } else {
      return TIMEFRAMES.filter(tf => (maxOpenBarsBeforeFilledSpreadBased[tf] ?? 0) !== (savedMaxOpenBarsBeforeFilledSpreadBased[tf] ?? 0))
    }
  }, [maxBarsStrategyType, maxOpenBarsBeforeFilled, savedMaxOpenBarsBeforeFilled, maxOpenBarsBeforeFilledPriceBased, savedMaxOpenBarsBeforeFilledPriceBased, maxOpenBarsBeforeFilledSpreadBased, savedMaxOpenBarsBeforeFilledSpreadBased])

  // Get list of changed timeframes for after filled (for current strategy type)
  const changedTimeframesAfterFilled = useMemo(() => {
    if (maxBarsStrategyType === 'global') {
      return TIMEFRAMES.filter(tf => (maxOpenBarsAfterFilled[tf] ?? 0) !== (savedMaxOpenBarsAfterFilled[tf] ?? 0))
    } else if (maxBarsStrategyType === 'price_based') {
      return TIMEFRAMES.filter(tf => (maxOpenBarsAfterFilledPriceBased[tf] ?? 0) !== (savedMaxOpenBarsAfterFilledPriceBased[tf] ?? 0))
    } else {
      return TIMEFRAMES.filter(tf => (maxOpenBarsAfterFilledSpreadBased[tf] ?? 0) !== (savedMaxOpenBarsAfterFilledSpreadBased[tf] ?? 0))
    }
  }, [maxBarsStrategyType, maxOpenBarsAfterFilled, savedMaxOpenBarsAfterFilled, maxOpenBarsAfterFilledPriceBased, savedMaxOpenBarsAfterFilledPriceBased, maxOpenBarsAfterFilledSpreadBased, savedMaxOpenBarsAfterFilledSpreadBased])

  // Modal state for trade chart
  const [selectedTrade, setSelectedTrade] = useState<TradeData | null>(null)
  const [chartMode, setChartMode] = useState<'live' | 'historical'>('live')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [copiedType, setCopiedType] = useState<'trade' | 'run' | 'rec' | 'id' | null>(null)

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
      // Sync max_open_bars configs from monitor status (both saved and editable)
      if (!hasMaxBarsChanges) {
        // Global settings
        if (data.max_open_bars_before_filled && typeof data.max_open_bars_before_filled === 'object') {
          setMaxOpenBarsBeforeFilled(data.max_open_bars_before_filled)
          setSavedMaxOpenBarsBeforeFilled(data.max_open_bars_before_filled)
        }
        if (data.max_open_bars_after_filled && typeof data.max_open_bars_after_filled === 'object') {
          setMaxOpenBarsAfterFilled(data.max_open_bars_after_filled)
          setSavedMaxOpenBarsAfterFilled(data.max_open_bars_after_filled)
        }
        // Price-based strategy settings
        if (data.max_open_bars_before_filled_price_based && typeof data.max_open_bars_before_filled_price_based === 'object') {
          setMaxOpenBarsBeforeFilledPriceBased(data.max_open_bars_before_filled_price_based)
          setSavedMaxOpenBarsBeforeFilledPriceBased(data.max_open_bars_before_filled_price_based)
        }
        if (data.max_open_bars_after_filled_price_based && typeof data.max_open_bars_after_filled_price_based === 'object') {
          setMaxOpenBarsAfterFilledPriceBased(data.max_open_bars_after_filled_price_based)
          setSavedMaxOpenBarsAfterFilledPriceBased(data.max_open_bars_after_filled_price_based)
        }
        // Spread-based strategy settings
        if (data.max_open_bars_before_filled_spread_based && typeof data.max_open_bars_before_filled_spread_based === 'object') {
          setMaxOpenBarsBeforeFilledSpreadBased(data.max_open_bars_before_filled_spread_based)
          setSavedMaxOpenBarsBeforeFilledSpreadBased(data.max_open_bars_before_filled_spread_based)
        }
        if (data.max_open_bars_after_filled_spread_based && typeof data.max_open_bars_after_filled_spread_based === 'object') {
          setMaxOpenBarsAfterFilledSpreadBased(data.max_open_bars_after_filled_spread_based)
          setSavedMaxOpenBarsAfterFilledSpreadBased(data.max_open_bars_after_filled_spread_based)
        }
      }
    } catch (err) {
      console.error('Failed to fetch monitor status:', err)
    }
  }, [hasMaxBarsChanges])

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

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    try {
      await Promise.all([
        fetchStats(),
        fetchOpenTrades(),
        fetchClosedTrades(),
        fetchCancelledTrades(),
        fetchMonitorStatus(),
      ])
    } catch (err) {
      console.error('Refresh failed:', err)
      // Optionally show error toast
    } finally {
      setRefreshing(false)
    }
  }, [fetchStats, fetchOpenTrades, fetchClosedTrades, fetchCancelledTrades, fetchMonitorStatus])

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

  // Calculate z-score distance to exit threshold for spread-based trades
  const calculateZScoreDistance = (trade: OpenPaperTrade, pairPrice: number | null): { zScore: number; distance: number; threshold: number } | null => {
    if (!pairPrice) return null

    // Parse strategy_metadata
    let metadata = trade.strategy_metadata
    if (typeof metadata === 'string') {
      try {
        metadata = JSON.parse(metadata)
      } catch {
        return null
      }
    }

    if (!metadata || typeof metadata !== 'object') return null

    const beta = metadata.beta
    const spread_mean = metadata.spread_mean
    const spread_std = metadata.spread_std
    const z_exit_threshold = metadata.z_exit_threshold

    if (beta === undefined || spread_mean === undefined || spread_std === undefined || z_exit_threshold === undefined) {
      return null
    }

    // Calculate current z-score
    const spread = pairPrice - beta * trade.entry_price
    const zScore = (spread - spread_mean) / spread_std
    const distance = Math.abs(z_exit_threshold) - Math.abs(zScore)

    return { zScore, distance, threshold: z_exit_threshold }
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
          <Button onClick={handleRefresh} size="sm" variant="outline" disabled={refreshing}>
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* Main Stats Grid */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Current State</h2>
        <div className="grid grid-cols-5 gap-4">
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Total Paper Trades</div>
            <div className="text-3xl font-bold text-white">{stats.total_paper_trades}</div>
            <div className="text-xs text-slate-500 mt-2">Open trades</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2 flex items-center gap-1">
              <Clock className="w-4 h-4" /> Pending Fill
            </div>
            <div className="text-3xl font-bold text-yellow-400">{stats.pending_fill}</div>
            <div className="text-xs text-slate-500 mt-2">Awaiting entry</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2 flex items-center gap-1">
              <CheckCircle className="w-4 h-4" /> Filled
            </div>
            <div className="text-3xl font-bold text-blue-400">{stats.filled}</div>
            <div className="text-xs text-slate-500 mt-2">Awaiting exit</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Closed</div>
            <div className="text-3xl font-bold text-slate-300">{stats.closed}</div>
            <div className="text-xs text-slate-500 mt-2">TP/SL hit only</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="pt-6">
            <div className="text-slate-400 text-sm mb-2">Cancelled</div>
            <div className="text-3xl font-bold text-orange-400">{stats.cancelled}</div>
            <div className="text-xs text-slate-500 mt-2">Max bars exceeded</div>
          </CardContent>
        </Card>
        </div>
      </div>

      {/* P&L Card */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Historical Performance</h2>
        <Card className="bg-slate-800 border-slate-700">
          <CardContent className="py-4">
            {(() => {
              const avgPnlPerTrade = stats.total_trades > 0 ? stats.total_pnl / stats.total_trades : 0
              const totalWinsPnl = stats.win_count > 0 ? stats.total_pnl * (stats.win_count / (stats.win_count + stats.loss_count)) : 0
              const totalLossesPnl = stats.loss_count > 0 ? Math.abs(stats.total_pnl - totalWinsPnl) : 0
              const profitFactor = totalLossesPnl > 0 ? totalWinsPnl / totalLossesPnl : (totalWinsPnl > 0 ? Infinity : 0)
              return (
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div className="flex items-center gap-6">
                    <div className="text-center">
                      <div className={`text-3xl font-bold ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Total P&L</div>
                    </div>
                    <div className="h-12 w-px bg-slate-700" />
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${avgPnlPerTrade >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {avgPnlPerTrade >= 0 ? '+' : ''}${avgPnlPerTrade.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Avg P&L/Trade</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${profitFactor >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                        {profitFactor === Infinity ? '∞' : profitFactor.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Profit Factor</div>
                    </div>
                    <div className="h-12 w-px bg-slate-700" />
                    <div className="text-center">
                      <div className="text-2xl font-bold text-white">{stats.total_trades}</div>
                      <div className="text-xs text-slate-400">Total Trades</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">{stats.win_count}</div>
                      <div className="text-xs text-slate-400">Wins</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-400">{stats.loss_count}</div>
                      <div className="text-xs text-slate-400">Losses</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-white">{stats.avg_bars_open.toFixed(1)}</div>
                      <div className="text-xs text-slate-400">Avg Bars Open</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-400">{stats.win_rate.toFixed(0)}%</div>
                      <div className="text-xs text-slate-400">Win Rate</div>
                    </div>
                  </div>
                </div>
              )
            })()}
          </CardContent>
        </Card>
      </div>

      {/* Closed Trades Summary Stats */}
      {closedTrades.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Closed Trades Summary</h2>
          <Card className="bg-slate-800 border-slate-700">
          <CardContent className="py-4">
            {(() => {
              const wins = closedTrades.filter(t => t.pnl > 0).length
              const losses = closedTrades.filter(t => t.pnl < 0).length
              const totalPnl = closedTrades.reduce((sum, t) => sum + (t.pnl || 0), 0)
              const avgPnlPerTrade = closedTrades.length > 0 ? totalPnl / closedTrades.length : 0
              const totalWinsPnl = closedTrades.filter(t => t.pnl > 0).reduce((sum, t) => sum + (t.pnl || 0), 0)
              const totalLossesPnl = Math.abs(closedTrades.filter(t => t.pnl < 0).reduce((sum, t) => sum + (t.pnl || 0), 0))
              const profitFactor = totalLossesPnl > 0 ? totalWinsPnl / totalLossesPnl : (totalWinsPnl > 0 ? Infinity : 0)
              const avgBarsOpen = closedTrades.length > 0 ? closedTrades.reduce((sum, t) => sum + (t.bars_open || 0), 0) / closedTrades.length : 0
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
                      <div className={`text-2xl font-bold ${avgPnlPerTrade >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {avgPnlPerTrade >= 0 ? '+' : ''}${avgPnlPerTrade.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Avg P&L/Trade</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${profitFactor >= 1 ? 'text-green-400' : 'text-red-400'}`}>
                        {profitFactor === Infinity ? '∞' : profitFactor.toFixed(2)}
                      </div>
                      <div className="text-xs text-slate-400">Profit Factor</div>
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
                      <div className="text-2xl font-bold text-white">{avgBarsOpen.toFixed(1)}</div>
                      <div className="text-xs text-slate-400">Avg Bars Open</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-400">{winRate.toFixed(0)}%</div>
                      <div className="text-xs text-slate-400">Win Rate</div>
                    </div>
                  </div>
                </div>
              )
            })()}
          </CardContent>
        </Card>
        </div>
      )}

      {/* Simulator Settings - Per-Timeframe Max Open Bars */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader
          className="pb-2 cursor-pointer hover:bg-slate-700/50 transition-colors"
          onClick={() => setMaxBarsConfigOpen(!maxBarsConfigOpen)}
        >
          <CardTitle className="text-sm flex items-center gap-2">
            <ChevronDown
              className={`w-4 h-4 text-orange-400 transition-transform ${maxBarsConfigOpen ? 'rotate-180' : ''}`}
            />
            <Clock className="w-4 h-4 text-orange-400" />
            Max Open Bars Configuration
            <span className="text-slate-500 text-xs font-normal">(0 = no cancellation)</span>
          </CardTitle>
        </CardHeader>
        {maxBarsConfigOpen && (
        <div className="px-6 py-3 border-t border-slate-700 bg-slate-800/50">
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setMaxBarsStrategyType('global')}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                maxBarsStrategyType === 'global'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Global
            </button>
            <button
              onClick={() => setMaxBarsStrategyType('price_based')}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                maxBarsStrategyType === 'price_based'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Price-Based
            </button>
            <button
              onClick={() => setMaxBarsStrategyType('spread_based')}
              className={`px-3 py-1.5 text-sm rounded transition-colors ${
                maxBarsStrategyType === 'spread_based'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              Spread-Based
            </button>
          </div>
        </div>
        )}
        {maxBarsConfigOpen && (
        <CardContent>
          {/* Table View */}
          <div className="overflow-x-auto mb-6">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-600">
                  <th className="text-left py-2 px-3 text-slate-400 font-semibold">Timeframe</th>
                  <th className="text-center py-2 px-3 text-blue-400 font-semibold">Before Filled</th>
                  <th className="text-center py-2 px-3 text-blue-300 font-semibold text-xs">Duration</th>
                  <th className="text-center py-2 px-3 text-green-400 font-semibold">After Filled</th>
                  <th className="text-center py-2 px-3 text-green-300 font-semibold text-xs">Duration</th>
                </tr>
              </thead>
              <tbody>
                {TIMEFRAMES.map((tf, idx) => {
                  // Get the correct state variables based on selected strategy type
                  let barsBefore: number
                  let barsAfter: number
                  let setBarsBefore: (fn: (prev: MaxOpenBarsConfig) => MaxOpenBarsConfig) => void
                  let setBarsAfter: (fn: (prev: MaxOpenBarsConfig) => MaxOpenBarsConfig) => void

                  if (maxBarsStrategyType === 'global') {
                    barsBefore = maxOpenBarsBeforeFilled[tf] ?? 0
                    barsAfter = maxOpenBarsAfterFilled[tf] ?? 0
                    setBarsBefore = setMaxOpenBarsBeforeFilled
                    setBarsAfter = setMaxOpenBarsAfterFilled
                  } else if (maxBarsStrategyType === 'price_based') {
                    barsBefore = maxOpenBarsBeforeFilledPriceBased[tf] ?? 0
                    barsAfter = maxOpenBarsAfterFilledPriceBased[tf] ?? 0
                    setBarsBefore = setMaxOpenBarsBeforeFilledPriceBased
                    setBarsAfter = setMaxOpenBarsAfterFilledPriceBased
                  } else {
                    barsBefore = maxOpenBarsBeforeFilledSpreadBased[tf] ?? 0
                    barsAfter = maxOpenBarsAfterFilledSpreadBased[tf] ?? 0
                    setBarsBefore = setMaxOpenBarsBeforeFilledSpreadBased
                    setBarsAfter = setMaxOpenBarsAfterFilledSpreadBased
                  }

                  const isChangedBefore = changedTimeframesBeforeFilled.includes(tf)
                  const isChangedAfter = changedTimeframesAfterFilled.includes(tf)
                  const durationBefore = barsToDuration(barsBefore, tf)
                  const durationAfter = barsToDuration(barsAfter, tf)

                  return (
                    <tr key={tf} className={`border-b border-slate-700 hover:bg-slate-700/30 transition-colors ${idx % 2 === 0 ? 'bg-slate-800/20' : ''}`}>
                      {/* Timeframe Column */}
                      <td className="py-3 px-3 text-slate-300 font-medium">{tf}</td>

                      {/* Before Filled Input */}
                      <td className="py-3 px-3">
                        <div className="flex items-center justify-center gap-1">
                          <input
                            type="number"
                            min="0"
                            value={barsBefore}
                            onChange={(e) => {
                              const val = parseInt(e.target.value) || 0
                              setBarsBefore(prev => ({ ...prev, [tf]: val }))
                            }}
                            className={`w-14 px-2 py-1.5 bg-slate-700 rounded text-white text-sm text-center ${
                              isChangedBefore ? 'border-2 border-yellow-400 ring-1 ring-yellow-400' : 'border border-slate-600'
                            } focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500`}
                          />
                          {isChangedBefore && <span className="text-yellow-400 text-xs font-bold">*</span>}
                        </div>
                      </td>

                      {/* Before Filled Duration */}
                      <td className="py-3 px-3 text-center">
                        <span className="text-xs text-blue-300 bg-blue-900/20 px-2 py-1 rounded">
                          {durationBefore || '—'}
                        </span>
                      </td>

                      {/* After Filled Input */}
                      <td className="py-3 px-3">
                        <div className="flex items-center justify-center gap-1">
                          <input
                            type="number"
                            min="0"
                            value={barsAfter}
                            onChange={(e) => {
                              const val = parseInt(e.target.value) || 0
                              setBarsAfter(prev => ({ ...prev, [tf]: val }))
                            }}
                            className={`w-14 px-2 py-1.5 bg-slate-700 rounded text-white text-sm text-center ${
                              isChangedAfter ? 'border-2 border-yellow-400 ring-1 ring-yellow-400' : 'border border-slate-600'
                            } focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500`}
                          />
                          {isChangedAfter && <span className="text-yellow-400 text-xs font-bold">*</span>}
                        </div>
                      </td>

                      {/* After Filled Duration */}
                      <td className="py-3 px-3 text-center">
                        <span className="text-xs text-green-300 bg-green-900/20 px-2 py-1 rounded">
                          {durationAfter || '—'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Save Button */}
          <div className="flex items-center gap-3 p-4 bg-slate-800/30 rounded-lg border border-slate-700">
            <Button
              size="sm"
              disabled={savingMaxBars || !hasMaxBarsChanges}
              onClick={async () => {
                setSavingMaxBars(true)
                try {
                  // Determine which settings to save based on selected strategy type
                  let beforeFilledData: MaxOpenBarsConfig
                  let afterFilledData: MaxOpenBarsConfig
                  let strategyType: string | undefined

                  if (maxBarsStrategyType === 'global') {
                    beforeFilledData = maxOpenBarsBeforeFilled
                    afterFilledData = maxOpenBarsAfterFilled
                    strategyType = undefined
                  } else if (maxBarsStrategyType === 'price_based') {
                    beforeFilledData = maxOpenBarsBeforeFilledPriceBased
                    afterFilledData = maxOpenBarsAfterFilledPriceBased
                    strategyType = 'price_based'
                  } else {
                    beforeFilledData = maxOpenBarsBeforeFilledSpreadBased
                    afterFilledData = maxOpenBarsAfterFilledSpreadBased
                    strategyType = 'spread_based'
                  }

                  // Save before filled
                  const resBeforeFilled = await fetch('/api/bot/simulator/monitor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      action: 'set-max-bars',
                      type: 'before_filled',
                      max_open_bars: beforeFilledData,
                      ...(strategyType && { strategy_type: strategyType })
                    })
                  })
                  if (!resBeforeFilled.ok) throw new Error('Failed to save before_filled settings')
                  const dataBeforeFilled = await resBeforeFilled.json()

                  // Update the correct state based on strategy type
                  const beforeFilledKey = strategyType
                    ? `max_open_bars_before_filled_${strategyType}`
                    : 'max_open_bars_before_filled'
                  if (dataBeforeFilled[beforeFilledKey]) {
                    if (maxBarsStrategyType === 'global') {
                      setSavedMaxOpenBarsBeforeFilled(dataBeforeFilled[beforeFilledKey])
                      setMaxOpenBarsBeforeFilled(dataBeforeFilled[beforeFilledKey])
                    } else if (maxBarsStrategyType === 'price_based') {
                      setSavedMaxOpenBarsBeforeFilledPriceBased(dataBeforeFilled[beforeFilledKey])
                      setMaxOpenBarsBeforeFilledPriceBased(dataBeforeFilled[beforeFilledKey])
                    } else {
                      setSavedMaxOpenBarsBeforeFilledSpreadBased(dataBeforeFilled[beforeFilledKey])
                      setMaxOpenBarsBeforeFilledSpreadBased(dataBeforeFilled[beforeFilledKey])
                    }
                  }

                  // Save after filled
                  const resAfterFilled = await fetch('/api/bot/simulator/monitor', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      action: 'set-max-bars',
                      type: 'after_filled',
                      max_open_bars: afterFilledData,
                      ...(strategyType && { strategy_type: strategyType })
                    })
                  })
                  if (!resAfterFilled.ok) throw new Error('Failed to save after_filled settings')
                  const dataAfterFilled = await resAfterFilled.json()

                  // Update the correct state based on strategy type
                  const afterFilledKey = strategyType
                    ? `max_open_bars_after_filled_${strategyType}`
                    : 'max_open_bars_after_filled'
                  if (dataAfterFilled[afterFilledKey]) {
                    if (maxBarsStrategyType === 'global') {
                      setSavedMaxOpenBarsAfterFilled(dataAfterFilled[afterFilledKey])
                      setMaxOpenBarsAfterFilled(dataAfterFilled[afterFilledKey])
                    } else if (maxBarsStrategyType === 'price_based') {
                      setSavedMaxOpenBarsAfterFilledPriceBased(dataAfterFilled[afterFilledKey])
                      setMaxOpenBarsAfterFilledPriceBased(dataAfterFilled[afterFilledKey])
                    } else {
                      setSavedMaxOpenBarsAfterFilledSpreadBased(dataAfterFilled[afterFilledKey])
                      setMaxOpenBarsAfterFilledSpreadBased(dataAfterFilled[afterFilledKey])
                    }
                  }

                  await fetchMonitorStatus()
                } catch (err) {
                  console.error('Failed to save max open bars:', err)
                  setError(err instanceof Error ? err.message : 'Failed to save')
                } finally {
                  setSavingMaxBars(false)
                }
              }}
              variant="default"
              className="bg-blue-600 hover:bg-blue-700"
            >
              {savingMaxBars ? 'Saving...' : 'Save Settings'}
            </Button>
            {hasMaxBarsChanges && (
              <Badge variant="secondary" className="bg-yellow-900/50 text-yellow-400 border-yellow-700">
                {changedTimeframesBeforeFilled.length + changedTimeframesAfterFilled.length} unsaved change{(changedTimeframesBeforeFilled.length + changedTimeframesAfterFilled.length) > 1 ? 's' : ''}
              </Badge>
            )}
          </div>
        </CardContent>
        )}
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
                  <div key={idx} className="flex items-center gap-2 flex-wrap">
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
                    {result.timeframe && (
                      <span className="text-slate-400">• {result.timeframe}</span>
                    )}
                    <span className="text-white">• {result.symbol}</span>
                    <span className="text-blue-400">@ ${result.current_price.toFixed(4)}</span>
                    {result.position_size_usd && (
                      <span className="text-blue-300">• ${result.position_size_usd.toFixed(2)}</span>
                    )}
                    {result.risk_amount_usd && (
                      <span className="text-orange-300">• ${result.risk_amount_usd.toFixed(2)}</span>
                    )}
                    {result.instance_name && (
                      <span className="text-slate-400">• {result.instance_name}</span>
                    )}
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
                        strategy_name: instance.strategy_name,
                        instance_id: run.instance_id,
                        run_id: run.run_id,
                        boundary_time: cycle.boundary_time
                      }))
                    )
                  )
                )
                .sort((a, b) => new Date(b.trade.created_at).getTime() - new Date(a.trade.created_at).getTime())
                .map(({ trade, instance_name, strategy_name, instance_id, run_id, boundary_time: _boundaryTime }) => {
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

                  // Extract pair symbol from strategy_metadata for spread-based trades
                  const isSpreadBased = trade.strategy_type === 'spread_based'
                  // Parse strategy_metadata if it's a JSON string
                  let strategyMetadata = trade.strategy_metadata
                  if (typeof strategyMetadata === 'string') {
                    try {
                      strategyMetadata = JSON.parse(strategyMetadata)
                    } catch (e) {
                      strategyMetadata = null
                    }
                  }
                  const pairSymbol = isSpreadBased && strategyMetadata?.pair_symbol ? strategyMetadata.pair_symbol : null
                  // Pair side is opposite of main symbol side for spread-based trades
                  const pairSide = isSpreadBased ? (trade.side === 'Buy' ? 'Sell' : 'Buy') : null

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
                          rejection_reason: trade.rejection_reason,
                          strategy_type: trade.strategy_type || null,
                          strategy_name: trade.strategy_name || null,
                          strategy_metadata: trade.strategy_metadata || null
                        })
                        setChartMode('live')
                      }}
                    >
                      {/* Row 1: Instance info + Symbol(s) + Side + Alert */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1 text-[10px] text-slate-500">
                            <div className="flex items-center gap-1">
                              <span className="bg-slate-700 px-1.5 py-0.5 rounded" title="Instance Name">{instance_name}</span>
                              {strategy_name && (
                                <span className="text-slate-400">• {strategy_name}</span>
                              )}
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(instance_id)
                                  setCopiedId(instance_id)
                                  setCopiedType('rec')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`p-0.5 rounded transition-all ${
                                  copiedId === instance_id && copiedType === 'rec'
                                    ? 'bg-purple-600/50 text-purple-300'
                                    : 'hover:bg-purple-600/30 text-slate-500 hover:text-purple-400'
                                }`}
                                title="Copy Instance ID"
                              >
                                {copiedId === instance_id && copiedType === 'rec' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                            <span>›</span>
                            <div className="flex items-center gap-1">
                              <span className="bg-slate-700/50 px-1 py-0.5 rounded font-mono" title="Run ID">{run_id.slice(0, 6)}</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(run_id)
                                  setCopiedId(run_id)
                                  setCopiedType('run')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`p-0.5 rounded transition-all ${
                                  copiedId === run_id && copiedType === 'run'
                                    ? 'bg-blue-600/50 text-blue-300'
                                    : 'hover:bg-blue-600/30 text-slate-500 hover:text-blue-400'
                                }`}
                                title="Copy Run ID"
                              >
                                {copiedId === run_id && copiedType === 'run' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          </div>
                          {/* Spread-based pair display */}
                          {isSpreadBased && pairSymbol ? (
                            <span className="font-bold text-white text-lg">
                              {trade.symbol} [{trade.side}] ⟷ {pairSymbol} [{pairSide || 'Sell'}]
                            </span>
                          ) : (
                            <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          )}
                          <span className={`text-xs px-2 py-1 rounded font-semibold ${isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                            {trade.side}
                          </span>
                          {rrRatio && <span className="text-xs bg-blue-900/30 text-blue-300 px-2 py-1 rounded">RR: {rrRatio.toFixed(1)}</span>}
                          {trade.timeframe && <span className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">{trade.timeframe}</span>}
                          {isSpreadBased && (() => {
                            const pairPrice = currentPrices[pairSymbol || '']
                            const zScoreData = calculateZScoreDistance(trade, pairPrice)
                            if (zScoreData) {
                              const { zScore, distance, threshold } = zScoreData
                              const isClose = distance < 0.2
                              const isCritical = distance < 0
                              return (
                                <span
                                  className={`text-xs px-2 py-1 rounded font-semibold ${
                                    isCritical
                                      ? 'bg-red-900/50 text-red-300 animate-pulse'
                                      : isClose
                                      ? 'bg-yellow-900/50 text-yellow-300'
                                      : 'bg-purple-900/30 text-purple-300'
                                  }`}
                                  title={`Z-Score: ${zScore.toFixed(3)}, Exit Threshold: ±${threshold.toFixed(3)}`}
                                >
                                  σ: {distance.toFixed(3)}
                                </span>
                              )
                            }
                            return null
                          })()}
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
                                rejection_reason: trade.rejection_reason,
                                strategy_type: trade.strategy_type || null,
                                strategy_name: trade.strategy_name || null,
                                strategy_metadata: trade.strategy_metadata || null
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

                      {/* Row 3: Prices + Position + Risk + PnL */}
                      <div className="flex items-center gap-6 flex-wrap">
                        <div className="flex items-center gap-4 text-sm">
                          <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                          <div><span className="text-green-400">TP:</span> <span className="text-green-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                          <div><span className="text-red-400">SL:</span> <span className="text-red-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                          <div><span className="text-slate-400">Qty:</span> <span className="text-white font-mono">{trade.quantity}</span></div>
                        </div>

                        {/* Position Size and Risk Amount */}
                        {(trade.position_size_usd || trade.risk_amount_usd) && (
                          <div className="flex items-center gap-3 bg-slate-700/50 rounded px-3 py-1.5 text-xs">
                            {trade.position_size_usd && (
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400">Position:</span>
                                <span className="text-blue-300 font-mono">${trade.position_size_usd.toFixed(2)}</span>
                              </div>
                            )}
                            {trade.position_size_usd && trade.risk_amount_usd && (
                              <span className="text-slate-600">•</span>
                            )}
                            {trade.risk_amount_usd && (
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400">Risk:</span>
                                <span className="text-orange-300 font-mono">${trade.risk_amount_usd.toFixed(2)}</span>
                              </div>
                            )}
                          </div>
                        )}

                        {lastChecked && (
                          <div className="flex items-center gap-2 bg-yellow-900/20 border border-yellow-700/50 rounded px-3 py-1">
                            <Clock className="w-3 h-3 text-yellow-500" />
                            <span className="text-yellow-400 font-mono">${lastChecked.price.toFixed(4)}</span>
                            <span className="text-[10px] text-yellow-600">{new Date(lastChecked.checkedAt).toLocaleTimeString()}</span>
                          </div>
                        )}

                        {/* Only show current price and PnL for filled trades */}
                        {isFilled && currentPrice && (
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

                      </div>

                      {/* ID Line - Bottom of card */}
                      <div className="mt-3 pt-3 border-t border-slate-700/50 bg-slate-800/20 -mx-4 -mb-4 px-4 py-3 rounded-b-lg">
                        <div className="flex flex-wrap gap-2 font-mono text-xs">
                          {/* Strategy Name - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Strategy:</span>
                            <span className="font-semibold">{trade.strategy_name || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_name || 'unknown')
                                setCopiedId(`strategy-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Name"
                            >
                              {copiedId === `strategy-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Strategy Type - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Type:</span>
                            <span className="font-semibold">{trade.strategy_type || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_type || 'unknown')
                                setCopiedId(`strategy-type-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-type-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Type"
                            >
                              {copiedId === `strategy-type-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Instance ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Instance:</span>
                            <span className="text-slate-200">{instance_id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(instance_id)
                                setCopiedId(`instance-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `instance-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Instance ID"
                            >
                              {copiedId === `instance-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Trade ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Trade:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`trade-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `trade-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Trade ID"
                            >
                              {copiedId === `trade-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Recommendation ID */}
                          {trade.id && (
                            <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                              <span className="text-slate-500">Rec:</span>
                              <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.id)
                                  setCopiedId(`rec-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `rec-${trade.id}` && copiedType === 'id'
                                    ? 'bg-slate-600/50 text-slate-300'
                                    : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                                }`}
                                title="Copy Recommendation ID"
                              >
                                {copiedId === `rec-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}

                          {/* Order ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Order:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`order-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `order-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Order ID"
                            >
                              {copiedId === `order-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Pair Order ID (spread-based only) */}
                          {isSpreadBased && trade.order_id_pair && (
                            <div className="flex items-center gap-1 bg-purple-900/20 px-2 py-1 rounded border border-purple-700/50">
                              <span className="text-purple-400">Pair:</span>
                              <span className="text-purple-200">{trade.order_id_pair.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.order_id_pair!)
                                  setCopiedId(`pair-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `pair-${trade.id}` && copiedType === 'id'
                                    ? 'bg-purple-600/50 text-purple-300'
                                    : 'hover:bg-purple-600/30 text-purple-500 hover:text-purple-300'
                                }`}
                                title="Copy Pair Order ID"
                              >
                                {copiedId === `pair-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
            </div>
          )}
        </CardContent>
      </Card>

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
                .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                .map(trade => {
                  const isWin = trade.pnl > 0
                  const isLong = trade.side === 'Buy'
                  // Extract pair symbol from strategy_metadata for spread-based trades
                  const isSpreadBased = trade.strategy_type === 'spread_based'
                  // Parse strategy_metadata if it's a JSON string
                  let strategyMetadata = trade.strategy_metadata
                  if (typeof strategyMetadata === 'string') {
                    try {
                      strategyMetadata = JSON.parse(strategyMetadata)
                    } catch (e) {
                      strategyMetadata = null
                    }
                  }
                  const pairSymbol = isSpreadBased && strategyMetadata?.pair_symbol ? strategyMetadata.pair_symbol : null
                  // Pair side is opposite of main symbol side for spread-based trades
                  const pairSide = isSpreadBased ? (trade.side === 'Buy' ? 'Sell' : 'Buy') : null

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
                          exit_reason: trade.exit_reason,
                          strategy_type: trade.strategy_type || null,
                          strategy_name: trade.strategy_name || null,
                          strategy_metadata: trade.strategy_metadata || null
                        })
                        setChartMode('historical')
                      }}
                    >
                      {/* Row 1: Instance + Symbol(s) + Side + Result + Date */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          <div className="flex items-center gap-1 text-[10px] text-slate-500">
                            <div className="flex items-center gap-1">
                              <span className="bg-slate-700 px-1.5 py-0.5 rounded" title="Instance Name">{trade.instance_name}</span>
                              {trade.instance_id && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    navigator.clipboard.writeText(trade.instance_id)
                                    setCopiedId(trade.instance_id)
                                    setCopiedType('rec')
                                    setTimeout(() => {
                                      setCopiedId(null)
                                      setCopiedType(null)
                                    }, 2000)
                                  }}
                                  className={`p-0.5 rounded transition-all ${
                                    copiedId === trade.instance_id && copiedType === 'rec'
                                      ? 'bg-purple-600/50 text-purple-300'
                                      : 'hover:bg-purple-600/30 text-slate-500 hover:text-purple-400'
                                  }`}
                                  title="Copy Instance ID"
                                >
                                  {copiedId === trade.instance_id && copiedType === 'rec' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                                </button>
                              )}
                            </div>
                            <span>›</span>
                            <div className="flex items-center gap-1">
                              <span className="bg-slate-700/50 px-1 py-0.5 rounded font-mono" title="Run ID">{trade.run_id?.slice(0, 6)}</span>
                              {trade.run_id && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    navigator.clipboard.writeText(trade.run_id)
                                    setCopiedId(trade.run_id)
                                    setCopiedType('run')
                                    setTimeout(() => {
                                      setCopiedId(null)
                                      setCopiedType(null)
                                    }, 2000)
                                  }}
                                  className={`p-0.5 rounded transition-all ${
                                    copiedId === trade.run_id && copiedType === 'run'
                                      ? 'bg-green-600/50 text-green-300'
                                      : 'hover:bg-green-600/30 text-slate-500 hover:text-green-400'
                                  }`}
                                  title="Copy Run ID"
                                >
                                  {copiedId === trade.run_id && copiedType === 'run' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                                </button>
                              )}
                            </div>
                          </div>
                          {/* Spread-based pair display */}
                          {isSpreadBased && pairSymbol ? (
                            <span className="font-bold text-white text-lg">
                              {trade.symbol} [{trade.side}] ⟷ {pairSymbol} [{pairSide || 'Sell'}]
                            </span>
                          ) : (
                            <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          )}
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
                          <button
                            onClick={async (e) => {
                              e.stopPropagation()
                              try {
                                const res = await fetch('/api/bot/simulator/reset-trade', {
                                  method: 'POST',
                                  headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ tradeId: trade.id })
                                })
                                if (res.ok) {
                                  // Refresh closed trades list
                                  await fetchClosedTrades()
                                } else {
                                  console.error('Failed to reset trade')
                                }
                              } catch (err) {
                                console.error('Reset trade error:', err)
                              }
                            }}
                            className="p-1.5 bg-slate-700 hover:bg-blue-600 rounded text-slate-400 hover:text-blue-300 transition-colors"
                            title="Reset trade to paper_trade status"
                          >
                            <RotateCcw className="w-4 h-4" />
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
                      <div className="flex items-center gap-6 text-sm flex-wrap">
                        <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-400">Exit:</span> <span className={`font-mono ${isWin ? 'text-green-400' : 'text-red-400'}`}>${trade.exit_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">TP:</span> <span className="text-slate-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">SL:</span> <span className="text-slate-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                        {/* Trade ID with Copy Button */}
                        <div className="flex items-center gap-2 ml-auto">
                          <span className="text-[10px] text-slate-600 font-mono" title="Trade ID">{trade.id.slice(0, 8)}...</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              navigator.clipboard.writeText(trade.id)
                              setCopiedId(trade.id)
                              setCopiedType('trade')
                              setTimeout(() => {
                                setCopiedId(null)
                                setCopiedType(null)
                              }, 2000)
                            }}
                            className={`p-1 rounded transition-all ${
                              copiedId === trade.id && copiedType === 'trade'
                                ? 'bg-green-600/50 text-green-300'
                                : 'hover:bg-green-600/30 text-slate-500 hover:text-green-400'
                            }`}
                            title="Copy Trade ID"
                          >
                            {copiedId === trade.id && copiedType === 'trade' ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                          </button>
                        </div>
                      </div>

                      {/* Row 4: Position Sizing Metrics */}
                      {(trade.position_size_usd || trade.risk_amount_usd) && (
                        <div className="flex items-center gap-6 text-sm mt-2 pt-2 border-t border-slate-700">
                          {trade.position_size_usd && (
                            <div><span className="text-slate-500">Position:</span> <span className="text-blue-400 font-mono">${trade.position_size_usd?.toFixed(2)}</span></div>
                          )}
                          {trade.risk_amount_usd && (
                            <div><span className="text-slate-500">Risk:</span> <span className="text-orange-400 font-mono">${trade.risk_amount_usd?.toFixed(2)}</span></div>
                          )}
                          {trade.sizing_method && (
                            <div><span className="text-slate-600 text-xs">({trade.sizing_method})</span></div>
                          )}
                        </div>
                      )}

                      {/* ID Line - Bottom of card */}
                      <div className="mt-3 pt-3 border-t border-slate-700/50 bg-slate-800/20 -mx-4 -mb-4 px-4 py-3 rounded-b-lg">
                        <div className="flex flex-wrap gap-2 font-mono text-xs">
                          {/* Strategy Name - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Strategy:</span>
                            <span className="font-semibold">{trade.strategy_name || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_name || 'unknown')
                                setCopiedId(`strategy-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Name"
                            >
                              {copiedId === `strategy-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Strategy Type - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Type:</span>
                            <span className="font-semibold">{trade.strategy_type || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_type || 'unknown')
                                setCopiedId(`strategy-type-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-type-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Type"
                            >
                              {copiedId === `strategy-type-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Instance ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Instance:</span>
                            <span className="text-slate-200">{trade.instance_id?.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.instance_id || '')
                                setCopiedId(`instance-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `instance-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Instance ID"
                            >
                              {copiedId === `instance-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Trade ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Trade:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`trade-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `trade-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Trade ID"
                            >
                              {copiedId === `trade-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Recommendation ID */}
                          {trade.id && (
                            <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                              <span className="text-slate-500">Rec:</span>
                              <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.id)
                                  setCopiedId(`rec-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `rec-${trade.id}` && copiedType === 'id'
                                    ? 'bg-slate-600/50 text-slate-300'
                                    : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                                }`}
                                title="Copy Recommendation ID"
                              >
                                {copiedId === `rec-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}

                          {/* Order ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Order:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`order-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `order-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Order ID"
                            >
                              {copiedId === `order-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Pair Order ID (spread-based only) */}
                          {isSpreadBased && trade.order_id_pair && (
                            <div className="flex items-center gap-1 bg-purple-900/20 px-2 py-1 rounded border border-purple-700/50">
                              <span className="text-purple-400">Pair:</span>
                              <span className="text-purple-200">{trade.order_id_pair.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.order_id_pair!)
                                  setCopiedId(`pair-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `pair-${trade.id}` && copiedType === 'id'
                                    ? 'bg-purple-600/50 text-purple-300'
                                    : 'hover:bg-purple-600/30 text-purple-500 hover:text-purple-300'
                                }`}
                                title="Copy Pair Order ID"
                              >
                                {copiedId === `pair-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}
                        </div>
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
                .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                .map(trade => {
                  const isWin = trade.pnl > 0
                  const isLong = trade.side === 'Buy'
                  // Extract pair symbol from strategy_metadata for spread-based trades
                  const isSpreadBased = trade.strategy_type === 'spread_based'
                  // Parse strategy_metadata if it's a JSON string
                  let strategyMetadata = trade.strategy_metadata
                  if (typeof strategyMetadata === 'string') {
                    try {
                      strategyMetadata = JSON.parse(strategyMetadata)
                    } catch (e) {
                      strategyMetadata = null
                    }
                  }
                  const pairSymbol = isSpreadBased && strategyMetadata?.pair_symbol ? strategyMetadata.pair_symbol : null
                  // Pair side is opposite of main symbol side for spread-based trades
                  const pairSide = isSpreadBased ? (trade.side === 'Buy' ? 'Sell' : 'Buy') : null

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
                          exit_reason: trade.exit_reason,
                          strategy_type: trade.strategy_type || null,
                          strategy_name: trade.strategy_name || null,
                          strategy_metadata: trade.strategy_metadata || null
                        })
                        setChartMode('historical')
                      }}
                    >
                      {/* Row 0: Instance Info */}
                      <div className="flex items-center gap-1 text-[10px] text-slate-500 mb-2">
                        <div className="flex items-center gap-1">
                          <span className="bg-slate-700 px-1.5 py-0.5 rounded" title="Instance Name">{trade.instance_name}</span>
                          {trade.strategy_name && (
                            <span className="text-slate-400">• {trade.strategy_name}</span>
                          )}
                          {trade.instance_id && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.instance_id)
                                setCopiedId(trade.instance_id)
                                setCopiedType('rec')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`p-0.5 rounded transition-all ${
                                copiedId === trade.instance_id && copiedType === 'rec'
                                  ? 'bg-purple-600/50 text-purple-300'
                                  : 'hover:bg-purple-600/30 text-slate-500 hover:text-purple-400'
                              }`}
                              title="Copy Instance ID"
                            >
                              {copiedId === trade.instance_id && copiedType === 'rec' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          )}
                        </div>
                        <span>›</span>
                        <div className="flex items-center gap-1">
                          <span className="bg-slate-700/50 px-1 py-0.5 rounded font-mono" title="Run ID">{trade.run_id?.slice(0, 6)}</span>
                          {trade.run_id && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.run_id)
                                setCopiedId(trade.run_id)
                                setCopiedType('run')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`p-0.5 rounded transition-all ${
                                copiedId === trade.run_id && copiedType === 'run'
                                  ? 'bg-orange-600/50 text-orange-300'
                                  : 'hover:bg-orange-600/30 text-slate-500 hover:text-orange-400'
                              }`}
                              title="Copy Run ID"
                            >
                              {copiedId === trade.run_id && copiedType === 'run' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Row 1: Symbol(s) + Side + Cancelled Badge + P&L */}
                      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                        <div className="flex items-center gap-3">
                          {/* Spread-based pair display */}
                          {isSpreadBased && pairSymbol ? (
                            <span className="font-bold text-white text-lg">
                              {trade.symbol} [{trade.side}] ⟷ {pairSymbol} [{pairSide || 'Sell'}]
                            </span>
                          ) : (
                            <span className="font-bold text-white text-xl">{trade.symbol}</span>
                          )}
                          <span className={`text-xs px-2 py-1 rounded font-semibold ${isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                            {trade.side}
                          </span>
                          <span className="text-sm px-3 py-1 rounded font-bold bg-orange-500 text-white">
                            ⏱️ CANCELLED
                          </span>
                          {trade.exit_reason && (
                            <span className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded ml-2">
                              {trade.exit_reason === 'max_bars_exceeded' ? 'Max Bars Exceeded' : trade.exit_reason}
                            </span>
                          )}
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
                          <span className="text-orange-500 font-semibold">⏱️ Cancelled:</span>
                          <span className="text-orange-500 font-semibold">
                            {trade.cancelled_at ? new Date(trade.cancelled_at).toLocaleString() : "--"}
                          </span>
                        </div>
                        {trade.bars_open !== undefined && (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-400">-</span>
                            <span className="text-slate-300">{trade.bars_open} bars</span>
                          </div>
                        )}
                        {!trade.closed_at && (
                          <div className="flex items-center gap-1">
                            <span className="text-slate-400">-</span>
                            <span className="text-orange-500 text-xs font-semibold">(before fill)</span>
                          </div>
                        )}
                      </div>

                      {/* Row 3: Prices */}
                      <div className="flex items-center gap-6 text-sm mb-3">
                        <div><span className="text-slate-400">Entry:</span> <span className="text-white font-mono">${trade.entry_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-400">Exit:</span> <span className={`font-mono ${isWin ? 'text-green-400' : 'text-red-400'}`}>${trade.exit_price?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">TP:</span> <span className="text-slate-400 font-mono">${trade.take_profit?.toFixed(4)}</span></div>
                        <div><span className="text-slate-500">SL:</span> <span className="text-slate-400 font-mono">${trade.stop_loss?.toFixed(4)}</span></div>
                      </div>

                      {/* ID Line - Bottom of card */}
                      <div className="mt-3 pt-3 border-t border-orange-600/30 bg-orange-900/10 -mx-4 -mb-4 px-4 py-3 rounded-b-lg">
                        <div className="flex flex-wrap gap-2 font-mono text-xs">
                          {/* Strategy Name - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Strategy:</span>
                            <span className="font-semibold">{trade.strategy_name || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_name || 'unknown')
                                setCopiedId(`strategy-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Name"
                            >
                              {copiedId === `strategy-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Strategy Type - Color Coded */}
                          <div className={`flex items-center gap-1 px-2 py-1 rounded border ${getStrategyTypeColor(trade.strategy_type)}`}>
                            <span className="opacity-70">Type:</span>
                            <span className="font-semibold">{trade.strategy_type || 'unknown'}</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.strategy_type || 'unknown')
                                setCopiedId(`strategy-type-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `strategy-type-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Strategy Type"
                            >
                              {copiedId === `strategy-type-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Instance ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Instance:</span>
                            <span className="text-slate-200">{trade.instance_id?.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.instance_id || '')
                                setCopiedId(`instance-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `instance-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Instance ID"
                            >
                              {copiedId === `instance-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Trade ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Trade:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`trade-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `trade-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Trade ID"
                            >
                              {copiedId === `trade-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Recommendation ID */}
                          {trade.id && (
                            <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                              <span className="text-slate-500">Rec:</span>
                              <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.id)
                                  setCopiedId(`rec-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `rec-${trade.id}` && copiedType === 'id'
                                    ? 'bg-slate-600/50 text-slate-300'
                                    : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                                }`}
                                title="Copy Recommendation ID"
                              >
                                {copiedId === `rec-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}

                          {/* Order ID */}
                          <div className="flex items-center gap-1 bg-slate-800/40 px-2 py-1 rounded border border-slate-700/50">
                            <span className="text-slate-500">Order:</span>
                            <span className="text-slate-200">{trade.id.slice(0, 8)}...</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                navigator.clipboard.writeText(trade.id)
                                setCopiedId(`order-${trade.id}`)
                                setCopiedType('id')
                                setTimeout(() => {
                                  setCopiedId(null)
                                  setCopiedType(null)
                                }, 2000)
                              }}
                              className={`ml-1 p-0.5 rounded transition-all ${
                                copiedId === `order-${trade.id}` && copiedType === 'id'
                                  ? 'bg-slate-600/50 text-slate-300'
                                  : 'hover:bg-slate-600/30 text-slate-500 hover:text-slate-300'
                              }`}
                              title="Copy Order ID"
                            >
                              {copiedId === `order-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                            </button>
                          </div>

                          {/* Pair Order ID (spread-based only) */}
                          {isSpreadBased && trade.order_id_pair && (
                            <div className="flex items-center gap-1 bg-purple-900/20 px-2 py-1 rounded border border-purple-700/50">
                              <span className="text-purple-400">Pair:</span>
                              <span className="text-purple-200">{trade.order_id_pair.slice(0, 8)}...</span>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  navigator.clipboard.writeText(trade.order_id_pair!)
                                  setCopiedId(`pair-${trade.id}`)
                                  setCopiedType('id')
                                  setTimeout(() => {
                                    setCopiedId(null)
                                    setCopiedType(null)
                                  }, 2000)
                                }}
                                className={`ml-1 p-0.5 rounded transition-all ${
                                  copiedId === `pair-${trade.id}` && copiedType === 'id'
                                    ? 'bg-purple-600/50 text-purple-300'
                                    : 'hover:bg-purple-600/30 text-purple-500 hover:text-purple-300'
                                }`}
                                title="Copy Pair Order ID"
                              >
                                {copiedId === `pair-${trade.id}` && copiedType === 'id' ? <Check className="w-2.5 h-2.5" /> : <Copy className="w-2.5 h-2.5" />}
                              </button>
                            </div>
                          )}
                        </div>
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


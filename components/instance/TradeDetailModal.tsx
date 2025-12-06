'use client'

import { useState, useEffect, useRef } from 'react'
import { X, TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { createChart, IChartApi, CandlestickSeries, CandlestickData, Time, ISeriesApi, createSeriesMarkers } from 'lightweight-charts'
import { Card, CardContent } from '@/components/ui/card'

interface TradeRow {
  id: string
  symbol: string
  side: string
  entry_price: number
  stop_loss: number
  take_profit: number
  fill_price: number | null
  exit_price: number | null
  pnl: number | null
  pnl_percent: number | null
  confidence: number | null
  rr_ratio: number | null
  created_at: string
  filled_at: string | null
  closed_at: string | null
  submitted_at: string | null
  status: string
  timeframe: string | null
  dry_run: number
  rejection_reason: string | null
}

interface TradeDetailModalProps {
  isOpen: boolean
  onClose: () => void
  trade: TradeRow | null
}

interface Candle {
  time: number
  open: number
  high: number
  low: number
  close: number
}

// Helper function to calculate RR ratio
function calculateRR(trade: TradeRow): number | null {
  const { entry_price, stop_loss, take_profit, side } = trade
  if (!entry_price || !stop_loss || !take_profit) return null

  const isLong = side === 'Buy'
  const risk = isLong ? (entry_price - stop_loss) : (stop_loss - entry_price)
  const reward = isLong ? (take_profit - entry_price) : (entry_price - take_profit)

  if (risk <= 0) return null
  return reward / risk
}

export function TradeDetailModal({ isOpen, onClose, trade }: TradeDetailModalProps) {
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(false)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)

  // Load candles when trade changes
  useEffect(() => {
    if (!isOpen || !trade) return

    const loadCandles = async () => {
      setLoading(true)
      try {
        // Use filled_at timestamp if available, otherwise use created_at
        const timestamp = trade.filled_at ? new Date(trade.filled_at).getTime() : new Date(trade.created_at).getTime()
        const timeframe = trade.timeframe || '1h'

        console.log(`[TradeDetailModal] Fetching candles for ${trade.symbol} ${timeframe} at ${timestamp}`)

        // Retry logic for reliability
        let retries = 3
        let lastError: Error | null = null

        while (retries > 0) {
          try {
            const res = await fetch(`/api/bot/trade-candles?symbol=${trade.symbol}&timeframe=${timeframe}&timestamp=${timestamp}&before=50&after=20`, {
              signal: AbortSignal.timeout(30000) // 30 second timeout
            })

            if (!res.ok) {
              throw new Error(`HTTP ${res.status}`)
            }

            const data = await res.json()

            if (data.error) {
              throw new Error(data.error)
            } else if (data.candles && data.candles.length > 0) {
              console.log(`[TradeDetailModal] Loaded ${data.candles.length} candles`)
              setCandles(data.candles)
              return // Success
            } else {
              throw new Error('No candles returned')
            }
          } catch (err) {
            lastError = err instanceof Error ? err : new Error(String(err))
            retries--
            if (retries > 0) {
              console.warn(`[TradeDetailModal] Retry ${4 - retries}/3: ${lastError.message}`)
              await new Promise(resolve => setTimeout(resolve, 1000)) // Wait 1s before retry
            }
          }
        }

        if (lastError) {
          console.error('[TradeDetailModal] Failed after retries:', lastError.message)
        }
      } catch (error) {
        console.error('[TradeDetailModal] Failed to load candles:', error)
      } finally {
        setLoading(false)
      }
    }

    loadCandles()
  }, [isOpen, trade])

  // Cleanup chart when modal closes
  useEffect(() => {
    if (!isOpen) {
      if (chartRef.current) {
        console.log('[TradeDetailModal] Cleaning up chart on modal close')
        chartRef.current.remove()
        chartRef.current = null
        candleSeriesRef.current = null
      }
      setCandles([])
    }
  }, [isOpen])

  // Create chart
  useEffect(() => {
    if (!isOpen || !chartContainerRef.current || !candles.length) return

    // Clean up existing chart before creating new one
    if (chartRef.current) {
      console.log('[TradeDetailModal] Cleaning up existing chart before recreating')
      chartRef.current.remove()
      chartRef.current = null
      candleSeriesRef.current = null
    }

    const timer = setTimeout((): void => {
      if (!chartContainerRef.current || chartRef.current) return

      try {
        const containerWidth = chartContainerRef.current.clientWidth || 600
        const containerHeight = chartContainerRef.current.clientHeight || 400

        console.log('[TradeDetailModal] Creating chart with', candles.length, 'candles')

        const chart = createChart(chartContainerRef.current, {
          layout: { background: { color: '#1e293b' }, textColor: '#94a3b8' },
          grid: { vertLines: { color: '#334155' }, horzLines: { color: '#334155' } },
          width: containerWidth,
          height: containerHeight,
          crosshair: { mode: 1 },
          timeScale: { timeVisible: true, secondsVisible: false },
        })

        chartRef.current = chart
        const series = chart.addSeries(CandlestickSeries, {
          upColor: '#22c55e',
          downColor: '#ef4444',
          borderUpColor: '#22c55e',
          borderDownColor: '#ef4444',
          wickUpColor: '#22c55e',
          wickDownColor: '#ef4444',
        })

        candleSeriesRef.current = series
        series.setData(candles as CandlestickData<Time>[])

        // Add price lines
        if (trade) {
          if (trade.entry_price) series.createPriceLine({ price: trade.entry_price, color: '#3b82f6', lineWidth: 2, title: 'Entry' })
          if (trade.stop_loss) series.createPriceLine({ price: trade.stop_loss, color: '#ef4444', lineWidth: 2, title: 'SL' })
          if (trade.take_profit) series.createPriceLine({ price: trade.take_profit, color: '#22c55e', lineWidth: 2, title: 'TP' })
          if (trade.exit_price) {
            const exitColor = (trade.pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444'
            series.createPriceLine({ price: trade.exit_price, color: exitColor, lineWidth: 2, title: 'Exit' })
          }
        }

        // Add markers for entry and fill times
        const markers: any[] = []
        if (trade) {
          const isLong = trade.side === 'Buy'

          // Helper function to find closest candle to a timestamp
          const findClosestCandle = (targetTime: number) => {
            return candles.reduce((closest, candle) => {
              const candleTime = candle.time as number
              const closestTime = closest ? (closest.time as number) : 0
              return Math.abs(candleTime - targetTime) < Math.abs(closestTime - targetTime) ? candle : closest
            }, candles[0])
          }

          // Entry marker (when trade was created/submitted)
          const entryTime = trade.submitted_at || trade.created_at
          if (entryTime) {
            const entryTimestamp = Math.floor(new Date(entryTime).getTime() / 1000)
            const closestCandle = findClosestCandle(entryTimestamp)
            if (closestCandle) {
              markers.push({
                time: closestCandle.time,
                position: isLong ? 'belowBar' as const : 'aboveBar' as const,
                color: '#3b82f6',
                shape: 'circle' as const,
                text: 'Entry',
              })
            }
          }

          // Fill marker (when trade was actually filled)
          if (trade.filled_at) {
            const fillTimestamp = Math.floor(new Date(trade.filled_at).getTime() / 1000)
            const closestCandle = findClosestCandle(fillTimestamp)
            if (closestCandle) {
              markers.push({
                time: closestCandle.time,
                position: isLong ? 'belowBar' as const : 'aboveBar' as const,
                color: '#10b981',
                shape: isLong ? 'arrowUp' as const : 'arrowDown' as const,
                text: 'Filled',
              })
            }
          }

          // Exit marker (when trade was closed)
          if (trade.closed_at) {
            const exitTimestamp = Math.floor(new Date(trade.closed_at).getTime() / 1000)
            const closestCandle = findClosestCandle(exitTimestamp)
            if (closestCandle) {
              markers.push({
                time: closestCandle.time,
                position: isLong ? 'aboveBar' as const : 'belowBar' as const,
                color: trade.pnl !== null && trade.pnl >= 0 ? '#22c55e' : '#ef4444',
                shape: isLong ? 'arrowDown' as const : 'arrowUp' as const,
                text: 'Exit',
              })
            }
          }
        }

        if (markers.length > 0) {
          // Sort markers by time (required by lightweight-charts)
          markers.sort((a, b) => Number(a.time) - Number(b.time))
          createSeriesMarkers(series, markers)
        }

        chart.timeScale().fitContent()
      } catch (err) {
        console.error('[TradeDetailModal] Chart creation error:', err)
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
        }
      }
    }, 100)

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      clearTimeout(timer)
      window.removeEventListener('resize', handleResize)
    }
  }, [isOpen, candles, trade])

  if (!isOpen || !trade) return null

  const setupQuality = trade.confidence ? trade.confidence * 0.4 : 0
  const rrScore = trade.rr_ratio ? Math.min(1, trade.rr_ratio / 3) * 0.25 : 0
  const marketScore = trade.confidence ? trade.confidence * 0.35 : 0

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <Card className="bg-slate-800 border-slate-700 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <CardContent className="p-6">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              {trade.side === 'Buy' ? <TrendingUp className="text-green-400" /> : <TrendingDown className="text-red-400" />}
              <h2 className="text-2xl font-bold text-white">{trade.symbol}</h2>
              <span className={`px-3 py-1 rounded text-sm font-bold ${trade.side === 'Buy' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'}`}>
                {trade.side === 'Buy' ? 'LONG' : 'SHORT'}
              </span>

              {/* Trade Type Badge */}
              <span className={`px-3 py-1 rounded text-xs font-bold ${
                trade.dry_run === 1 ? 'bg-yellow-900 text-yellow-300' : 'bg-blue-900 text-blue-300'
              }`}>
                {trade.dry_run === 1 ? '📄 PAPER' : '💰 LIVE'}
              </span>

              {/* Status Badge */}
              <span className={`px-3 py-1 rounded text-xs font-bold ${
                trade.status === 'filled' || trade.status === 'closed' ? 'bg-green-900 text-green-300'
                : trade.status === 'rejected' ? 'bg-red-900 text-red-300'
                : trade.status === 'cancelled' ? 'bg-orange-900 text-orange-300'
                : 'bg-slate-700 text-slate-300'
              }`}>
                {trade.status === 'paper_trade' ? 'Paper' : trade.status.toUpperCase()}
              </span>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-white"><X size={24} /></button>
          </div>

          {/* Rejection Reason Alert */}
          {trade.status === 'rejected' && trade.rejection_reason && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg">
              <div className="text-red-300 text-sm">
                <span className="font-bold">Rejection Reason:</span> {trade.rejection_reason}
              </div>
            </div>
          )}

          {/* Chart */}
          <div className="mb-6 bg-slate-700/50 rounded-lg overflow-hidden relative">
            <div ref={chartContainerRef} className="w-full h-[400px]" />
            {loading && <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80"><Loader2 className="animate-spin text-blue-400" size={32} /></div>}
          </div>

          {/* Trade Details Grid */}
          <div className="grid grid-cols-4 gap-4 mb-6">
            <div className="bg-slate-700 rounded-lg p-4">
              <div className="text-slate-400 text-xs mb-1">Entry Price</div>
              <div className="text-white font-mono text-lg">${trade.entry_price.toFixed(4)}</div>
              <div className="text-slate-500 text-xs mt-1">{trade.filled_at ? new Date(trade.filled_at).toLocaleString() : '-'}</div>
            </div>
            <div className="bg-slate-700 rounded-lg p-4">
              <div className="text-slate-400 text-xs mb-1">Stop Loss</div>
              <div className="text-red-400 font-mono text-lg">${trade.stop_loss.toFixed(4)}</div>
              <div className="text-slate-500 text-xs mt-1">Risk: {((trade.entry_price - trade.stop_loss) / trade.entry_price * 100).toFixed(2)}%</div>
            </div>
            <div className="bg-slate-700 rounded-lg p-4">
              <div className="text-slate-400 text-xs mb-1">Take Profit</div>
              <div className="text-green-400 font-mono text-lg">${trade.take_profit.toFixed(4)}</div>
              <div className="text-slate-500 text-xs mt-1">Reward: {((trade.take_profit - trade.entry_price) / trade.entry_price * 100).toFixed(2)}%</div>
            </div>
            <div className="bg-slate-700 rounded-lg p-4">
              <div className="text-slate-400 text-xs mb-1">R:R Ratio</div>
              <div className={`font-mono text-lg ${(() => {
                const rr = trade.rr_ratio ?? calculateRR(trade)
                return rr && rr >= 1 ? 'text-green-400' : 'text-yellow-400'
              })()}`}>
                {(() => {
                  const rr = trade.rr_ratio ?? calculateRR(trade)
                  return rr ? `1:${rr.toFixed(2)}` : '-'
                })()}
              </div>
              <div className="text-slate-500 text-xs mt-1">Status: {trade.status}</div>
            </div>
          </div>

          {/* Confidence Breakdown */}
          {trade.confidence && (
            <div className="bg-slate-700/50 rounded-lg p-4 mb-6">
              <h3 className="text-white font-semibold mb-3">Confidence Calculation</h3>
              <div className="bg-slate-700 rounded p-3 font-mono text-sm mb-3">
                <span className="text-blue-400">Confidence</span> = <span className="text-green-400">{(setupQuality).toFixed(3)}</span> + <span className="text-yellow-400">{(rrScore).toFixed(3)}</span> + <span className="text-purple-400">{(marketScore).toFixed(3)}</span> = <span className="text-white font-bold">{trade.confidence.toFixed(3)}</span>
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div className="bg-slate-700 rounded p-2 text-center"><div className="text-green-400 font-bold">40%</div><div className="text-slate-400 text-xs">Setup Quality</div></div>
                <div className="bg-slate-700 rounded p-2 text-center"><div className="text-yellow-400 font-bold">25%</div><div className="text-slate-400 text-xs">R:R Ratio</div></div>
                <div className="bg-slate-700 rounded p-2 text-center"><div className="text-purple-400 font-bold">35%</div><div className="text-slate-400 text-xs">Market Env</div></div>
              </div>
            </div>
          )}

          {/* P&L */}
          {trade.pnl !== null && (
            <div className={`rounded-lg p-4 ${trade.pnl >= 0 ? 'bg-green-900/30 border border-green-500' : 'bg-red-900/30 border border-red-500'}`}>
              <div className="flex items-center justify-between">
                <span className="text-slate-300">Realized P&L:</span>
                <div className="text-right">
                  <div className={`text-2xl font-bold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>${trade.pnl.toFixed(2)}</div>
                  <div className={`text-sm ${trade.pnl_percent && trade.pnl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>{trade.pnl_percent ? `${trade.pnl_percent >= 0 ? '+' : ''}${trade.pnl_percent.toFixed(2)}%` : '-'}</div>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}


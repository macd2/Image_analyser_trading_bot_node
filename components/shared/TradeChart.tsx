'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickSeries, CandlestickData, Time, createSeriesMarkers } from 'lightweight-charts'
import { useBybitKlineWebSocket } from '@/hooks/useBybitKlineWebSocket'

export interface TradeData {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  stop_loss: number | null
  take_profit: number | null
  exit_price?: number | null
  status: string
  submitted_at?: string | null
  filled_at?: string | null
  fill_time?: string | null  // When price touched entry (simulated fill)
  fill_price?: number | null // Price at which trade was filled
  closed_at?: string | null
  created_at: string
  timeframe?: string | null
  // Additional fields for display
  dry_run?: number | null  // 1 = paper trade, 0 = live trade
  rejection_reason?: string | null
  exit_reason?: string | null
}

interface TradeChartProps {
  trade: TradeData
  height?: number
  mode?: 'live' | 'historical'
}

const TIMEFRAME_MAP: Record<string, string> = {
  '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
  '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
  '1d': 'D', '1w': 'W', '1M': 'M'
}

export default function TradeChart({ trade, height = 400, mode = 'live' }: TradeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [candles, setCandles] = useState<CandlestickData<Time>[]>([])
  const [chartReady, setChartReady] = useState(false)
  const [dataRendered, setDataRendered] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [wsEnabled, setWsEnabled] = useState(false)
  const [priceDecimals, setPriceDecimals] = useState<number>(4)
  const initialLoadRef = useRef(true)

  // Show loading until data is rendered on chart (or there's an error)
  const loading = !dataRendered && !error

  const getBybitInterval = (tf: string | null): string => TIMEFRAME_MAP[tf || '1h'] || '60'

  // Track if component is mounted to avoid state updates after unmount
  const isMountedRef = useRef(true)

  // Reset state when trade changes
  useEffect(() => {
    console.log('[TradeChart] Trade changed, resetting state for:', trade.symbol)
    setCandles([])
    setDataRendered(false)
    setError(null)
    setWsEnabled(false)
    initialLoadRef.current = true

    // Cleanup resize handler before destroying chart
    if (resizeHandlerRef.current) {
      window.removeEventListener('resize', resizeHandlerRef.current)
      resizeHandlerRef.current = null
    }

    // Destroy existing chart so it can be recreated fresh
    if (chartRef.current) {
      console.log('[TradeChart] Destroying old chart')
      try {
        chartRef.current.remove()
      } catch (e) {
        console.warn('[TradeChart] Error removing chart:', e)
      }
      chartRef.current = null
      candleSeriesRef.current = null
      setChartReady(false)
    }
  }, [trade.id, trade.symbol])

  // Store resize handler in ref for cleanup
  const resizeHandlerRef = useRef<(() => void) | null>(null)

  // Helper to get decimals from a price
  const getDecimalsFromPrice = (price: number | null | undefined): number => {
    if (!price) return 0
    const str = price.toString()
    if (!str.includes('.')) return 0
    return str.split('.')[1]?.length || 0
  }

  // Calculate minimum required decimals from trade prices
  const tradePriceDecimals = Math.max(
    getDecimalsFromPrice(trade.entry_price),
    getDecimalsFromPrice(trade.stop_loss),
    getDecimalsFromPrice(trade.take_profit),
    getDecimalsFromPrice(trade.exit_price)
  )

  // WebSocket update handler
  const handleKlineUpdate = useCallback((kline: { start: number; open: string; high: string; low: string; close: string }) => {
    if (!candleSeriesRef.current) return
    const newCandle: CandlestickData<Time> = {
      time: Math.floor(kline.start / 1000) as Time,
      open: parseFloat(kline.open),
      high: parseFloat(kline.high),
      low: parseFloat(kline.low),
      close: parseFloat(kline.close),
    }
    candleSeriesRef.current.update(newCandle)
  }, [])

  // Only enable WebSocket in live mode
  useBybitKlineWebSocket({
    symbol: trade.symbol,
    interval: getBybitInterval(trade.timeframe ?? null),
    onKlineUpdate: handleKlineUpdate,
    enabled: wsEnabled && mode === 'live'
  })

  // Fetch candles
  useEffect(() => {
    const fetchCandles = async () => {
      const tradeTimestamp = trade.submitted_at || trade.filled_at || trade.created_at
      if (!tradeTimestamp) {
        console.error('[TradeChart] No timestamp available')
        setError('No timestamp available')
        return
      }

      setDataRendered(false)
      setError(null)

      try {
        const timestamp = new Date(tradeTimestamp).getTime()
        const timeframe = trade.timeframe || '1h'

        // For historical mode (closed trades), fetch candles up to closed_at
        const endTimestamp = mode === 'historical' && trade.closed_at
          ? new Date(trade.closed_at).getTime()
          : undefined

        let url = `/api/bot/trade-candles?symbol=${trade.symbol}&timeframe=${timeframe}&timestamp=${timestamp}&before=50&after=20`
        if (endTimestamp) {
          url += `&endTimestamp=${endTimestamp}`
        }

        console.log('[TradeChart] Fetching candles:', url)
        const res = await fetch(url)
        const data = await res.json()
        console.log('[TradeChart] Response:', data)

        if (data.error) {
          console.error('[TradeChart] API error:', data.error)
          setError(data.error)
        } else if (data.candles && data.candles.length > 0) {
          console.log('[TradeChart] Setting candles:', data.candles.length)
          setCandles(data.candles)
          // Use max of API precision and trade price precision
          const apiDecimals = data.precision?.priceDecimals ?? 4
          setPriceDecimals(Math.max(apiDecimals, tradePriceDecimals, 4))
          // Enable WebSocket only in live mode
          if (mode === 'live') setWsEnabled(true)
        } else {
          console.error('[TradeChart] No candles in response')
          setError('No candles found')
        }
      } catch (err) {
        console.error('[TradeChart] Fetch error:', err)
        setError('Failed to fetch candles')
      }
    }

    fetchCandles()
    return () => setWsEnabled(false)
  }, [trade.symbol, trade.submitted_at, trade.filled_at, trade.created_at, trade.closed_at, trade.timeframe, mode, tradePriceDecimals])

  // Create chart - recreate when chartReady is false (after reset) or on mount
  useEffect(() => {
    // Skip if chart already exists or container not ready
    if (chartReady || !chartContainerRef.current || chartRef.current) return

    const timer = setTimeout(() => {
      if (!chartContainerRef.current || chartRef.current) return
      console.log('[TradeChart] Creating chart')
      const chart = createChart(chartContainerRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        width: chartContainerRef.current.clientWidth || 600,
        height,
        crosshair: { mode: 1 },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: {
          autoScale: true,
          scaleMargins: { top: 0.1, bottom: 0.1 },
          borderVisible: false,
          ticksVisible: true,
          mode: 0, // Normal mode - shows all prices
        },
        localization: { priceFormatter: (price: number) => price.toFixed(priceDecimals) },
      })
      chartRef.current = chart
      setChartReady(true)
      console.log('[TradeChart] Chart created and ready')

      // Create and store resize handler for cleanup
      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth, height })
        }
      }
      resizeHandlerRef.current = handleResize
      window.addEventListener('resize', handleResize)
    }, 100)

    return () => clearTimeout(timer)
  }, [chartReady, height, priceDecimals])

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      console.log('[TradeChart] Unmounting, cleaning up')
      isMountedRef.current = false
      if (resizeHandlerRef.current) {
        window.removeEventListener('resize', resizeHandlerRef.current)
      }
      if (chartRef.current) {
        try {
          chartRef.current.remove()
        } catch (e) {
          console.warn('[TradeChart] Error removing chart on unmount:', e)
        }
        chartRef.current = null
      }
    }
  }, [])

  // Set data and add price lines/markers
  useEffect(() => {
    console.log('[TradeChart] Data effect - chartReady:', chartReady, 'chartRef:', !!chartRef.current, 'candles:', candles.length)
    if (!chartReady || !chartRef.current || candles.length === 0) return

    try {
      // Remove old series if it exists
      if (candleSeriesRef.current && chartRef.current) {
        console.log('[TradeChart] Removing old series')
        chartRef.current.removeSeries(candleSeriesRef.current)
        candleSeriesRef.current = null
      }

      if (!chartRef.current) return // Chart may have been disposed

      console.log('[TradeChart] Adding new series with', candles.length, 'candles')
      const series = chartRef.current.addSeries(CandlestickSeries, {
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      })
      candleSeriesRef.current = series
      series.setData(candles)
      console.log('[TradeChart] Data set on series')

      const formatPrice = (p: number) => p.toFixed(priceDecimals)

      // Price lines
      if (trade.entry_price) {
        series.createPriceLine({ price: trade.entry_price, color: '#3b82f6', lineWidth: 2, lineStyle: 2, title: `Entry ${formatPrice(trade.entry_price)}` })
      }
      if (trade.stop_loss) {
        series.createPriceLine({ price: trade.stop_loss, color: '#ef4444', lineWidth: 1, lineStyle: 1, title: `SL ${formatPrice(trade.stop_loss)}` })
      }
      if (trade.take_profit) {
        series.createPriceLine({ price: trade.take_profit, color: '#22c55e', lineWidth: 1, lineStyle: 1, title: `TP ${formatPrice(trade.take_profit)}` })
      }
    if (trade.exit_price) {
      series.createPriceLine({ price: trade.exit_price, color: '#f59e0b', lineWidth: 2, lineStyle: 0, title: `Exit ${formatPrice(trade.exit_price)}` })
    }

    // Markers - Signal (when created), Fill (when entry touched), Exit (when closed)
    const markers: { time: Time; position: string; color: string; shape: string; text: string }[] = []
    // Normalize side to handle both 'Buy'/'Sell' and 'LONG'/'SHORT' formats
    const sideUpper = trade.side?.toUpperCase() || ''
    const isLong = sideUpper === 'BUY' || sideUpper === 'LONG'

    // Helper to find closest candle
    const findClosestCandle = (timestamp: number) =>
      candles.reduce((c, candle) =>
        Math.abs((candle.time as number) - timestamp) < Math.abs((c.time as number) - timestamp) ? candle : c
      , candles[0])

    // 1. Signal marker - when the trade signal was created
    const signalTs = trade.created_at
    if (signalTs) {
      const signalTime = Math.floor(new Date(signalTs).getTime() / 1000)
      const closestSignal = findClosestCandle(signalTime)
      if (closestSignal) {
        markers.push({
          time: closestSignal.time,
          position: 'belowBar',
          color: '#3b82f6',
          shape: 'circle',
          text: 'Signal',
        })
      }
    }

    // 2. Fill marker - when entry price was touched (simulated fill)
    const fillTs = trade.fill_time || trade.filled_at
    if (fillTs) {
      const fillTime = Math.floor(new Date(fillTs).getTime() / 1000)
      const closestFill = findClosestCandle(fillTime)
      if (closestFill) {
        markers.push({
          time: closestFill.time,
          position: isLong ? 'belowBar' : 'aboveBar',
          color: '#f59e0b',
          shape: isLong ? 'arrowUp' : 'arrowDown',
          text: 'Fill',
        })
      }
    }

    // 3. Exit marker - when trade was closed (SL/TP hit)
    if (trade.closed_at && trade.exit_price) {
      const closedTime = Math.floor(new Date(trade.closed_at).getTime() / 1000)
      const closestExit = findClosestCandle(closedTime)
      if (closestExit) {
        const isWin = trade.exit_reason === 'tp_hit'
        markers.push({
          time: closestExit.time,
          position: isLong ? 'aboveBar' : 'belowBar',
          color: isWin ? '#22c55e' : '#ef4444',
          shape: isLong ? 'arrowDown' : 'arrowUp',
          text: isWin ? 'TP Hit' : 'SL Hit',
        })
      }
    }

    if (markers.length > 0) {
      markers.sort((a, b) => Number(a.time) - Number(b.time))
      createSeriesMarkers(series, markers as any)
    }

      if (initialLoadRef.current && chartRef.current) {
        chartRef.current.timeScale().fitContent()
        initialLoadRef.current = false
      }

      // Wait for the chart to actually render before hiding loading spinner
      // Check isMountedRef to avoid state updates after unmount
      requestAnimationFrame(() => {
        if (isMountedRef.current) {
          setDataRendered(true)
          console.log('[TradeChart] Data rendered successfully')
        }
      })
    } catch (e) {
      console.warn('[TradeChart] Error setting data on chart (may be disposed):', e)
    }
  }, [candles, trade, priceDecimals, chartReady])

  return (
    <div className="relative w-full bg-slate-900" style={{ height }}>
      <div ref={chartContainerRef} className="w-full h-full rounded-lg overflow-hidden bg-[#0f172a]" />
      {mode === 'live' && wsEnabled && (
        <div className="absolute top-2 right-2 flex items-center gap-1.5 bg-green-900/80 px-2 py-1 rounded text-xs text-green-400">
          <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
          LIVE
        </div>
      )}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#0f172a] rounded-lg z-10">
          <div className="text-white flex flex-col items-center gap-2">
            <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
            <div className="text-sm">Loading chart...</div>
          </div>
        </div>
      )}
      {error && !loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#0f172a] rounded-lg z-10">
          <div className="text-red-400 text-sm">{error}</div>
        </div>
      )}
    </div>
  )
}


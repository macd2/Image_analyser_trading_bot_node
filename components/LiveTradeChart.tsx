'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, IChartApi, ISeriesApi, CandlestickSeries, CandlestickData, Time, createSeriesMarkers } from 'lightweight-charts'
import { useBybitKlineWebSocket } from '@/hooks/useBybitKlineWebSocket'

interface Trade {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  stop_loss: number | null
  take_profit: number | null
  exit_price: number | null
  status: string
  submitted_at: string | null
  filled_at: string | null
  fill_time?: string | null  // When price touched entry (simulated fill)
  fill_price?: number | null // Price at which trade was filled
  closed_at: string | null
  created_at: string
  timeframe: string | null
  exit_reason?: string | null
}

interface LiveTradeChartProps {
  trade: Trade
  height?: number
}

export default function LiveTradeChart({ trade, height = 400 }: LiveTradeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const [candles, setCandles] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsEnabled, setWsEnabled] = useState(false)
  const [fetchStatus, setFetchStatus] = useState<string>('loading')
  const [priceDecimals, setPriceDecimals] = useState<number | null>(null) // null until loaded
  const initialLoadRef = useRef(true) // Track if this is the initial load

  // Convert timeframe to Bybit WebSocket interval format
  const getBybitInterval = (timeframe: string | null): string => {
    const mapping: Record<string, string> = {
      '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
      '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
      '1d': 'D', '1w': 'W', '1M': 'M'
    }
    return mapping[timeframe || '1h'] || '60'
  }

  // Handle real-time kline updates from WebSocket
  const handleKlineUpdate = useCallback((kline: any) => {
    if (!candleSeriesRef.current) {
      console.log('[LiveTradeChart] Received kline but series not ready yet')
      return
    }

    // Bybit sends timestamp in milliseconds, convert to seconds for lightweight-charts
    const timeInSeconds = Math.floor(kline.start / 1000) as Time

    const newCandle: CandlestickData<Time> = {
      time: timeInSeconds,
      open: parseFloat(kline.open),
      high: parseFloat(kline.high),
      low: parseFloat(kline.low),
      close: parseFloat(kline.close),
    }

    // Update chart directly - no state update to avoid re-renders
    candleSeriesRef.current.update(newCandle)
  }, [])

  // WebSocket connection for real-time updates
  useBybitKlineWebSocket({
    symbol: trade.symbol,
    interval: getBybitInterval(trade.timeframe),
    onKlineUpdate: handleKlineUpdate,
    enabled: wsEnabled
  })

  // Fetch candles for the trade
  useEffect(() => {
    const fetchCandles = async () => {
      // Use submitted_at, filled_at, or created_at as timestamp
      const tradeTimestamp = trade.submitted_at || trade.filled_at || trade.created_at

      if (!tradeTimestamp) {
        setError('No timestamp available for this trade')
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const timestamp = new Date(tradeTimestamp).getTime()
        const timeframe = trade.timeframe || '1h'

        const res = await fetch(
          `/api/bot/trade-candles?symbol=${trade.symbol}&timeframe=${timeframe}&timestamp=${timestamp}&before=50&after=20`
        )
        const data = await res.json()

        if (data.error) {
          setError(data.error)
          setFetchStatus('error')
        } else if (data.candles && data.candles.length > 0) {
          setCandles(data.candles)
          setFetchStatus(data.fetch_status || 'loaded')
          // Set price precision from API response
          if (data.precision?.priceDecimals !== undefined) {
            setPriceDecimals(data.precision.priceDecimals)
          }
          // Enable WebSocket after historical data is loaded
          setWsEnabled(true)
        } else {
          setError('No candles found')
          setFetchStatus('error')
        }
      } catch (err) {
        console.error('Failed to fetch candles:', err)
        setError('Failed to fetch candles')
      } finally {
        setLoading(false)
      }
    }

    fetchCandles()

    // Cleanup: disable WebSocket when component unmounts
    return () => setWsEnabled(false)
  }, [trade.symbol, trade.submitted_at, trade.filled_at, trade.created_at, trade.timeframe])

  // Helper to format price with correct decimals
  const formatPrice = useCallback((price: number) => {
    return price.toFixed(priceDecimals ?? 2)
  }, [priceDecimals])

  // Create chart (only once)
  useEffect(() => {
    if (!chartContainerRef.current || chartRef.current) return

    const timer = setTimeout(() => {
      if (!chartContainerRef.current) return

      const containerWidth = chartContainerRef.current.clientWidth || 600
      const containerHeight = height

      const chart = createChart(chartContainerRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        width: containerWidth,
        height: containerHeight,
        crosshair: { mode: 1 },
        timeScale: { timeVisible: true, secondsVisible: false },
        rightPriceScale: {
          mode: 0, // Normal mode
        },
      })

      chartRef.current = chart

      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
            height: containerHeight
          })
        }
      }
      window.addEventListener('resize', handleResize)

      return () => {
        window.removeEventListener('resize', handleResize)
        if (chartRef.current) {
          chartRef.current.remove()
          chartRef.current = null
        }
      }
    }, 100)

    return () => clearTimeout(timer)
  }, [height])

  // Update chart price formatter when precision changes
  useEffect(() => {
    if (!chartRef.current || priceDecimals === null) return

    chartRef.current.applyOptions({
      localization: {
        priceFormatter: (price: number) => price.toFixed(priceDecimals),
      },
    })
  }, [priceDecimals])

  // Initialize series once when chart is ready, candles are loaded, and precision is known
  useEffect(() => {
    if (!chartRef.current || candles.length === 0 || priceDecimals === null) return

    // Only create series on initial load (when series doesn't exist yet)
    if (candleSeriesRef.current) {
      // Series already exists - don't recreate or call setData
      // Live updates are handled by series.update() in the WebSocket handler
      return
    }

    // Create new candlestick series (only on first load)
    const series = chartRef.current.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    })
    candleSeriesRef.current = series

    // Set candle data (only on initial load)
    series.setData(candles as CandlestickData<Time>[])

    // Add price lines for Entry, SL, TP with proper precision
    if (trade.entry_price) {
      series.createPriceLine({
        price: trade.entry_price,
        color: '#3b82f6',
        lineWidth: 2,
        lineStyle: 2,
        title: `Entry ${formatPrice(trade.entry_price)}`,
      })
    }

    if (trade.stop_loss) {
      series.createPriceLine({
        price: trade.stop_loss,
        color: '#ef4444',
        lineWidth: 1,
        lineStyle: 1,
        title: `SL ${formatPrice(trade.stop_loss)}`,
      })
    }

    if (trade.take_profit) {
      series.createPriceLine({
        price: trade.take_profit,
        color: '#22c55e',
        lineWidth: 1,
        lineStyle: 1,
        title: `TP ${formatPrice(trade.take_profit)}`,
      })
    }

    // Add exit price line if trade is closed
    if (trade.exit_price) {
      series.createPriceLine({
        price: trade.exit_price,
        color: '#f59e0b',
        lineWidth: 2,
        lineStyle: 0,
        title: `Exit ${formatPrice(trade.exit_price)}`,
      })
    }

    // Add markers for trade events - Signal, Fill, Exit
    const markers: any[] = []
    const isLong = trade.side === 'Buy'

    // Helper to find closest candle
    const findClosestCandle = (timestamp: number) =>
      candles.reduce((closest, candle) => {
        const candleTime = candle.time as number
        const closestTime = closest ? (closest.time as number) : 0
        return Math.abs(candleTime - timestamp) < Math.abs(closestTime - timestamp) ? candle : closest
      }, candles[0])

    // 1. Signal marker - when the trade signal was created
    const signalTs = trade.created_at
    if (signalTs) {
      const signalTime = Math.floor(new Date(signalTs).getTime() / 1000)
      const closestSignal = findClosestCandle(signalTime)
      if (closestSignal) {
        // Position signal marker above/below based on side
        const signalPosition = isLong ? 'belowBar' : 'aboveBar'
        markers.push({
          time: closestSignal.time,
          position: signalPosition,
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
        // Position marker based on where exit price is relative to candle close
        const candleClose = closestExit.close as number
        const exitAboveCandle = trade.exit_price > candleClose
        const markerPosition: 'aboveBar' | 'belowBar' = exitAboveCandle ? 'aboveBar' : 'belowBar'

        markers.push({
          time: closestExit.time,
          position: markerPosition,
          color: isWin ? '#22c55e' : '#ef4444',
          shape: isLong ? 'arrowDown' : 'arrowUp',
          text: isWin ? 'TP Hit' : 'SL Hit',
        })
      }
    }

    if (markers.length > 0) {
      // Sort markers by time (required by lightweight-charts)
      markers.sort((a, b) => Number(a.time) - Number(b.time))
      createSeriesMarkers(series, markers)
    }

    // Only fit content on initial load, not on live updates
    if (initialLoadRef.current) {
      chartRef.current.timeScale().fitContent()
      initialLoadRef.current = false
    }
  }, [candles, trade, formatPrice, priceDecimals])

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={chartContainerRef} className="w-full h-full rounded-lg overflow-hidden" />
      
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 rounded-lg">
          <div className="text-white flex flex-col items-center gap-2">
            <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
            <div className="text-sm">
              {fetchStatus === 'fetching' ? 'Fetching latest candles from Bybit...' : 'Loading chart...'}
            </div>
          </div>
        </div>
      )}

      {error && !loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 rounded-lg">
          <div className="text-red-400 text-sm">{error}</div>
        </div>
      )}
    </div>
  )
}


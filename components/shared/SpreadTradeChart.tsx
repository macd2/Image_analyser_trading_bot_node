'use client'

import { useEffect, useState } from 'react'
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from 'recharts'
import { SpreadTradeData, ChartDataSet, Candle, StrategyMetadata, TradeMarker } from './SpreadTradeChart.types'
import { LoadingState, ErrorState } from './index'

interface SpreadTradeChartProps {
  trade: SpreadTradeData
  height?: number
  mode?: 'live' | 'historical'
  showAssetPrices?: boolean
}

const TIMEFRAME_MAP: Record<string, string> = {
  '1m': '1', '3m': '3', '5m': '5', '15m': '15', '30m': '30',
  '1h': '60', '2h': '120', '4h': '240', '6h': '360', '12h': '720',
  '1d': 'D', '1w': 'W', '1M': 'M'
}

export default function SpreadTradeChart({
  trade,
  height = 600,
  showAssetPrices = true,
}: SpreadTradeChartProps) {
  const [chartData, setChartData] = useState<ChartDataSet | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Parse metadata - it might come as a JSON string or object
  const parseMetadata = (meta: any): StrategyMetadata | undefined => {
    if (!meta) return undefined
    if (typeof meta === 'string') {
      try {
        return JSON.parse(meta)
      } catch {
        return undefined
      }
    }
    return meta as StrategyMetadata
  }

  const metadata = parseMetadata(trade.strategy_metadata)

  // Debug logging
  console.log('[SpreadTradeChart] Rendering for', trade.symbol, {
    raw_metadata: trade.strategy_metadata,
    parsed_metadata: metadata,
  })

  // Validate metadata
  useEffect(() => {
    if (!metadata) {
      setError('No strategy metadata found - this is not a spread-based trade')
      setLoading(false)
      return
    }

    if (!metadata.pair_symbol) {
      setError('Missing pair_symbol in strategy metadata')
      setLoading(false)
      return
    }
  }, [metadata])

  // Fetch candles and build chart data
  useEffect(() => {
    if (!metadata || !trade.symbol) return

    const fetchData = async () => {
      try {
        setLoading(true)
        setError(null)

        const timestamp = trade.submitted_at || trade.filled_at || trade.created_at
        if (!timestamp) {
          setError('No timestamp available for this trade')
          setLoading(false)
          return
        }

        const timeframe = TIMEFRAME_MAP[trade.timeframe || '1h'] || '60'

        // Fetch primary asset candles
        const primaryRes = await fetch(
          `/api/bot/trade-candles?symbol=${trade.symbol}&timeframe=${timeframe}&timestamp=${new Date(timestamp).getTime()}&before=50&after=20`
        )
        if (!primaryRes.ok) throw new Error('Failed to fetch primary candles')
        const primaryData = await primaryRes.json()

        // Fetch pair asset candles
        const pairRes = await fetch(
          `/api/bot/spread-pair-candles?pair_symbol=${metadata.pair_symbol}&timeframe=${timeframe}&timestamp=${new Date(timestamp).getTime()}&before=50&after=20`
        )
        if (!pairRes.ok) throw new Error('Failed to fetch pair candles')
        const pairData = await pairRes.json()

        // Build chart data
        const data = buildChartData(
          primaryData.candles,
          pairData.candles,
          metadata,
          trade
        )

        setChartData(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load chart data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [trade.id, trade.symbol, trade.timeframe, trade.submitted_at, trade.filled_at, trade.created_at, metadata?.pair_symbol, metadata?.z_exit_threshold])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} />
  if (!chartData) return <ErrorState message="No chart data available" />

  return (
    <div className="space-y-4">
      {/* Z-Score Pane */}
      <ZScorePane data={chartData} metadata={metadata!} height={height / 3} />

      {/* Spread Price Pane */}
      <SpreadPricePane data={chartData} metadata={metadata!} height={height / 3} />

      {/* Asset Prices Pane */}
      {showAssetPrices && (
        <AssetPricePane data={chartData} metadata={metadata!} primarySymbol={trade.symbol} height={height / 3} />
      )}
    </div>
  )
}

// ============================================================
// Z-SCORE PANE
// ============================================================

function ZScorePane({
  data,
  metadata,
  height,
}: {
  data: ChartDataSet
  metadata: StrategyMetadata
  height: number
}) {
  const chartData = data.zScores.map((point) => ({
    time: point.time,
    timeLabel: formatTimestamp(point.time),
    z_score: point.z_score,
    is_mean_reverting: point.is_mean_reverting,
  }))

  // Debug: Log marker data
  console.log('[ZScorePane] Markers:', {
    signal: data.signalMarker,
    fill: data.fillMarker,
    exit: data.exitMarker,
  })
  console.log('[ZScorePane] Chart data length:', chartData.length)
  console.log('[ZScorePane] First 3 chart data points:', chartData.slice(0, 3))

  // Find marker positions in chart data by matching timeLabel
  const findMarkerIndex = (marker: TradeMarker | undefined): number => {
    if (!marker) {
      console.log('[ZScorePane] Marker is undefined')
      return -1
    }
    console.log(`[ZScorePane] Looking for marker "${marker.label}" with timeLabel "${marker.timeLabel}"`)
    console.log('[ZScorePane] Chart data length:', chartData.length)
    console.log('[ZScorePane] First 5 timeLabels:', chartData.slice(0, 5).map(d => d.timeLabel))
    const index = chartData.findIndex(d => d.timeLabel === marker.timeLabel)
    console.log(`[ZScorePane] Found marker at index: ${index}`)
    if (index < 0) {
      console.warn(`[ZScorePane] Marker NOT found! Available timeLabels (all):`, chartData.map(d => d.timeLabel))
    }
    return index
  }

  const signalIndex = findMarkerIndex(data.signalMarker)
  const fillIndex = findMarkerIndex(data.fillMarker)
  const exitIndex = findMarkerIndex(data.exitMarker)

  console.log('[ZScorePane] Final marker indices:', { signalIndex, fillIndex, exitIndex })

  // Custom dot renderer for markers
  const MarkerDot = (props: any) => {
    const { cx, cy, fill, r, stroke, strokeWidth } = props
    console.log('[ZScorePane] MarkerDot rendered:', { cx, cy, fill, r, stroke, strokeWidth })
    return (
      <circle
        cx={cx}
        cy={cy}
        r={r || 6}
        fill={fill}
        stroke={stroke || 'white'}
        strokeWidth={strokeWidth || 2}
      />
    )
  }

  // Calculate dynamic Y-axis domain based on data
  const zScores = data.zScores.map(p => p.z_score)
  const minZ = Math.min(...zScores)
  const maxZ = Math.max(...zScores)
  const padding = (maxZ - minZ) * 0.15 // 15% padding
  const yDomain = [minZ - padding, maxZ + padding]

  // Generate nice tick values
  const tickCount = 5
  const tickInterval = (yDomain[1] - yDomain[0]) / (tickCount - 1)
  const yTicks = Array.from({ length: tickCount }, (_, i) => yDomain[0] + i * tickInterval)



  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Z-Score (Entry/Exit Signals)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timeLabel"
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            interval={Math.max(0, Math.floor(chartData.length / 6))}
          />
          <YAxis
            stroke="#94a3b8"
            type="number"
            domain={[yDomain[0], yDomain[1]]}
            ticks={yTicks}
            tickFormatter={(value) => typeof value === 'number' ? value.toFixed(3) : String(value)}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
            formatter={(value: any) => {
              if (typeof value === 'number') return value.toFixed(3)
              return value
            }}
          />
          <Legend
            wrapperStyle={{ paddingTop: '10px' }}
            formatter={(value) => {
              const legendLabels: Record<string, string> = {
                'Z-Score': 'Z-Score (Statistical Signal)',
              }
              return legendLabels[value] || value
            }}
          />

          {/* Background shading for mean-reverting zones */}
          <ReferenceLine y={0} stroke="#64748b" strokeDasharray="5 5" label="Mean (μ)" />
          <ReferenceLine
            y={2.0}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label="Entry (±2.0σ)"
          />
          <ReferenceLine
            y={-2.0}
            stroke="#10b981"
            strokeDasharray="3 3"
            label="Entry (±2.0σ)"
          />
          <ReferenceLine
            y={metadata.z_exit_threshold}
            stroke="#94a3b8"
            strokeDasharray="2 2"
            label={`Exit (+${metadata.z_exit_threshold}σ)`}
          />
          <ReferenceLine
            y={-metadata.z_exit_threshold}
            stroke="#94a3b8"
            strokeDasharray="2 2"
            label={`Exit (-${metadata.z_exit_threshold}σ)`}
          />

          <Line
            type="monotone"
            dataKey="z_score"
            stroke="#f59e0b"
            dot={false}
            strokeWidth={2}
            name="Z-Score"
            isAnimationActive={false}
          />

          {/* Render signal marker using ReferenceDot with correct x/y values */}
          {signalIndex >= 0 && data.signalMarker && (
            <ReferenceDot
              x={data.signalMarker.timeLabel}
              y={data.zScores[signalIndex].z_score}
              r={5}
              fill={data.signalMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.signalMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// ============================================================
// SPREAD PRICE PANE
// ============================================================

function SpreadPricePane({
  data,
  metadata,
  height,
}: {
  data: ChartDataSet
  metadata: StrategyMetadata
  height: number
}) {
  const chartData = data.spreads.map((point) => ({
    time: point.time,
    timeLabel: formatTimestamp(point.time),
    spread: point.spread,
    mean: point.spread_mean,
    upper_entry: point.spread_mean + 2 * point.spread_std,
    lower_entry: point.spread_mean - 2 * point.spread_std,
    upper_stop: point.spread_mean + 3.5 * point.spread_std,
    lower_stop: point.spread_mean - 3.5 * point.spread_std,
  }))

  // Find marker positions in chart data
  const findMarkerIndex = (marker: TradeMarker | undefined): number => {
    if (!marker) return -1
    const index = chartData.findIndex(d => d.timeLabel === marker.timeLabel)
    if (index >= 0) {
      console.log(`[SpreadPricePane] Found ${marker.label} marker at index ${index}, timeLabel: ${marker.timeLabel}`)
    } else {
      console.warn(`[SpreadPricePane] Could not find ${marker.label} marker with timeLabel: ${marker.timeLabel}`)
      console.warn(`[SpreadPricePane] Available timeLabels (first 5):`, chartData.slice(0, 5).map(d => d.timeLabel))
    }
    return index
  }

  const signalIndex = findMarkerIndex(data.signalMarker)
  const fillIndex = findMarkerIndex(data.fillMarker)
  const exitIndex = findMarkerIndex(data.exitMarker)

  // Custom dot renderer for markers
  const MarkerDot = (props: any) => {
    const { cx, cy, fill, r, stroke, strokeWidth } = props
    return (
      <circle
        cx={cx}
        cy={cy}
        r={r || 6}
        fill={fill}
        stroke={stroke || 'white'}
        strokeWidth={strokeWidth || 2}
      />
    )
  }

  // Debug logging
  if (chartData.length > 0) {
    console.log('[SpreadPricePane] First data point:', chartData[0])
    console.log('[SpreadPricePane] Spread values:', data.spreads.slice(0, 3).map(p => p.spread))
  }

  // Calculate dynamic Y-axis domain based on data AND reference lines
  const spreads = data.spreads.map(p => p.spread)
  const minSpread = Math.min(...spreads)
  const maxSpread = Math.max(...spreads)

  // Include reference lines in domain calculation
  const upperStop = metadata.spread_mean + 3.5 * metadata.spread_std
  const lowerStop = metadata.spread_mean - 3.5 * metadata.spread_std

  const minValue = Math.min(minSpread, lowerStop)
  const maxValue = Math.max(maxSpread, upperStop)
  const padding = (maxValue - minValue) * 0.15 // 15% padding
  const yDomain = [minValue - padding, maxValue + padding]

  // Generate nice tick values
  const tickCount = 5
  const tickInterval = (yDomain[1] - yDomain[0]) / (tickCount - 1)
  const yTicks = Array.from({ length: tickCount }, (_, i) => yDomain[0] + i * tickInterval)



  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Spread Price (Risk Management)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timeLabel"
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            interval={Math.max(0, Math.floor(chartData.length / 6))}
          />
          <YAxis
            stroke="#94a3b8"
            type="number"
            domain={[yDomain[0], yDomain[1]]}
            ticks={yTicks}
            tickFormatter={(value) => typeof value === 'number' ? value.toFixed(6) : String(value)}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
            formatter={(value: any) => {
              if (typeof value === 'number') return value.toFixed(6)
              return value
            }}
          />
          <Legend
            wrapperStyle={{ paddingTop: '10px' }}
            formatter={(value) => {
              const legendLabels: Record<string, string> = {
                'spread': 'Spread Price (Y - β×X)',
              }
              return legendLabels[value] || value
            }}
          />

          {/* Statistical boundaries */}
          <ReferenceLine y={metadata.spread_mean} stroke="#64748b" label="μ (Mean)" />
          <ReferenceLine
            y={metadata.spread_mean + 2 * metadata.spread_std}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label="Short Entry (μ+2σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean - 2 * metadata.spread_std}
            stroke="#10b981"
            strokeDasharray="3 3"
            label="Long Entry (μ-2σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean + 3.5 * metadata.spread_std}
            stroke="#8b5cf6"
            strokeDasharray="2 2"
            label="Short Stop (μ+3.5σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean - 3.5 * metadata.spread_std}
            stroke="#8b5cf6"
            strokeDasharray="2 2"
            label="Long Stop (μ-3.5σ)"
          />

          <Line
            type="monotone"
            dataKey="spread"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={2}
            name="spread"
          />

          {/* Render signal marker */}
          {signalIndex >= 0 && data.signalMarker && (
            <ReferenceDot
              x={data.signalMarker.timeLabel}
              y={data.spreads[signalIndex].spread}
              r={5}
              fill={data.signalMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.signalMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {/* Render fill marker */}
          {fillIndex >= 0 && data.fillMarker && (
            <ReferenceDot
              x={data.fillMarker.timeLabel}
              y={data.spreads[fillIndex].spread}
              r={5}
              fill={data.fillMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.fillMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {/* Render exit marker */}
          {exitIndex >= 0 && data.exitMarker && (
            <ReferenceDot
              x={data.exitMarker.timeLabel}
              y={data.spreads[exitIndex].spread}
              r={5}
              fill={data.exitMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.exitMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// ============================================================
// ASSET PRICES PANE
// ============================================================

function AssetPricePane({
  data,
  metadata,
  primarySymbol,
  height,
}: {
  data: ChartDataSet
  metadata: StrategyMetadata
  primarySymbol: string
  height: number
}) {

  const chartData = data.prices.map((point) => ({
    time: point.time,
    timeLabel: formatTimestamp(point.time),
    price_x: point.price_x,
    price_y: point.price_y,
  }))

  // Find marker positions in chart data
  const findMarkerIndex = (marker: TradeMarker | undefined): number => {
    if (!marker) return -1
    const index = chartData.findIndex(d => d.timeLabel === marker.timeLabel)
    if (index >= 0) {
      console.log(`[AssetPricePane] Found ${marker.label} marker at index ${index}, timeLabel: ${marker.timeLabel}`)
    } else {
      console.warn(`[AssetPricePane] Could not find ${marker.label} marker with timeLabel: ${marker.timeLabel}`)
      console.warn(`[AssetPricePane] Available timeLabels (first 5):`, chartData.slice(0, 5).map(d => d.timeLabel))
    }
    return index
  }

  const signalIndex = findMarkerIndex(data.signalMarker)
  const fillIndex = findMarkerIndex(data.fillMarker)
  const exitIndex = findMarkerIndex(data.exitMarker)

  // Custom dot renderer for markers
  const MarkerDot = (props: any) => {
    const { cx, cy, fill, r, stroke, strokeWidth } = props
    return (
      <circle
        cx={cx}
        cy={cy}
        r={r || 6}
        fill={fill}
        stroke={stroke || 'white'}
        strokeWidth={strokeWidth || 2}
      />
    )
  }

  // Calculate dynamic Y-axis domains for both assets
  const pricesX = data.prices.map(p => p.price_x)
  const pricesY = data.prices.map(p => p.price_y)

  const minX = Math.min(...pricesX)
  const maxX = Math.max(...pricesX)
  const paddingX = (maxX - minX) * 0.15
  const yDomainLeft = [minX - paddingX, maxX + paddingX]

  const minY = Math.min(...pricesY)
  const maxY = Math.max(...pricesY)
  const paddingY = (maxY - minY) * 0.15
  const yDomainRight = [minY - paddingY, maxY + paddingY]

  // Generate tick values for both axes
  const tickCountLeft = 5
  const tickIntervalLeft = (yDomainLeft[1] - yDomainLeft[0]) / (tickCountLeft - 1)
  const yTicksLeft = Array.from({ length: tickCountLeft }, (_, i) => yDomainLeft[0] + i * tickIntervalLeft)

  const tickCountRight = 5
  const tickIntervalRight = (yDomainRight[1] - yDomainRight[0]) / (tickCountRight - 1)
  const yTicksRight = Array.from({ length: tickCountRight }, (_, i) => yDomainRight[0] + i * tickIntervalRight)



  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Asset Prices (Context)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis
            dataKey="timeLabel"
            stroke="#94a3b8"
            tick={{ fontSize: 12 }}
            interval={Math.max(0, Math.floor(chartData.length / 6))}
          />
          <YAxis
            stroke="#94a3b8"
            yAxisId="left"
            type="number"
            domain={[yDomainLeft[0], yDomainLeft[1]]}
            ticks={yTicksLeft}
            tickFormatter={(value) => typeof value === 'number' ? value.toFixed(6) : String(value)}
          />
          <YAxis
            stroke="#94a3b8"
            yAxisId="right"
            orientation="right"
            type="number"
            domain={[yDomainRight[0], yDomainRight[1]]}
            ticks={yTicksRight}
            tickFormatter={(value) => typeof value === 'number' ? value.toFixed(6) : String(value)}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
            formatter={(value: any) => {
              if (typeof value === 'number') return value.toFixed(6)
              return value
            }}
          />
          <Legend
            wrapperStyle={{ paddingTop: '10px' }}
            formatter={(value) => {
              const legendLabels: Record<string, string> = {
                'price_x': `Primary Asset (${primarySymbol})`,
                'price_y': `Pair Asset (${metadata.pair_symbol})`,
              }
              return legendLabels[value] || value
            }}
          />

          <Line
            yAxisId="left"
            type="monotone"
            dataKey="price_x"
            stroke="#06b6d4"
            dot={false}
            strokeWidth={2}
            name="price_x"
          />

          {/* Markers for price_x line */}
          {signalIndex >= 0 && data.signalMarker && (
            <ReferenceDot
              x={data.signalMarker.timeLabel}
              y={data.prices[signalIndex].price_x}
              yAxisId="left"
              r={5}
              fill={data.signalMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.signalMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {fillIndex >= 0 && data.fillMarker && (
            <ReferenceDot
              x={data.fillMarker.timeLabel}
              y={data.prices[fillIndex].price_x}
              yAxisId="left"
              r={5}
              fill={data.fillMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.fillMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {exitIndex >= 0 && data.exitMarker && (
            <ReferenceDot
              x={data.exitMarker.timeLabel}
              y={data.prices[exitIndex].price_x}
              yAxisId="left"
              r={5}
              fill={data.exitMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.exitMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          <Line
            yAxisId="right"
            type="monotone"
            dataKey="price_y"
            stroke="#ec4899"
            dot={false}
            strokeWidth={2}
            name="price_y"
          />

          {/* Markers for price_y line */}
          {signalIndex >= 0 && data.signalMarker && (
            <ReferenceDot
              x={data.signalMarker.timeLabel}
              y={data.prices[signalIndex].price_y}
              yAxisId="right"
              r={5}
              fill={data.signalMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.signalMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {fillIndex >= 0 && data.fillMarker && (
            <ReferenceDot
              x={data.fillMarker.timeLabel}
              y={data.prices[fillIndex].price_y}
              yAxisId="right"
              r={5}
              fill={data.fillMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.fillMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}

          {exitIndex >= 0 && data.exitMarker && (
            <ReferenceDot
              x={data.exitMarker.timeLabel}
              y={data.prices[exitIndex].price_y}
              yAxisId="right"
              r={5}
              fill={data.exitMarker.color}
              stroke="white"
              strokeWidth={1.5}
              label={{
                value: data.exitMarker.label,
                position: 'top',
                fill: '#e2e8f0',
                fontSize: 10,
                fontWeight: 'bold',
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function buildChartData(
  primaryCandles: Candle[],
  pairCandles: Candle[],
  metadata: StrategyMetadata,
  trade: SpreadTradeData
): ChartDataSet {
  const zScores = []
  const spreads = []
  const prices = []

  // Align candles by timestamp
  const minLength = Math.min(primaryCandles.length, pairCandles.length)

  // Debug: log first timestamp to understand format
  if (minLength > 0) {
    const firstTime = primaryCandles[0].time
    console.log('[buildChartData] First candle timestamp:', firstTime, 'Type:', typeof firstTime)
    console.log('[buildChartData] Formatted:', formatTimestamp(firstTime))
  }

  for (let i = 0; i < minLength; i++) {
    const primary = primaryCandles[i]
    const pair = pairCandles[i]
    const time = primary.time

    // Calculate spread
    const spread = pair.close - metadata.beta * primary.close
    const z_score = (spread - metadata.spread_mean) / metadata.spread_std

    zScores.push({
      time,
      z_score,
      is_mean_reverting: Math.abs(z_score) < 3,
    })

    spreads.push({
      time,
      spread,
      spread_mean: metadata.spread_mean,
      spread_std: metadata.spread_std,
    })

    prices.push({
      time,
      price_x: primary.close,
      price_y: pair.close,
    })
  }

  // Helper to find closest candle time to a given timestamp
  const findClosestCandleTime = (targetTimestamp: number): number | null => {
    if (zScores.length === 0) return null

    let closest = zScores[0].time
    let minDiff = Math.abs(zScores[0].time - targetTimestamp)

    for (const point of zScores) {
      const diff = Math.abs(point.time - targetTimestamp)
      if (diff < minDiff) {
        minDiff = diff
        closest = point.time
      }
    }

    return closest
  }

  // Build markers - use closest candle time instead of exact match
  let signalMarker: TradeMarker | undefined
  if (trade.created_at) {
    const signalTime = Math.floor(new Date(trade.created_at).getTime() / 1000)
    console.log('[buildChartData] Signal creation:', {
      trade_created_at: trade.created_at,
      signalTime,
      zScoresLength: zScores.length,
      firstZScoreTime: zScores[0]?.time,
      lastZScoreTime: zScores[zScores.length - 1]?.time,
    })
    const closestTime = findClosestCandleTime(signalTime)
    console.log('[buildChartData] Closest candle time found:', closestTime)
    if (closestTime !== null) {
      const formattedLabel = formatTimestamp(closestTime)
      signalMarker = {
        timeLabel: formattedLabel,
        type: 'signal' as const,
        color: '#3b82f6',
        label: 'Signal',
      }
      console.log('[buildChartData] Signal marker created:', signalMarker)
    } else {
      console.warn('[buildChartData] No closest candle time found for signal')
    }
  } else {
    console.warn('[buildChartData] No created_at for signal marker')
  }

  let fillMarker: TradeMarker | undefined
  if (trade.filled_at || trade.fill_time) {
    const fillTime = Math.floor(new Date(trade.filled_at || trade.fill_time!).getTime() / 1000)
    const closestTime = findClosestCandleTime(fillTime)
    if (closestTime !== null) {
      fillMarker = {
        timeLabel: formatTimestamp(closestTime),
        type: 'fill' as const,
        color: '#f59e0b',
        label: 'Fill',
      }
    }
  }

  let exitMarker: TradeMarker | undefined
  if (trade.closed_at && trade.exit_price) {
    const exitTime = Math.floor(new Date(trade.closed_at).getTime() / 1000)
    const closestTime = findClosestCandleTime(exitTime)
    if (closestTime !== null) {
      exitMarker = {
        timeLabel: formatTimestamp(closestTime),
        type: 'exit' as const,
        color: trade.exit_reason === 'tp_hit' ? '#22c55e' : '#ef4444',
        label: trade.exit_reason === 'tp_hit' ? 'TP Hit' : 'SL Hit',
      }
    }
  }

  return {
    zScores,
    spreads,
    prices,
    entryTime: trade.filled_at ? new Date(trade.filled_at).getTime() : undefined,
    exitTime: trade.closed_at ? new Date(trade.closed_at).getTime() : undefined,
    signalMarker,
    fillMarker,
    exitMarker,
  }
}

// ============================================================
// HELPER: FORMAT TIMESTAMP
// ============================================================

function formatTimestamp(timestamp: number | string | null | undefined): string {
  try {
    if (!timestamp) {
      return 'Invalid'
    }

    // Convert to number if it's a string
    let ts = typeof timestamp === 'string' ? parseInt(timestamp, 10) : timestamp

    if (isNaN(ts) || ts <= 0) {
      console.warn('[formatTimestamp] Invalid timestamp value:', timestamp)
      return 'Invalid'
    }

    // Handle both milliseconds and seconds
    // Timestamps from Bybit are in milliseconds (13 digits)
    // If less than 10 billion (10^10), it's likely in seconds
    let ms = ts
    if (ts < 10000000000) {
      ms = ts * 1000
    }

    const date = new Date(ms)
    const timeMs = date.getTime()

    // Check if date is valid
    if (isNaN(timeMs)) {
      console.warn('[formatTimestamp] Invalid date from timestamp:', timestamp, 'converted ms:', ms)
      return 'Invalid'
    }

    // Format: "2025-12-20 11:09:31"
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')

    const formatted = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    return formatted
  } catch (error) {
    console.error('[formatTimestamp] Error:', timestamp, error)
    return 'Invalid'
  }
}


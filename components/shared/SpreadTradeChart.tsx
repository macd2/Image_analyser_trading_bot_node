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
} from 'recharts'
import { SpreadTradeData, ChartDataSet, Candle, StrategyMetadata } from './SpreadTradeChart.types'
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

  const metadata = trade.strategy_metadata as StrategyMetadata | undefined

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
  }, [trade, metadata])

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
        <AssetPricePane data={chartData} metadata={metadata!} height={height / 3} />
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
    z_score: point.z_score,
    is_mean_reverting: point.is_mean_reverting,
  }))

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Z-Score (Entry/Exit Signals)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="time" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
          />
          <Legend />

          {/* Background shading for mean-reverting zones */}
          <ReferenceLine y={0} stroke="#64748b" strokeDasharray="5 5" label="Mean" />
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
          />
          <ReferenceLine
            y={metadata.z_exit_threshold}
            stroke="#94a3b8"
            strokeDasharray="2 2"
            label={`Exit (${metadata.z_exit_threshold})`}
          />
          <ReferenceLine
            y={-metadata.z_exit_threshold}
            stroke="#94a3b8"
            strokeDasharray="2 2"
          />

          <Line
            type="monotone"
            dataKey="z_score"
            stroke="#f59e0b"
            dot={false}
            strokeWidth={2}
            name="Z-Score"
          />
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
    spread: point.spread,
    mean: point.spread_mean,
    upper_entry: point.spread_mean + 2 * point.spread_std,
    lower_entry: point.spread_mean - 2 * point.spread_std,
    upper_stop: point.spread_mean + 3.5 * point.spread_std,
    lower_stop: point.spread_mean - 3.5 * point.spread_std,
  }))

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Spread Price (Risk Management)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="time" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
          />
          <Legend />

          {/* Statistical boundaries */}
          <ReferenceLine y={metadata.spread_mean} stroke="#64748b" label="μ (Mean)" />
          <ReferenceLine
            y={metadata.spread_mean + 2 * metadata.spread_std}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label="Entry (μ+2σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean - 2 * metadata.spread_std}
            stroke="#10b981"
            strokeDasharray="3 3"
            label="Entry (μ-2σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean + 3.5 * metadata.spread_std}
            stroke="#8b5cf6"
            strokeDasharray="2 2"
            label="Stop (μ+3.5σ)"
          />
          <ReferenceLine
            y={metadata.spread_mean - 3.5 * metadata.spread_std}
            stroke="#8b5cf6"
            strokeDasharray="2 2"
            label="Stop (μ-3.5σ)"
          />

          <Line
            type="monotone"
            dataKey="spread"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={2}
            name="Spread"
          />
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
  height,
}: {
  data: ChartDataSet
  metadata: StrategyMetadata
  height: number
}) {
  const chartData = data.prices.map((point) => ({
    time: point.time,
    price_x: point.price_x,
    price_y: point.price_y,
  }))

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Asset Prices (Context)</h3>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="time" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" yAxisId="left" />
          <YAxis stroke="#94a3b8" yAxisId="right" orientation="right" />
          <Tooltip
            contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
            labelStyle={{ color: '#e2e8f0' }}
          />
          <Legend />

          <Line
            yAxisId="left"
            type="monotone"
            dataKey="price_x"
            stroke="#06b6d4"
            dot={false}
            strokeWidth={2}
            name={`Primary (${metadata.pair_symbol.split('USDT')[0]})`}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="price_y"
            stroke="#ec4899"
            dot={false}
            strokeWidth={2}
            name={`Pair (${metadata.pair_symbol})`}
          />
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

  return {
    zScores,
    spreads,
    prices,
    entryTime: trade.filled_at ? new Date(trade.filled_at).getTime() : undefined,
    exitTime: trade.closed_at ? new Date(trade.closed_at).getTime() : undefined,
  }
}


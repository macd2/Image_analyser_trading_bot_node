'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, LineChart, Line, ScatterChart, Scatter, ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface PositionSizingMetrics {
  avg_position_size: number
  min_position_size: number
  max_position_size: number
  median_position_size: number
  avg_risk_amount: number
  avg_risk_percentage: number
  distribution: Array<{ bucket: string; count: number; percentage: number }>
  correlation: { position_size_vs_pnl: number; position_size_vs_win_rate: number }
  by_strategy: Array<{ strategy: string; avg_position_size: number; avg_risk_amount: number; trade_count: number }>
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']

export default function PositionManagement() {
  const [metrics, setMetrics] = useState<PositionSizingMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [blinkingKpis, setBlinkingKpis] = useState<Set<number>>(new Set())

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('/api/dashboard/position-sizing')
        if (!res.ok) throw new Error('Failed to fetch position metrics')
        const data = await res.json()
        setMetrics(data)
        // Trigger blink on first load
        setBlinkingKpis(new Set([0, 1, 2, 3]))
        setTimeout(() => setBlinkingKpis(new Set()), 600)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchMetrics()
  }, [])

  if (loading) return <div className="text-gray-400">Loading position management...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (!metrics) return null

  // KPI Cards
  const kpis = [
    { label: 'Avg Position Size', value: `$${metrics.avg_position_size.toFixed(2)}`, range: `$${metrics.min_position_size.toFixed(0)} - $${metrics.max_position_size.toFixed(0)}` },
    { label: 'Median Position Size', value: `$${metrics.median_position_size.toFixed(2)}`, range: `${((metrics.median_position_size / metrics.avg_position_size) * 100).toFixed(0)}% of avg` },
    { label: 'Avg Risk Amount', value: `$${metrics.avg_risk_amount.toFixed(2)}`, range: `${metrics.avg_risk_percentage.toFixed(2)}% per trade` },
    { label: 'Position-P&L Correlation', value: metrics.correlation.position_size_vs_pnl.toFixed(2), range: metrics.correlation.position_size_vs_pnl > 0.5 ? 'Strong' : 'Weak' },
  ]

  // Risk distribution over time (mock data)
  const riskTrendData = [
    { time: '00:00', risk: 2.1 },
    { time: '04:00', risk: 2.3 },
    { time: '08:00', risk: 2.5 },
    { time: '12:00', risk: 2.2 },
    { time: '16:00', risk: 2.4 },
    { time: '20:00', risk: 2.6 },
    { time: '24:00', risk: metrics.avg_risk_percentage },
  ]

  // Scatter data for position size vs P&L
  const scatterData = metrics.by_strategy.map((s) => ({
    strategy: s.strategy,
    positionSize: s.avg_position_size,
    riskAmount: s.avg_risk_amount,
    trades: s.trade_count,
  }))

  // Quartile data (mock)
  const quartileData = [
    { quartile: 'Q1 (0-25%)', min: metrics.min_position_size, max: metrics.min_position_size + (metrics.max_position_size - metrics.min_position_size) * 0.25, avg: metrics.min_position_size + (metrics.max_position_size - metrics.min_position_size) * 0.125 },
    { quartile: 'Q2 (25-50%)', min: metrics.min_position_size + (metrics.max_position_size - metrics.min_position_size) * 0.25, max: metrics.median_position_size, avg: (metrics.min_position_size + metrics.median_position_size) / 2 },
    { quartile: 'Q3 (50-75%)', min: metrics.median_position_size, max: metrics.min_position_size + (metrics.max_position_size - metrics.min_position_size) * 0.75, avg: (metrics.median_position_size + metrics.max_position_size) / 2 },
    { quartile: 'Q4 (75-100%)', min: metrics.min_position_size + (metrics.max_position_size - metrics.min_position_size) * 0.75, max: metrics.max_position_size, avg: metrics.max_position_size - (metrics.max_position_size - metrics.min_position_size) * 0.125 },
  ]

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, idx) => {
          const isBlinking = blinkingKpis.has(idx)
          return (
            <div key={idx} className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${isBlinking ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">{kpi.label}</p>
              <p className={`text-2xl font-bold text-blue-400 mt-1 ${isBlinking ? 'text-blink' : ''}`}>{kpi.value}</p>
              <p className="text-xs text-gray-500 mt-1">{kpi.range}</p>
            </div>
          )
        })}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Position Size Distribution */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Position Size Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={metrics.distribution}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="bucket" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="count" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Risk % Over Time */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Risk % Distribution Over Time</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={riskTrendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="risk" stroke="#f59e0b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Position Size vs Risk by Strategy */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Position Size vs Risk by Strategy</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="positionSize" name="Position Size" stroke="#94a3b8" type="number" />
              <YAxis dataKey="riskAmount" name="Risk Amount" stroke="#94a3b8" type="number" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter name="Strategies" data={scatterData} fill="#10b981">
                {scatterData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* Position Size Quartiles */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Position Size Quartiles</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={quartileData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="quartile" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="avg" fill="#8b5cf6" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Strategy Breakdown Table */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 overflow-x-auto">
        <h3 className="text-sm font-semibold text-white mb-4">Position Sizing by Strategy</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-gray-400">Strategy</th>
              <th className="text-right py-2 px-3 text-gray-400">Avg Position Size</th>
              <th className="text-right py-2 px-3 text-gray-400">Avg Risk Amount</th>
              <th className="text-right py-2 px-3 text-gray-400">Trade Count</th>
            </tr>
          </thead>
          <tbody>
            {metrics.by_strategy.map((s, idx) => (
              <tr key={idx} className="border-b border-slate-700 hover:bg-slate-700/50">
                <td className="py-3 px-3 text-white font-medium">{s.strategy}</td>
                <td className="py-3 px-3 text-right text-gray-300">${s.avg_position_size.toFixed(2)}</td>
                <td className="py-3 px-3 text-right text-gray-300">${s.avg_risk_amount.toFixed(2)}</td>
                <td className="py-3 px-3 text-right text-gray-300">{s.trade_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}


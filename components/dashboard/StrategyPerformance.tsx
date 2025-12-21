'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, LineChart, Line, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts'
import { useBlink } from '@/hooks/useBlink'

interface StrategyMetrics {
  strategy_name: string
  timeframe: string
  trade_count: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
  avg_confidence: number
  sharpe_ratio: number
  sortino_ratio: number
  expectancy: number
  profit_factor: number
  max_drawdown: number
  recovery_factor: number
  coefficient_of_variation: number
  win_loss_ratio: number
}

export default function StrategyPerformance() {
  const [strategies, setStrategies] = useState<StrategyMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchStrategies = async () => {
      try {
        const res = await fetch('/api/dashboard/strategy-performance')
        if (!res.ok) throw new Error('Failed to fetch strategy performance')
        const data = await res.json()
        setStrategies(data.strategies || [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchStrategies()
  }, [])

  if (loading) return <div className="text-gray-400">Loading strategy performance...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>

  if (strategies.length === 0) {
    return <div className="text-gray-400">No strategy data available</div>
  }

  // Prepare data for charts
  const winRateData = strategies.map(s => ({
    name: `${s.strategy_name} ${s.timeframe}`,
    value: s.win_rate,
  }))

  const sharpeData = strategies.map(s => ({
    name: `${s.strategy_name} ${s.timeframe}`,
    value: s.sharpe_ratio,
  }))

  const radarData = strategies.slice(0, 3).map(s => ({
    metric: `${s.strategy_name} ${s.timeframe}`,
    winRate: Math.min(s.win_rate, 100),
    sharpe: Math.min(Math.max(s.sharpe_ratio * 10, 0), 100),
    expectancy: Math.min(Math.max(s.expectancy * 10, 0), 100),
    profitFactor: Math.min(s.profit_factor * 20, 100),
    consistency: Math.min((1 - s.coefficient_of_variation) * 100, 100),
  }))

  const cumulativePnlData = strategies.map((s) => ({
    name: `${s.strategy_name} ${s.timeframe}`,
    pnl: s.total_pnl,
    trades: s.trade_count,
  }))

  return (
    <div className="space-y-6">
      {/* Ranking Table */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 overflow-x-auto">
        <h3 className="text-sm font-semibold text-white mb-4">Strategy Rankings (by Sharpe Ratio)</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-gray-400">Strategy</th>
              <th className="text-right py-2 px-3 text-gray-400">Trades</th>
              <th className="text-right py-2 px-3 text-gray-400">Win Rate</th>
              <th className="text-right py-2 px-3 text-gray-400">Total P&L</th>
              <th className="text-right py-2 px-3 text-gray-400">Sharpe</th>
              <th className="text-right py-2 px-3 text-gray-400">Expectancy</th>
            </tr>
          </thead>
          <tbody>
            {strategies.map((s, idx) => {
              const blinkRow = useBlink(s.total_pnl)
              return (
                <tr key={idx} className={`border-b border-slate-700 hover:bg-slate-700/50 ${blinkRow ? 'blink' : ''}`}>
                  <td className="py-3 px-3 text-white font-medium">{s.strategy_name} {s.timeframe}</td>
                  <td className="py-3 px-3 text-right text-gray-300">{s.trade_count}</td>
                  <td className={`py-3 px-3 text-right font-medium ${s.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {s.win_rate.toFixed(1)}%
                  </td>
                  <td className={`py-3 px-3 text-right font-medium ${s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'} ${blinkRow ? 'text-blink' : ''}`}>
                    ${s.total_pnl.toFixed(2)}
                  </td>
                  <td className="py-3 px-3 text-right text-gray-300">{s.sharpe_ratio.toFixed(2)}</td>
                  <td className="py-3 px-3 text-right text-gray-300">${s.expectancy.toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Win Rate Chart */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Win Rate by Strategy</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={winRateData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" stroke="#94a3b8" />
              <YAxis dataKey="name" type="category" stroke="#94a3b8" width={150} tick={{ fontSize: 12 }} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="value" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Sharpe Ratio Chart */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Sharpe Ratio by Strategy</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={sharpeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="value" fill="#10b981">
                {sharpeData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.value >= 1 ? '#10b981' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Cumulative P&L */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Cumulative P&L</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={cumulativePnlData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="pnl" stroke="#3b82f6" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Multi-Metric Radar */}
        {radarData.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <h3 className="text-sm font-semibold text-white mb-4">Multi-Metric Comparison (Top 3)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="metric" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} stroke="#94a3b8" />
                <Radar name="Win Rate" dataKey="winRate" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                <Radar name="Sharpe" dataKey="sharpe" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}


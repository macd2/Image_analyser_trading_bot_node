'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts'

interface CorrelationMetrics {
  confidence_vs_winrate: number
  position_size_vs_pnl: number
  strategy_consistency: Array<{
    strategy: string
    coefficient_of_variation: number
    win_loss_ratio: number
    consecutive_wins: number
    consecutive_losses: number
  }>
  pnl_distribution: Array<{
    strategy: string
    avg_pnl: number
    std_dev: number
    min_pnl: number
    max_pnl: number
  }>
  confidence_levels: Array<{
    level: string
    win_rate: number
    trade_count: number
    avg_pnl: number
  }>
}

export default function CorrelationAnalysis() {
  const [metrics, setMetrics] = useState<CorrelationMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [blinkingMetrics, setBlinkingMetrics] = useState<Set<string>>(new Set())

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch('/api/dashboard/correlation-analysis')
        if (!res.ok) throw new Error('Failed to fetch correlation metrics')
        const data = await res.json()
        setMetrics(data)
        // Trigger blink on first load
        setBlinkingMetrics(new Set(['confidence', 'position']))
        setTimeout(() => setBlinkingMetrics(new Set()), 600)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchMetrics()
  }, [])

  if (loading) return <div className="text-gray-400">Loading correlation analysis...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (!metrics) return null

  // Correlation cards
  const correlations = [
    {
      label: 'Confidence vs Win Rate',
      value: metrics.confidence_vs_winrate.toFixed(2),
      strength: Math.abs(metrics.confidence_vs_winrate) > 0.7 ? 'Strong' : Math.abs(metrics.confidence_vs_winrate) > 0.4 ? 'Moderate' : 'Weak',
      key: 'confidence',
    },
    {
      label: 'Position Size vs P&L',
      value: metrics.position_size_vs_pnl.toFixed(2),
      strength: Math.abs(metrics.position_size_vs_pnl) > 0.7 ? 'Strong' : Math.abs(metrics.position_size_vs_pnl) > 0.4 ? 'Moderate' : 'Weak',
      key: 'position',
    },
  ]

  // Radar data for consistency
  const radarData = metrics.strategy_consistency.slice(0, 3).map(s => ({
    strategy: s.strategy,
    cv: Math.min((1 - s.coefficient_of_variation) * 100, 100),
    wlRatio: Math.min(s.win_loss_ratio * 20, 100),
  }))

  return (
    <div className="space-y-6">
      {/* Correlation Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {correlations.map((corr) => {
          const isBlinking = blinkingMetrics.has(corr.key)
          return (
            <div key={corr.key} className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${isBlinking ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">{corr.label}</p>
              <p className={`text-3xl font-bold mt-2 ${Math.abs(parseFloat(corr.value)) > 0.5 ? 'text-green-400' : 'text-yellow-400'} ${isBlinking ? 'text-blink' : ''}`}>
                {corr.value}
              </p>
              <p className="text-xs text-gray-500 mt-1">{corr.strength} correlation</p>
            </div>
          )
        })}
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Confidence Levels Performance */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Win Rate by Confidence Level</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={metrics.confidence_levels}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="level" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="win_rate" fill="#3b82f6">
                {metrics.confidence_levels.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.win_rate >= 50 ? '#10b981' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* P&L Distribution by Strategy */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">P&L Distribution by Strategy</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={metrics.pnl_distribution}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="strategy" stroke="#94a3b8" angle={-45} textAnchor="end" height={80} tick={{ fontSize: 12 }} />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="avg_pnl" fill="#10b981">
                {metrics.pnl_distribution.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.avg_pnl >= 0 ? '#10b981' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Strategy Consistency Radar */}
        {radarData.length > 0 && (
          <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <h3 className="text-sm font-semibold text-white mb-4">Strategy Consistency (Top 3)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <RadarChart data={radarData}>
                <PolarGrid stroke="#334155" />
                <PolarAngleAxis dataKey="strategy" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} stroke="#94a3b8" />
                <Radar name="Consistency" dataKey="cv" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.25} />
                <Radar name="Win/Loss Ratio" dataKey="wlRatio" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
                <Legend />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Confidence Levels Table */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Confidence Level Breakdown</h3>
          <div className="space-y-2">
            {metrics.confidence_levels.map((level, idx) => (
              <div key={idx} className="flex items-center justify-between p-3 bg-slate-700 rounded">
                <div>
                  <p className="text-sm font-medium text-white">{level.level}</p>
                  <p className="text-xs text-gray-500">{level.trade_count} trades</p>
                </div>
                <div className="text-right">
                  <p className={`text-sm font-bold ${level.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {level.win_rate.toFixed(1)}%
                  </p>
                  <p className="text-xs text-gray-400">${level.avg_pnl.toFixed(2)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Strategy Consistency Table */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 overflow-x-auto">
        <h3 className="text-sm font-semibold text-white mb-4">Strategy Consistency Metrics</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-gray-400">Strategy</th>
              <th className="text-right py-2 px-3 text-gray-400">Coefficient of Variation</th>
              <th className="text-right py-2 px-3 text-gray-400">Win/Loss Ratio</th>
            </tr>
          </thead>
          <tbody>
            {metrics.strategy_consistency.map((s, idx) => (
              <tr key={idx} className="border-b border-slate-700 hover:bg-slate-700/50">
                <td className="py-3 px-3 text-white font-medium">{s.strategy}</td>
                <td className="py-3 px-3 text-right text-gray-300">{s.coefficient_of_variation.toFixed(2)}</td>
                <td className="py-3 px-3 text-right text-gray-300">{s.win_loss_ratio.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}


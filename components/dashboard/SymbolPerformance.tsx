'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, ScatterChart, Scatter, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useBlink } from '@/hooks/useBlink'

interface SymbolMetrics {
  symbol: string
  trade_count: number
  win_rate: number
  total_pnl: number
  avg_pnl: number
  avg_confidence: number
  best_trade: number
  worst_trade: number
  winning_trades: number
  losing_trades: number
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']

export default function SymbolPerformance() {
  const [symbols, setSymbols] = useState<SymbolMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchSymbols = async () => {
      try {
        const res = await fetch('/api/dashboard/symbol-performance')
        if (!res.ok) throw new Error('Failed to fetch symbol performance')
        const data = await res.json()
        setSymbols(data.symbols || [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchSymbols()
  }, [])

  if (loading) return <div className="text-gray-400">Loading symbol performance...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>

  if (symbols.length === 0) {
    return <div className="text-gray-400">No symbol data available</div>
  }

  // Prepare data for charts
  const winRateData = symbols.map(s => ({
    name: s.symbol,
    value: s.win_rate,
  }))

  const scatterData = symbols.map(s => ({
    symbol: s.symbol,
    confidence: s.avg_confidence,
    winRate: s.win_rate,
    trades: s.trade_count,
  }))

  const pnlData = symbols.map((s) => ({
    name: s.symbol,
    value: Math.max(s.total_pnl, 0.01), // Ensure positive for pie chart
    pnl: s.total_pnl,
  }))

  return (
    <div className="space-y-6">
      {/* Summary Table */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 overflow-x-auto">
        <h3 className="text-sm font-semibold text-white mb-4">Symbol Performance Summary</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-2 px-3 text-gray-400">Symbol</th>
              <th className="text-right py-2 px-3 text-gray-400">Trades</th>
              <th className="text-right py-2 px-3 text-gray-400">Win Rate</th>
              <th className="text-right py-2 px-3 text-gray-400">Total P&L</th>
              <th className="text-right py-2 px-3 text-gray-400">Avg P&L</th>
              <th className="text-right py-2 px-3 text-gray-400">Best Trade</th>
              <th className="text-right py-2 px-3 text-gray-400">Worst Trade</th>
              <th className="text-right py-2 px-3 text-gray-400">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((s, idx) => {
              const blinkRow = useBlink(s.total_pnl)
              return (
                <tr key={idx} className={`border-b border-slate-700 hover:bg-slate-700/50 ${blinkRow ? 'blink' : ''}`}>
                  <td className="py-3 px-3 text-white font-medium">{s.symbol}</td>
                  <td className="py-3 px-3 text-right text-gray-300">{s.trade_count}</td>
                  <td className={`py-3 px-3 text-right font-medium ${s.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {s.win_rate.toFixed(1)}%
                  </td>
                  <td className={`py-3 px-3 text-right font-medium ${s.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'} ${blinkRow ? 'text-blink' : ''}`}>
                    ${s.total_pnl.toFixed(2)}
                  </td>
                  <td className={`py-3 px-3 text-right ${s.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${s.avg_pnl.toFixed(2)}
                  </td>
                  <td className="py-3 px-3 text-right text-green-400">${s.best_trade.toFixed(2)}</td>
                  <td className="py-3 px-3 text-right text-red-400">${s.worst_trade.toFixed(2)}</td>
                  <td className="py-3 px-3 text-right text-gray-300">{s.avg_confidence.toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Win Rate by Symbol */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Win Rate by Symbol</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={winRateData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" stroke="#94a3b8" />
              <YAxis dataKey="name" type="category" stroke="#94a3b8" width={100} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Bar dataKey="value" fill="#3b82f6">
                {winRateData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.value >= 50 ? '#10b981' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Confidence vs Win Rate Scatter */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Confidence vs Win Rate</h3>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="confidence" name="Confidence" stroke="#94a3b8" type="number" domain={[0, 1]} />
              <YAxis dataKey="winRate" name="Win Rate %" stroke="#94a3b8" type="number" domain={[0, 100]} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} cursor={{ strokeDasharray: '3 3' }} />
              <Scatter name="Symbols" data={scatterData} fill="#3b82f6">
                {scatterData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* P&L Distribution Pie */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 lg:col-span-2">
          <h3 className="text-sm font-semibold text-white mb-4">P&L Distribution by Symbol</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pnlData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                label={({ name, pnl }) => `${name}: $${pnl.toFixed(0)}`}
              >
                {pnlData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} formatter={(value) => `$${typeof value === 'number' ? value.toFixed(2) : value}`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}


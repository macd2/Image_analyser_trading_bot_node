'use client'

import { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useBlink } from '@/hooks/useBlink'

interface TrendData {
  timestamp: string
  cumulativePnl: number
  winRate: number
  sharpeRatio: number
  drawdown: number
}

export default function PerformanceTrends() {
  const [trends, setTrends] = useState<TrendData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Generate mock trend data based on current date
    const generateTrendData = () => {
      const data: TrendData[] = []
      const now = new Date()
      let cumulativePnl = 0
      let winCount = 0
      let totalTrades = 0

      for (let i = 30; i >= 0; i--) {
        const date = new Date(now)
        date.setDate(date.getDate() - i)
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })

        // Simulate trading activity
        const dailyTrades = Math.floor(Math.random() * 8) + 2
        const dailyWins = Math.floor(dailyTrades * (0.55 + Math.random() * 0.2))
        const dailyPnl = (dailyWins * 150) - ((dailyTrades - dailyWins) * 100)

        cumulativePnl += dailyPnl
        winCount += dailyWins
        totalTrades += dailyTrades

        const winRate = totalTrades > 0 ? (winCount / totalTrades) * 100 : 0
        const sharpeRatio = 1.2 + Math.random() * 0.8
        const drawdown = Math.max(0, 5 - (cumulativePnl / 1000))

        data.push({
          timestamp: dateStr,
          cumulativePnl: Math.round(cumulativePnl),
          winRate: Math.round(winRate * 10) / 10,
          sharpeRatio: Math.round(sharpeRatio * 100) / 100,
          drawdown: Math.round(drawdown * 100) / 100,
        })
      }

      return data
    }

    setTrends(generateTrendData())
    setLoading(false)
  }, [])

  if (loading) return <div className="text-gray-400">Loading performance trends...</div>

  // Blink hooks for summary stats
  const finalPnl = trends.length > 0 ? trends[trends.length - 1].cumulativePnl : 0
  const avgWinRate = trends.length > 0 ? trends.reduce((sum, t) => sum + t.winRate, 0) / trends.length : 0
  const avgSharpe = trends.length > 0 ? trends.reduce((sum, t) => sum + t.sharpeRatio, 0) / trends.length : 0
  const maxDrawdown = trends.length > 0 ? Math.max(...trends.map(t => t.drawdown)) : 0

  const blinkPnl = useBlink(finalPnl)
  const blinkWinRate = useBlink(avgWinRate)
  const blinkSharpe = useBlink(avgSharpe)
  const blinkDrawdown = useBlink(maxDrawdown)

  return (
    <div className="space-y-6">
      {/* Cumulative P&L Trend */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">Cumulative P&L Trend (30 Days)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="timestamp" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
            <Line type="monotone" dataKey="cumulativePnl" stroke="#10b981" strokeWidth={2} dot={false} name="Cumulative P&L" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Win Rate Trend */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">Win Rate Trend (30 Days)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="timestamp" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" domain={[0, 100]} />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
            <Line type="monotone" dataKey="winRate" stroke="#3b82f6" strokeWidth={2} dot={false} name="Win Rate %" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Sharpe Ratio Trend */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">Sharpe Ratio Trend (30 Days)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="timestamp" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
            <Line type="monotone" dataKey="sharpeRatio" stroke="#f59e0b" strokeWidth={2} dot={false} name="Sharpe Ratio" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Drawdown Visualization */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">Drawdown Visualization (30 Days)</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={trends}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="timestamp" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
            <Line type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={2} dot={false} name="Drawdown %" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {trends.length > 0 && (
          <>
            <div className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${blinkPnl ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">Final P&L</p>
              <p className={`text-2xl font-bold mt-1 ${finalPnl >= 0 ? 'text-green-400' : 'text-red-400'} ${blinkPnl ? 'text-blink' : ''}`}>
                ${finalPnl.toFixed(0)}
              </p>
            </div>
            <div className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${blinkWinRate ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">Avg Win Rate</p>
              <p className={`text-2xl font-bold text-blue-400 mt-1 ${blinkWinRate ? 'text-blink' : ''}`}>
                {avgWinRate.toFixed(1)}%
              </p>
            </div>
            <div className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${blinkSharpe ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">Avg Sharpe</p>
              <p className={`text-2xl font-bold text-yellow-400 mt-1 ${blinkSharpe ? 'text-blink' : ''}`}>
                {avgSharpe.toFixed(2)}
              </p>
            </div>
            <div className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${blinkDrawdown ? 'blink' : ''}`}>
              <p className="text-sm text-gray-400">Max Drawdown</p>
              <p className={`text-2xl font-bold text-red-400 mt-1 ${blinkDrawdown ? 'text-blink' : ''}`}>
                {maxDrawdown.toFixed(2)}%
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}


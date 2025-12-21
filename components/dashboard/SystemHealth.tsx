'use client'

import { useEffect, useState } from 'react'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { AlertCircle, CheckCircle, TrendingUp, DollarSign } from 'lucide-react'
import { useBlink } from '@/hooks/useBlink'

interface DashboardOverview {
  system_health: {
    active_instances: number
    total_instances: number
    instance_status: Array<{ id: string; name: string; status: string; is_active: boolean }>
  }
  performance: {
    total_pnl: number
    win_rate: number
    total_trades: number
    winning_trades: number
    losing_trades: number
    avg_confidence: number
  }
  positions: {
    open_count: number
    closed_today_count: number
    unrealized_pnl: number
  }
  timestamp: string
}

export default function SystemHealth() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Blink hooks for each metric
  const blinkPnl = useBlink(overview?.performance.total_pnl)
  const blinkWinRate = useBlink(overview?.performance.win_rate)
  const blinkInstances = useBlink(overview?.system_health.active_instances)
  const blinkPositions = useBlink(overview?.positions.open_count)

  useEffect(() => {
    const fetchOverview = async () => {
      try {
        const res = await fetch('/api/dashboard/overview')
        if (!res.ok) throw new Error('Failed to fetch overview')
        const data = await res.json()
        setOverview(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchOverview()
    const interval = setInterval(fetchOverview, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  if (loading) return <div className="text-gray-400">Loading system health...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (!overview) return null

  const { system_health, performance, positions } = overview

  // KPI Cards
  const kpis = [
    {
      label: 'Active Instances',
      value: system_health.active_instances,
      total: system_health.total_instances,
      icon: CheckCircle,
      color: 'text-green-400',
    },
    {
      label: 'Total P&L',
      value: `$${performance.total_pnl.toFixed(2)}`,
      change: performance.total_pnl >= 0 ? '+' : '',
      icon: DollarSign,
      color: performance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400',
    },
    {
      label: 'Win Rate',
      value: `${performance.win_rate.toFixed(1)}%`,
      total: `${performance.winning_trades}/${performance.total_trades}`,
      icon: TrendingUp,
      color: performance.win_rate >= 50 ? 'text-green-400' : 'text-red-400',
    },
    {
      label: 'Open Positions',
      value: positions.open_count,
      unrealized: `${positions.unrealized_pnl >= 0 ? '+' : ''}$${positions.unrealized_pnl.toFixed(2)}`,
      icon: AlertCircle,
      color: 'text-blue-400',
    },
  ]

  // Trade volume data (mock for now - would come from historical data)
  const tradeVolumeData = [
    { day: 'Mon', wins: 5, losses: 2 },
    { day: 'Tue', wins: 8, losses: 3 },
    { day: 'Wed', wins: 6, losses: 4 },
    { day: 'Thu', wins: 9, losses: 2 },
    { day: 'Fri', wins: 7, losses: 3 },
  ]

  // P&L trend data (mock for now)
  const pnlTrendData = [
    { time: '00:00', pnl: 0 },
    { time: '04:00', pnl: 245 },
    { time: '08:00', pnl: 520 },
    { time: '12:00', pnl: 890 },
    { time: '16:00', pnl: 1250 },
    { time: '20:00', pnl: 1680 },
    { time: '24:00', pnl: performance.total_pnl },
  ]

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {kpis.map((kpi, idx) => {
          const Icon = kpi.icon
          const blinkClass = [blinkInstances, blinkPnl, blinkWinRate, blinkPositions][idx] ? 'blink' : ''
          return (
            <div key={idx} className={`bg-slate-800 rounded-lg p-4 border border-slate-700 ${blinkClass}`}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm text-gray-400">{kpi.label}</p>
                  <p className={`text-2xl font-bold mt-1 ${kpi.color} ${blinkClass ? 'text-blink' : ''}`}>{kpi.value}</p>
                  {kpi.total && <p className="text-xs text-gray-500 mt-1">{kpi.total}</p>}
                  {kpi.unrealized && <p className="text-xs text-gray-500 mt-1">{kpi.unrealized}</p>}
                </div>
                <Icon className={`w-5 h-5 ${kpi.color}`} />
              </div>
            </div>
          )
        })}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* P&L Trend */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">P&L Trend (Today)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={pnlTrendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Line type="monotone" dataKey="pnl" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Trade Volume */}
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <h3 className="text-sm font-semibold text-white mb-4">Trade Volume (Weekly)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={tradeVolumeData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="day" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }} />
              <Legend />
              <Bar dataKey="wins" stackId="a" fill="#10b981" />
              <Bar dataKey="losses" stackId="a" fill="#ef4444" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Instance Status */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <h3 className="text-sm font-semibold text-white mb-4">Instance Status</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {system_health.instance_status.map((instance) => (
            <div key={instance.id} className="bg-slate-700 rounded p-3 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-white">{instance.name}</p>
                <p className={`text-xs ${instance.is_active ? 'text-green-400' : 'text-gray-500'}`}>
                  {instance.is_active ? '● Active' : '○ Inactive'}
                </p>
              </div>
              {instance.is_active && <CheckCircle className="w-4 h-4 text-green-400" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}


'use client'

import { useState, useEffect } from 'react'
import { Camera, Lightbulb, Zap, TrendingUp, DollarSign, ChevronDown } from 'lucide-react'

export type StatsScope = 'cycle' | 'run' | 'instance' | 'global'

interface Stats {
  images_analyzed: number
  valid_signals: number
  avg_confidence: number
  actionable_percent: number
  total_trades: number
  win_count: number
  loss_count: number
  total_pnl: number
  instance_count?: number
}

interface StatsBarProps {
  scope: StatsScope
  scopeId?: string | null
  onScopeChange?: (scope: StatsScope) => void
  showScopeSelector?: boolean
}

const scopeLabels: Record<StatsScope, string> = {
  cycle: 'This Cycle',
  run: 'This Run',
  instance: 'This Instance',
  global: 'All Time',
}

export default function StatsBar({
  scope,
  scopeId,
  onScopeChange,
  showScopeSelector = true,
}: StatsBarProps) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [scopeOpen, setScopeOpen] = useState(false)

  useEffect(() => {
    fetchStats()
  }, [scope, scopeId])

  const fetchStats = async () => {
    try {
      setLoading(true)

      // If scope requires an ID but none provided, fall back to global
      const effectiveScope = (scope !== 'global' && !scopeId) ? 'global' : scope

      const params = new URLSearchParams({ scope: effectiveScope })
      if (scopeId && effectiveScope !== 'global') params.set('id', scopeId)

      const res = await fetch(`/api/bot/stats?${params}`)
      if (res.ok) {
        const data = await res.json()
        setStats(data.stats)
      }
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    } finally {
      setLoading(false)
    }
  }

  const winRate = stats && stats.total_trades > 0
    ? ((stats.win_count / stats.total_trades) * 100).toFixed(0)
    : '0'

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-slate-400">Performance Stats</h3>
        {showScopeSelector && onScopeChange && (
          <div className="relative">
            <button
              onClick={() => setScopeOpen(!scopeOpen)}
              className="flex items-center gap-1.5 text-xs bg-slate-700 hover:bg-slate-600 px-2.5 py-1.5 rounded transition"
            >
              <span>{scopeLabels[scope]}</span>
              <ChevronDown className={`w-3 h-3 transition ${scopeOpen ? 'rotate-180' : ''}`} />
            </button>
            {scopeOpen && (
              <div className="absolute right-0 top-full mt-1 bg-slate-700 border border-slate-600 rounded shadow-lg z-10">
                {(Object.keys(scopeLabels) as StatsScope[]).map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      onScopeChange(s)
                      setScopeOpen(false)
                    }}
                    className={`block w-full text-left px-3 py-1.5 text-xs hover:bg-slate-600 transition ${
                      scope === s ? 'text-sky-400' : 'text-slate-300'
                    }`}
                  >
                    {scopeLabels[s]}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="h-8 bg-slate-700 rounded mb-1"></div>
              <div className="h-3 bg-slate-700 rounded w-16"></div>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <StatItem icon={Camera} label="Analyzed" value={stats?.images_analyzed || 0} />
          <StatItem icon={Lightbulb} label="Signals" value={stats?.valid_signals || 0} />
          <StatItem
            icon={Zap}
            label="Avg Conf"
            value={(stats?.avg_confidence || 0).toFixed(2)}
          />
          <StatItem
            icon={TrendingUp}
            label="Actionable"
            value={`${(stats?.actionable_percent || 0).toFixed(1)}%`}
          />
          <StatItem
            icon={TrendingUp}
            label="Win Rate"
            value={`${winRate}%`}
            subValue={`${stats?.win_count || 0}W / ${stats?.loss_count || 0}L`}
          />
          <StatItem
            icon={DollarSign}
            label="P&L"
            value={`$${(stats?.total_pnl || 0).toFixed(2)}`}
            valueColor={stats && stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}
          />
        </div>
      )}
    </div>
  )
}

function StatItem({
  icon: Icon,
  label,
  value,
  subValue,
  valueColor = 'text-white',
}: {
  icon: React.ElementType
  label: string
  value: string | number
  subValue?: string
  valueColor?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-4 h-4 text-slate-500" />
      <div>
        <div className={`text-lg font-semibold ${valueColor}`}>{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
        {subValue && <div className="text-xs text-slate-600">{subValue}</div>}
      </div>
    </div>
  )
}


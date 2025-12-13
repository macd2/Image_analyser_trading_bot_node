'use client'

import { useState, useEffect } from 'react'
import { Camera, Lightbulb, Zap, TrendingUp, DollarSign, ChevronDown, ChevronUp, Clock, Cpu, Loader2, Gauge, BarChart3 } from 'lucide-react'

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

interface InstanceStats {
  running_duration_hours: number
  cycle_count: number
  charts_captured: number
  analyses_completed: number
  recommendations_generated: number
  trades_executed: number
  slots_used: number
  slots_available: number
  start_time: string
}

interface AggregateStats {
  total_pnl: number
  win_rate: number
  total_trades: number
  running_since: string
}

interface StatsBarProps {
  scope: StatsScope
  scopeId?: string | null
  instanceId?: string | null
  onScopeChange?: (scope: StatsScope) => void
  showScopeSelector?: boolean
}

const scopeLabels: Record<StatsScope, string> = {
  cycle: 'Latest Cycle',
  run: 'Latest Run',
  instance: 'All Time',
  global: 'All Time',
}

export default function StatsBar({
  scope,
  scopeId,
  instanceId,
  onScopeChange,
  showScopeSelector = true,
}: StatsBarProps) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [instanceStats, setInstanceStats] = useState<InstanceStats | null>(null)
  const [aggregateStats, setAggregateStats] = useState<AggregateStats | null>(null)
  const [scopeOpen, setScopeOpen] = useState(false)
  const [loadingSection2, setLoadingSection2] = useState(false)
  const [detailedBreakdownOpen, setDetailedBreakdownOpen] = useState(false)

  const fetchScopedStats = async () => {
    setLoadingSection2(true)
    try {
      let effectiveScope = scope
      let effectiveScopeId = scopeId

      // If scope is 'cycle' but no scopeId provided, fetch the latest cycle ID
      if (scope === 'cycle' && !scopeId && instanceId) {
        try {
          const cycleRes = await fetch(`/api/bot/latest-cycle?instance_id=${instanceId}`)
          if (cycleRes.ok) {
            const cycleData = await cycleRes.json()
            effectiveScopeId = cycleData.cycle_id
          } else {
            // Fallback to instance scope if no cycle found
            effectiveScope = 'instance'
            effectiveScopeId = instanceId
          }
        } catch (err) {
          console.error('Failed to fetch latest cycle:', err)
          effectiveScope = 'instance'
          effectiveScopeId = instanceId
        }
      }

      // If scope is 'run' but no scopeId provided, fetch the latest run ID
      if (scope === 'run' && !scopeId && instanceId) {
        try {
          const runRes = await fetch(`/api/bot/latest-run?instance_id=${instanceId}`)
          if (runRes.ok) {
            const runData = await runRes.json()
            effectiveScopeId = runData.run_id
          } else {
            // Fallback to instance scope if no run found
            effectiveScope = 'instance'
            effectiveScopeId = instanceId
          }
        } catch (err) {
          console.error('Failed to fetch latest run:', err)
          effectiveScope = 'instance'
          effectiveScopeId = instanceId
        }
      }

      // If no scope ID and not global, use instance scope
      if (!effectiveScopeId && effectiveScope !== 'global' && instanceId) {
        effectiveScope = 'instance'
        effectiveScopeId = instanceId
      }

      const params = new URLSearchParams({ scope: effectiveScope })
      if (effectiveScopeId && effectiveScope !== 'global') params.set('id', effectiveScopeId)

      const res = await fetch(`/api/bot/stats?${params}`)
      if (res.ok) {
        const data = await res.json()
        console.log('Stats response:', data)
        setStats(data.stats)
      } else {
        console.error('Stats fetch failed:', res.status)
      }

      if (instanceId) {
        // For cycle/run scopes, fetch cycle/run-specific stats
        // For instance/global scopes, fetch instance-wide stats
        let instanceStatsUrl = `/api/bot/bot-stats?instance_id=${instanceId}`

        if (effectiveScope === 'cycle' && effectiveScopeId) {
          instanceStatsUrl = `/api/bot/cycle-stats?cycle_id=${effectiveScopeId}`
        } else if (effectiveScope === 'run' && effectiveScopeId) {
          instanceStatsUrl = `/api/bot/run-stats?run_id=${effectiveScopeId}`
        }

        const instanceRes = await fetch(instanceStatsUrl)
        if (instanceRes.ok) {
          const instanceData = await instanceRes.json()
          console.log('Instance stats response:', instanceData)

          // Handle different response formats
          // bot-stats returns { runtime_stats, performance_metrics }
          // cycle-stats and run-stats return data directly
          let stats = instanceData
          if (instanceData.runtime_stats) {
            stats = { ...instanceData.runtime_stats, ...instanceData.performance_metrics }
          }

          setInstanceStats({
            running_duration_hours: Number(stats.running_duration_hours) || 0,
            cycle_count: Number(stats.cycle_count) || 0,
            charts_captured: Number(stats.charts_captured) || 0,
            analyses_completed: Number(stats.analyses_completed) || 0,
            recommendations_generated: Number(stats.recommendations_generated) || 0,
            trades_executed: Number(stats.trades_executed) || 0,
            slots_used: Number(stats.slots_used) || 0,
            slots_available: Number(stats.slots_available) || 5,
            start_time: stats.start_time || '',
          })
        } else {
          console.error('Instance stats fetch failed:', instanceRes.status)
        }
      }
    } catch (error) {
      console.error('Failed to fetch scoped stats:', error)
    } finally {
      setLoadingSection2(false)
    }
  }

  useEffect(() => {
    if (!instanceId) return
    const fetchAggregateStats = async () => {
      try {
        const aggregateRes = await fetch(`/api/bot/instance-aggregate?instance_id=${instanceId}`)
        if (aggregateRes.ok) {
          const aggregateData = await aggregateRes.json()
          setAggregateStats(aggregateData)
        }
      } catch (error) {
        console.error('Failed to fetch aggregate stats:', error)
      }
    }
    fetchAggregateStats()
  }, [instanceId])

  useEffect(() => {
    fetchScopedStats()
  }, [scope, scopeId, instanceId])

  const winRate = stats && stats.total_trades > 0
    ? ((stats.win_count / stats.total_trades) * 100).toFixed(0)
    : '0'

  const slotUsagePercentage = instanceStats
    ? (instanceStats.slots_used / instanceStats.slots_available) * 100
    : 0

  const formatDuration = (hours: number): string => {
    if (hours < 1) {
      const minutes = Math.round(hours * 60)
      return `${minutes}m`
    }
    if (hours < 24) {
      return `${hours.toFixed(1)}h`
    }
    const days = Math.floor(hours / 24)
    const remainingHours = Math.round(hours % 24)
    return `${days}d ${remainingHours}h`
  }

  const formatDaysAgo = (dateString: string): string => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays}d ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
    return `${Math.floor(diffDays / 30)}mo ago`
  }

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
      <div className="mb-4">
        <h3 className="text-sm font-medium text-slate-400">Performance Stats</h3>
      </div>
      <div className="space-y-6">
        {/* SECTION 1: INSTANCE LIFETIME */}
        {instanceId ? (
          <div>
            <div className="flex items-center gap-2 text-xs text-slate-400 mb-2 font-semibold">
              <Gauge className="w-3 h-3" />
              Instance Lifetime
            </div>
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-slate-700/30 rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <DollarSign className="w-3 h-3 text-amber-400" />
                  <span className="text-xs text-slate-400">P&L Total</span>
                </div>
                <div className={`font-medium text-sm ${aggregateStats && aggregateStats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {aggregateStats ? `$${aggregateStats.total_pnl.toFixed(2)}` : <span className="text-slate-500 text-xs italic">Waiting for data...</span>}
                </div>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <TrendingUp className="w-3 h-3 text-green-400" />
                  <span className="text-xs text-slate-400">Win Rate</span>
                </div>
                <div className="text-white font-medium text-sm">
                  {aggregateStats ? `${aggregateStats.win_rate}%` : <span className="text-slate-500 text-xs italic">Waiting for data...</span>}
                </div>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <TrendingUp className="w-3 h-3 text-cyan-400" />
                  <span className="text-xs text-slate-400">Trades</span>
                </div>
                <div className="text-white font-medium text-sm">
                  {aggregateStats ? aggregateStats.total_trades : <span className="text-slate-500 text-xs italic">Waiting for data...</span>}
                </div>
              </div>
              <div className="bg-slate-700/30 rounded p-2">
                <div className="flex items-center gap-2 mb-1">
                  <Clock className="w-3 h-3 text-blue-400" />
                  <span className="text-xs text-slate-400">Since</span>
                </div>
                <div className="text-white font-medium text-sm">
                  {aggregateStats ? formatDaysAgo(aggregateStats.running_since) : <span className="text-slate-500 text-xs italic">Waiting for data...</span>}
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {/* SECTION 2: DETAILED BREAKDOWN */}
        {instanceId ? (
          <div>
            <div className="flex items-center justify-between mb-2">
              <button
                onClick={() => setDetailedBreakdownOpen(!detailedBreakdownOpen)}
                className="flex items-center gap-2 text-xs text-slate-400 font-semibold hover:text-slate-300 transition"
              >
                <BarChart3 className="w-3 h-3" />
                Detailed Breakdown
                {detailedBreakdownOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showScopeSelector && onScopeChange && (
                <div className="relative">
                  <button
                    onClick={() => setScopeOpen(!scopeOpen)}
                    className="flex items-center gap-1 px-2 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 rounded border border-slate-600 text-slate-300 transition"
                  >
                    {scopeLabels[scope]}
                    <ChevronDown className="w-3 h-3" />
                  </button>
                  {scopeOpen && (
                    <div className="absolute right-0 mt-1 bg-slate-800 border border-slate-700 rounded shadow-lg z-10">
                      {(['run', 'cycle', 'instance', 'global'] as const).map((s) => (
                        <button
                          key={s}
                          onClick={() => {
                            onScopeChange(s)
                            setScopeOpen(false)
                          }}
                          className={`block w-full text-left px-3 py-2 text-xs ${
                            scope === s ? 'bg-slate-700 text-white' : 'text-slate-300 hover:bg-slate-700/50'
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

            {detailedBreakdownOpen && (
              <>
                {loadingSection2 ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
                  </div>
                ) : instanceStats && stats ? (
                  <div className="space-y-2">
                <div className="grid grid-cols-4 gap-3">
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <DollarSign className="w-3 h-3 text-amber-400" />
                      <span className="text-xs text-slate-400">P&L</span>
                    </div>
                    <div className={`font-medium text-sm ${stats.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${(stats.total_pnl || 0).toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingUp className="w-3 h-3 text-green-400" />
                      <span className="text-xs text-slate-400">Win Rate</span>
                    </div>
                    <div className="text-white font-medium text-sm">{winRate}%</div>
                    <div className="text-[10px] text-slate-500">{stats.win_count || 0}W / {stats.loss_count || 0}L</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="w-3 h-3 text-blue-400" />
                      <span className="text-xs text-slate-400">Running</span>
                    </div>
                    <div className="text-white font-medium text-sm">{formatDuration(instanceStats.running_duration_hours)}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Cpu className="w-3 h-3 text-purple-400" />
                      <span className="text-xs text-slate-400">Cycles</span>
                    </div>
                    <div className="text-white font-medium text-sm">{instanceStats.cycle_count}</div>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Camera className="w-3 h-3 text-blue-400" />
                      <span className="text-xs text-slate-400">Analyzed</span>
                    </div>
                    <div className="text-white font-medium text-sm">{stats.images_analyzed || 0}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Lightbulb className="w-3 h-3 text-yellow-400" />
                      <span className="text-xs text-slate-400">Signals</span>
                    </div>
                    <div className="text-white font-medium text-sm">{stats.valid_signals || 0}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Zap className="w-3 h-3 text-cyan-400" />
                      <span className="text-xs text-slate-400">Avg Conf</span>
                    </div>
                    <div className="text-white font-medium text-sm">{(stats.avg_confidence || 0).toFixed(2)}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-slate-400">Slots</span>
                    </div>
                    <div className="text-white font-medium text-sm mb-1">{instanceStats.slots_used}/{instanceStats.slots_available}</div>
                    <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-500 ${slotUsagePercentage > 80 ? 'bg-red-500' : slotUsagePercentage > 50 ? 'bg-amber-500' : 'bg-green-500'}`}
                        style={{ width: `${slotUsagePercentage}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Camera className="w-3 h-3 text-blue-400" />
                      <span className="text-xs text-slate-400">Charts</span>
                    </div>
                    <div className="text-white font-medium text-sm">{instanceStats.charts_captured}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <Zap className="w-3 h-3 text-purple-400" />
                      <span className="text-xs text-slate-400">Analyses</span>
                    </div>
                    <div className="text-white font-medium text-sm">{instanceStats.analyses_completed}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingUp className="w-3 h-3 text-green-400" />
                      <span className="text-xs text-slate-400">Executed</span>
                    </div>
                    <div className="text-white font-medium text-sm">{instanceStats.trades_executed}</div>
                  </div>
                  <div className="bg-slate-700/30 rounded p-2">
                    <div className="flex items-center gap-2 mb-1">
                      <TrendingUp className="w-3 h-3 text-cyan-400" />
                      <span className="text-xs text-slate-400">Actionable</span>
                    </div>
                    <div className="text-white font-medium text-sm">{(stats.actionable_percent || 0).toFixed(1)}%</div>
                  </div>
                </div>
                  </div>
                ) : null}
              </>
            )}
          </div>
        ) : null}
      </div>
    </div>
  )
}


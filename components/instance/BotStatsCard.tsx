'use client'

import { useState, useEffect } from 'react'
import { Activity, Clock, Cpu, User } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState } from '@/components/shared'

interface BotStatsCardProps {
  instanceId: string
}

interface BotStats {
  instance_info: {
    id: string
    name: string
    mode: 'paper' | 'live'
    timeframe: string
    prompt_name: string
    is_active: boolean
  }
  runtime_stats: {
    cycle_count: number
    running_duration_hours: number
    start_time: string
    current_run_id: string
    total_trades: number
    win_rate: number
    total_pnl: number
    avg_confidence: number
  }
  performance_metrics: {
    charts_captured: number
    analyses_completed: number
    recommendations_generated: number
    trades_executed: number
    slots_used: number
    slots_available: number
  }
}

export function BotStatsCard({ instanceId }: BotStatsCardProps) {
  const [stats, setStats] = useState<BotStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchStats()
    const interval = setInterval(fetchStats, 10000) // Refresh every 10 seconds
    return () => clearInterval(interval)
  }, [instanceId])

  const fetchStats = async () => {
    try {
      const res = await fetch(`/api/bot/bot-stats?instance_id=${instanceId}`)
      if (!res.ok) throw new Error('Failed to fetch bot stats')
      const data = await res.json()
      setStats(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingState text="Loading bot stats..." />
  if (error) return <div className="text-red-400 text-sm">Error: {error}</div>
  if (!stats) return <div className="text-slate-500 text-sm">No bot stats available</div>

  const { instance_info, runtime_stats, performance_metrics } = stats
  
  // Calculate slot usage percentage
  const slotUsagePercentage = performance_metrics.slots_available > 0 
    ? Math.round((performance_metrics.slots_used / performance_metrics.slots_available) * 100)
    : 0

  // Format running duration
  const formatDuration = (hours: number) => {
    if (hours < 1) return `${Math.round(hours * 60)}m`
    if (hours < 24) return `${hours.toFixed(1)}h`
    return `${(hours / 24).toFixed(1)}d`
  }

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Activity className="w-4 h-4 text-green-400" />
            Bot Statistics
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-1 rounded ${instance_info.mode === 'paper' ? 'bg-yellow-900/50 text-yellow-400' : 'bg-green-900/50 text-green-400'}`}>
              {instance_info.mode === 'paper' ? 'PAPER' : 'LIVE'}
            </span>
            <span className="text-xs text-slate-400">
              {instance_info.timeframe}
            </span>
          </div>
        </div>
        <div className="text-xs text-slate-400 flex items-center gap-2">
          <User className="w-3 h-3" />
          {instance_info.name}
          <span className="text-slate-500">•</span>
          <span className="text-slate-500">{instance_info.prompt_name}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {/* Row 1: Running Duration + Cycles + Position Slots + Started */}
        <div className="grid grid-cols-4 gap-3">
          <div className="bg-slate-700/30 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="w-3 h-3 text-blue-400" />
              <span className="text-xs text-slate-400">Running</span>
            </div>
            <div className="text-white font-medium text-sm">
              {formatDuration(runtime_stats.running_duration_hours)}
            </div>
          </div>
          <div className="bg-slate-700/30 rounded p-2">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="w-3 h-3 text-purple-400" />
              <span className="text-xs text-slate-400">Cycles</span>
            </div>
            <div className="text-white font-medium text-sm">
              {runtime_stats.cycle_count}
            </div>
          </div>
          <div className="bg-slate-700/30 rounded p-2">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-400">Position Slots</span>
            </div>
            <div className="text-white font-medium text-sm mb-1">
              {performance_metrics.slots_used}/{performance_metrics.slots_available}
            </div>
            <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${slotUsagePercentage > 80 ? 'bg-red-500' : slotUsagePercentage > 50 ? 'bg-amber-500' : 'bg-green-500'}`}
                style={{ width: `${slotUsagePercentage}%` }}
              />
            </div>
          </div>
          <div className="bg-slate-700/30 rounded p-2 text-center">
            <div className="text-[10px] text-slate-400 mb-1">Started</div>
            <div className="text-white font-medium text-sm">{new Date(runtime_stats.start_time).toLocaleDateString()}</div>
          </div>
        </div>

        {/* Row 2: Charts + Analyses + Signals + Trades Executed */}
        <div className="grid grid-cols-4 gap-3">
          <div className="bg-blue-900/20 rounded p-2 text-center">
            <div className="text-[10px] text-blue-400 mb-1">Charts</div>
            <div className="text-white font-medium text-sm">{performance_metrics.charts_captured}</div>
          </div>
          <div className="bg-purple-900/20 rounded p-2 text-center">
            <div className="text-[10px] text-purple-400 mb-1">Analyses</div>
            <div className="text-white font-medium text-sm">{performance_metrics.analyses_completed}</div>
          </div>
          <div className="bg-amber-900/20 rounded p-2 text-center">
            <div className="text-[10px] text-amber-400 mb-1">Signals</div>
            <div className="text-white font-medium text-sm">{performance_metrics.recommendations_generated}</div>
          </div>
          <div className="bg-green-900/20 rounded p-2 text-center">
            <div className="text-[10px] text-green-400 mb-1">Executed</div>
            <div className="text-white font-medium text-sm">{performance_metrics.trades_executed}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

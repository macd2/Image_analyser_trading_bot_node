'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { Plus, RefreshCw, Play, TrendingUp, TrendingDown, Target, DollarSign, Brain, Beaker, FileText, Flame } from 'lucide-react'
import { InstanceCardData } from '@/components/InstanceCard'
import StatsBar from '@/components/StatsBar'
import { useRealtime } from '@/hooks/useRealtime'
import { LoadingState, ErrorState } from '@/components/shared'

// Custom card component for instances page that links to /instances/[id]
function InstanceCardForNewDesign({ instance, onAction }: { instance: InstanceCardData; onAction: (id: string, action: 'start' | 'stop' | 'kill') => Promise<void> }) {
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const handleAction = async (action: 'start' | 'stop' | 'kill') => {
    if (!onAction) return
    setActionLoading(action)
    try {
      await onAction(instance.id, action)
    } finally {
      setActionLoading(null)
    }
  }

  const isRunning = instance.is_running

  // Calculate wins/losses for win rate breakdown
  const totalTrades = instance.total_trades
  const winRate = instance.win_rate / 100
  const wins = Math.round(totalTrades * winRate)
  const losses = totalTrades - wins

  // Calculate P&L percentage (assuming starting balance or using absolute value)
  const pnl = instance.total_pnl
  const pnlPercent = totalTrades > 0 ? (pnl / totalTrades) * 10 : 0 // Rough estimate

  // Calculate Expected Value (EV) = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
  const avgWin = wins > 0 ? (pnl > 0 ? pnl / wins : 0) : 0
  const avgLoss = losses > 0 ? (pnl < 0 ? Math.abs(pnl) / losses : 0) : 0
  const lossRate = totalTrades > 0 ? losses / totalTrades : 0
  const expectedValue = totalTrades > 0 ? (winRate * avgWin) - (lossRate * avgLoss) : 0

  return (
    <Link href={`/instances/${instance.id}`} className="block">
      <div className="bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-900/50 hover:-translate-y-0.5 transition-all duration-200 overflow-hidden">
        {/* Header */}
        <div className="p-5 border-b border-slate-700 hover:bg-slate-700/50 transition cursor-pointer">
          <div className="flex items-start justify-between mb-2">
            <h3 className="font-bold text-white text-xl">{instance.name}</h3>
            {isRunning ? (
              <span className="px-3 py-1 text-sm font-medium bg-green-600/20 text-green-400 rounded-full flex items-center gap-1.5">
                <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                Running
              </span>
            ) : (
              <span className="px-3 py-1 text-sm font-medium bg-slate-600/20 text-slate-400 rounded-full">
                Stopped
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 text-sm text-slate-400">
            <Brain className="w-4 h-4" />
            <span>{instance.prompt_name || 'No prompt set'}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Trades */}
            <div>
              <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-1.5">
                <TrendingUp className="w-3.5 h-3.5" />
                <span>Trades</span>
              </div>
              <div className="text-white text-2xl font-bold">{instance.total_trades}</div>
              {instance.live_trades > 0 && (
                <div className="text-slate-400 text-xs mt-1">{instance.live_trades} live</div>
              )}
            </div>

            {/* Win Rate */}
            <div>
              <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-1.5">
                <Target className="w-3.5 h-3.5" />
                <span>Win Rate</span>
              </div>
              <div className="text-white text-2xl font-bold">{instance.win_rate.toFixed(0)}%</div>
              {totalTrades > 0 && (
                <div className="text-slate-400 text-xs mt-1">
                  {wins}W / {losses}L
                </div>
              )}
            </div>

            {/* P&L with Trend Arrow */}
            <div>
              <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-1.5">
                <DollarSign className="w-3.5 h-3.5" />
                <span>P&L</span>
              </div>
              <div className={`text-2xl font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {pnl >= 0 ? '+' : '-'}${Math.abs(pnl).toFixed(2)}
              </div>
              {pnl !== 0 && (
                <div className={`flex items-center gap-0.5 text-xs mt-1 ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {pnl >= 0 ? (
                    <TrendingUp className="w-3 h-3" />
                  ) : (
                    <TrendingDown className="w-3 h-3" />
                  )}
                  <span>{pnl >= 0 ? '+' : ''}{pnlPercent.toFixed(1)}%</span>
                </div>
              )}
            </div>

            {/* Expected Value (EV) */}
            <div>
              <div className="flex items-center gap-1.5 text-slate-400 text-xs mb-1.5">
                <Flame className="w-3.5 h-3.5" />
                <span>EV</span>
              </div>
              <div className={`text-2xl font-bold ${expectedValue >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {expectedValue >= 0 ? '+' : ''}${expectedValue.toFixed(2)}
              </div>
              {totalTrades > 0 && (
                <div className="text-slate-400 text-xs mt-1">
                  per trade
                </div>
              )}
            </div>
          </div>

          {/* Mode badges */}
          <div className="flex gap-2">
            {instance.config.use_testnet && (
              <span className="px-3 py-1.5 text-xs font-medium bg-blue-600/20 text-blue-400 rounded-lg flex items-center gap-1.5">
                <Beaker className="w-3.5 h-3.5" />
                Testnet
              </span>
            )}
            {instance.config.paper_trading ? (
              <span className="px-3 py-1.5 text-xs font-medium bg-amber-600/20 text-amber-400 rounded-lg flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                Dry Run
              </span>
            ) : (
              <span className="px-3 py-1.5 text-xs font-medium bg-red-600/20 text-red-400 rounded-lg flex items-center gap-1.5">
                <Flame className="w-3.5 h-3.5" />
                Live Trading
              </span>
            )}
          </div>
        </div>

        {/* Actions - Always show all buttons */}
        <div className="p-4 border-t border-slate-700 flex gap-2" onClick={(e) => e.preventDefault()}>
          <button
            onClick={(e) => {
              e.preventDefault()
              handleAction('start')
            }}
            disabled={actionLoading !== null || isRunning}
            className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 text-white text-sm font-medium rounded-lg transition disabled:opacity-50 ${
              instance.config.paper_trading
                ? 'bg-amber-600 hover:bg-amber-700'
                : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {isRunning || actionLoading === 'start' ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {isRunning ? 'Running' : (instance.config.paper_trading ? 'Dry' : 'Start')}
          </button>
          <button
            onClick={(e) => {
              e.preventDefault()
              handleAction('stop')
            }}
            disabled={actionLoading !== null || !isRunning}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 text-white text-sm font-medium rounded-lg transition disabled:opacity-50 bg-amber-600 hover:bg-amber-700"
          >
            Stop
          </button>
          <button
            onClick={(e) => {
              e.preventDefault()
              if (confirm('⚠️ KILL SWITCH: Immediately terminate this instance?')) {
                handleAction('kill')
              }
            }}
            disabled={actionLoading !== null || !isRunning}
            className="flex items-center justify-center gap-2 px-3 py-2 text-white text-sm font-medium rounded-lg transition disabled:opacity-50 bg-red-700 hover:bg-red-800"
          >
            Kill
          </button>
        </div>
      </div>
    </Link>
  )
}

export default function InstancesPage() {
  const [instances, setInstances] = useState<InstanceCardData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  // Get realtime running instance status from WebSocket
  const { runningInstances, onInstanceStatus } = useRealtime()

  const fetchInstances = useCallback(async () => {
    try {
      setRefreshing(true)
      const res = await fetch('/api/bot/instances?summary=true')
      if (!res.ok) {
        throw new Error('Failed to fetch instances')
      }
      const data = await res.json()
      setInstances(data.instances || [])
      setError(null)
    } catch (err) {
      console.error('Failed to fetch instances:', err)
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    fetchInstances()
    const interval = setInterval(fetchInstances, 10000)
    return () => clearInterval(interval)
  }, [fetchInstances])

  // Listen for realtime instance status updates
  useEffect(() => {
    const unsubscribe = onInstanceStatus((update) => {
      setInstances(prev => prev.map(inst =>
        inst.id === update.instanceId
          ? { ...inst, is_running: update.isRunning }
          : inst
      ))
    })
    return unsubscribe
  }, [onInstanceStatus])

  const handleAction = async (instanceId: string, action: 'start' | 'stop' | 'kill') => {
    try {
      const res = await fetch('/api/bot/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instance_id: instanceId, action })
      })
      if (!res.ok) throw new Error('Action failed')
      await fetchInstances()
    } catch (err) {
      console.error('Action failed:', err)
    }
  }

  const handleCreateInstance = async () => {
    // Prompt for instance name
    const name = prompt('Enter a name for the new instance:')
    if (!name?.trim()) return

    try {
      setLoading(true)
      const res = await fetch('/api/bot/instances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Failed to create instance')
      }

      const data = await res.json()
      console.log(`[INSTANCES] Created new instance: ${data.id}`)

      // Refresh instances list
      await fetchInstances()

      // Redirect to the new instance detail page
      window.location.href = `/instances/${data.id}`
    } catch (err) {
      console.error('Failed to create instance:', err)
      alert(`Failed to create instance: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingState text="Loading instances..." />
  if (error) return <ErrorState message={error} onRetry={fetchInstances} />

  const instancesWithRealtimeStatus = instances.map(inst => ({
    ...inst,
    is_running: runningInstances.includes(inst.id) || inst.is_running
  }))

  const runningCount = instancesWithRealtimeStatus.filter(i => i.is_running).length

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            🤖 Bot Instances
            {runningCount > 0 && (
              <span className="px-2 py-1 text-sm bg-green-600/20 text-green-400 rounded-full">
                {runningCount} running
              </span>
            )}
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            {instancesWithRealtimeStatus.length} instance{instancesWithRealtimeStatus.length !== 1 ? 's' : ''} configured
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchInstances}
            disabled={refreshing}
            className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 transition disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-5 h-5 text-slate-300 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={handleCreateInstance}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-medium"
          >
            <Plus className="w-5 h-5" />
            New Instance
          </button>
        </div>
      </div>

      {/* Global Stats Bar */}
      <StatsBar scope="global" showScopeSelector={false} />

      {/* Instance Cards Grid */}
      {instancesWithRealtimeStatus.length === 0 ? (
        <div className="bg-slate-800 rounded-xl p-12 text-center">
          <div className="text-4xl mb-4">🤖</div>
          <h3 className="text-xl font-semibold text-white mb-2">No instances yet</h3>
          <p className="text-slate-400 mb-6">Create your first bot instance to get started</p>
          <button
            onClick={handleCreateInstance}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-medium"
          >
            <Plus className="w-5 h-5" />
            Create Instance
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-2 gap-4">
          {instancesWithRealtimeStatus.map((instance) => (
            <InstanceCardForNewDesign
              key={instance.id}
              instance={instance}
              onAction={handleAction}
            />
          ))}
        </div>
      )}
    </div>
  )
}


'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { Plus, RefreshCw, Play } from 'lucide-react'
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

  return (
    <Link href={`/instances/${instance.id}`} className="block">
      <div className="bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-600 transition overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-700 hover:bg-slate-700/50 transition cursor-pointer">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-white text-lg">{instance.name}</h3>
              {isRunning ? (
                <span className="px-2 py-0.5 text-xs font-medium bg-green-600/20 text-green-400 rounded-full flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></span>
                  Running
                </span>
              ) : (
                <span className="px-2 py-0.5 text-xs font-medium bg-slate-600/20 text-slate-400 rounded-full">
                  Stopped
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="p-4 space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div>
              <div className="text-slate-400 text-xs">Trades</div>
              <div className="text-white font-semibold">{instance.total_trades}</div>
              <div className="text-slate-500 text-xs">{instance.live_trades} live</div>
            </div>
            <div>
              <div className="text-slate-400 text-xs">Win Rate</div>
              <div className="text-white font-semibold">{(instance.win_rate * 100).toFixed(0)}%</div>
              <div className="text-slate-500 text-xs">-</div>
            </div>
            <div>
              <div className="text-slate-400 text-xs">P&L</div>
              <div className={`font-semibold ${instance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${instance.total_pnl.toFixed(2)}
              </div>
              <div className="text-slate-500 text-xs">-</div>
            </div>
          </div>

          {/* Prompt */}
          <div className="text-xs text-slate-400">
            {instance.prompt_name || 'No prompt'}
          </div>

          {/* Mode badges */}
          <div className="flex gap-2">
            {instance.config.use_testnet && (
              <span className="px-2 py-1 text-xs bg-blue-600/20 text-blue-400 rounded">Testnet</span>
            )}
            {instance.config.paper_trading && (
              <span className="px-2 py-1 text-xs bg-amber-600/20 text-amber-400 rounded">Dry Run</span>
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
        body: JSON.stringify({ instanceId, action })
      })
      if (!res.ok) throw new Error('Action failed')
      await fetchInstances()
    } catch (err) {
      console.error('Action failed:', err)
    }
  }

  const handleCreateInstance = () => {
    // Navigate to bot control or show create modal
    window.location.href = '/bot'
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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


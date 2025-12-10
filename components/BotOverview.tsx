'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Plus, RefreshCw, Loader2 } from 'lucide-react'
import InstanceCard, { InstanceCardData } from './InstanceCard'
import StatsBar from './StatsBar'
import { useRealtime } from '@/hooks/useRealtime'

export default function BotOverview() {
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
    // Refresh every 10 seconds (can be less frequent now with realtime updates)
    const interval = setInterval(fetchInstances, 10000)
    return () => clearInterval(interval)
  }, [fetchInstances])

  // Listen for realtime instance status updates
  useEffect(() => {
    const unsubscribe = onInstanceStatus((update) => {
      console.log('[BotOverview] Instance status update:', update)
      // Update the local instance state immediately
      setInstances(prev => prev.map(inst =>
        inst.id === update.instanceId
          ? { ...inst, is_running: update.isRunning }
          : inst
      ))
    })
    return unsubscribe
  }, [onInstanceStatus])

  // Merge DB status with realtime process status - realtime takes precedence
  const instancesWithRealtimeStatus = useMemo(() => {
    return instances.map(inst => ({
      ...inst,
      // If we have realtime data, use it; otherwise fall back to DB status
      is_running: runningInstances.includes(inst.id) || inst.is_running
    }))
  }, [instances, runningInstances])

  const handleAction = async (instanceId: string, action: 'start' | 'stop' | 'kill') => {
    try {
      const res = await fetch('/api/bot/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          instance_id: instanceId,
        }),
      })
      
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Action failed')
      }
      
      // Refresh instances after action
      await fetchInstances()
    } catch (err) {
      console.error(`Failed to ${action} instance:`, err)
      alert(`Failed to ${action}: ${err instanceof Error ? err.message : 'Unknown error'}`)
    }
  }

  const [creatingInstance, setCreatingInstance] = useState(false)

  const handleCreateInstance = async () => {
    const name = prompt('Enter instance name:')
    if (!name?.trim()) return

    setCreatingInstance(true)
    try {
      const res = await fetch('/api/bot/instances', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() }),
      })

      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || 'Failed to create instance')
      }

      await fetchInstances()
    } catch (err) {
      console.error('Failed to create instance:', err)
      alert(`Failed to create instance: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setCreatingInstance(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300">
          <h3 className="font-semibold">Error loading instances</h3>
          <p className="text-sm mt-1">{error}</p>
          <button
            onClick={async () => {
              setRefreshing(true)
              try {
                await fetchInstances()
              } finally {
                setRefreshing(false)
              }
            }}
            disabled={refreshing}
            className="mt-3 px-3 py-1 bg-red-700 hover:bg-red-600 rounded text-sm flex items-center gap-1"
          >
            {refreshing ? (
              <>
                <Loader2 className="animate-spin h-3 w-3" />
                Retrying...
              </>
            ) : (
              'Retry'
            )}
          </button>
        </div>
      </div>
    )
  }

  // Use the realtime-enhanced instances for display
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
            disabled={creatingInstance}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-medium disabled:opacity-50"
          >
            {creatingInstance ? (
              <>
                <Loader2 className="animate-spin w-5 h-5" />
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-5 h-5" />
                New Instance
              </>
            )}
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
            disabled={creatingInstance}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition font-medium disabled:opacity-50"
          >
            {creatingInstance ? (
              <>
                <Loader2 className="animate-spin w-5 h-5" />
                Creating...
              </>
            ) : (
              <>
                <Plus className="w-5 h-5" />
                Create Instance
              </>
            )}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {instancesWithRealtimeStatus.map((instance) => (
            <InstanceCard
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


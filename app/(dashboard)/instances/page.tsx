'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, RefreshCw } from 'lucide-react'
import InstanceCard, { InstanceCardData } from '@/components/InstanceCard'
import StatsBar from '@/components/StatsBar'
import { useRealtime } from '@/hooks/useRealtime'
import { LoadingState, ErrorState } from '@/components/shared'

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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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


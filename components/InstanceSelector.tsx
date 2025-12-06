'use client'

import { useState, useEffect } from 'react'
import { ChevronDown, Plus, Check } from 'lucide-react'

export interface Instance {
  id: string
  name: string
  prompt_name: string | null
  prompt_version: string | null
  min_confidence: number | null
  max_leverage: number | null
  symbols: string | null  // JSON array
  timeframe: string | null
  settings: string | null  // JSON blob
  is_active: number
  is_running: boolean  // From runs table - true if there's a running run
  current_run_id: string | null  // ID of currently running run
  created_at: string
  updated_at: string | null
}

interface InstanceSelectorProps {
  selectedInstance: Instance | null
  onInstanceChange: (instance: Instance | null) => void
  disabled?: boolean
  refreshInterval?: number  // Optional polling interval in ms (default: 10000)
}

export default function InstanceSelector({
  selectedInstance,
  onInstanceChange,
  disabled = false,
  refreshInterval = 10000  // Refresh every 10 seconds by default
}: InstanceSelectorProps) {
  const [instances, setInstances] = useState<Instance[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchInstances()
    // Set up polling for dynamic status updates
    const interval = setInterval(fetchInstances, refreshInterval)
    return () => clearInterval(interval)
  }, [refreshInterval])

  const fetchInstances = async () => {
    try {
      const res = await fetch('/api/bot/instances')
      if (res.ok) {
        const data = await res.json()
        const newInstances = data.instances || []
        setInstances(newInstances)

        // Auto-select instance if none selected
        if (!selectedInstance && newInstances.length > 0) {
          // Prefer active instance, fallback to first instance
          const active = newInstances.find((i: Instance) => i.is_active)
          onInstanceChange(active || newInstances[0])
        }

        // Update selected instance if its status changed
        if (selectedInstance) {
          const updated = newInstances.find((i: Instance) => i.id === selectedInstance.id)
          if (updated && updated.is_running !== selectedInstance.is_running) {
            onInstanceChange(updated)
          }
        }
      }
    } catch (error) {
      console.error('Failed to fetch instances:', error)
    } finally {
      setLoading(false)
    }
  }

  // Format prompt name for display - always show the actual function name
  const formatPromptName = (promptName: string | null): string => {
    if (!promptName) return 'No prompt set'
    return promptName
  }

  // Format instance ID for display (show first 8 chars of UUID)
  const formatInstanceId = (id: string): string => {
    return id.length > 8 ? id.substring(0, 8) : id
  }

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-lg px-4 py-3 animate-pulse">
        <div className="h-5 bg-slate-700 rounded w-32"></div>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-3 bg-slate-800 rounded-lg px-4 py-3 min-w-[280px] transition ${
          disabled ? 'opacity-50 cursor-not-allowed' : 'hover:bg-slate-700 cursor-pointer'
        }`}
      >
        <div className="flex-1 text-left">
          {selectedInstance ? (
            <>
              <div className="flex items-center gap-2">
                <span className="font-medium text-white">{selectedInstance.name}</span>
                {selectedInstance.is_running ? (
                  <span className="text-xs bg-green-600/20 text-green-400 px-1.5 py-0.5 rounded">Running</span>
                ) : (
                  <span className="text-xs bg-slate-600/20 text-slate-400 px-1.5 py-0.5 rounded">Stopped</span>
                )}
              </div>
              <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
                <span className="text-blue-400">{formatPromptName(selectedInstance.prompt_name)}</span>
                <span className="text-slate-500">•</span>
                <span className="font-mono text-slate-500">{formatInstanceId(selectedInstance.id)}</span>
              </div>
            </>
          ) : (
            <span className="text-slate-400">Select Instance...</span>
          )}
        </div>
        <ChevronDown className={`w-4 h-4 text-slate-400 transition ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-80 overflow-y-auto">
          {instances.length === 0 ? (
            <div className="p-4 text-center text-slate-400 text-sm">
              No instances configured
            </div>
          ) : (
            instances.map((instance) => (
              <button
                key={instance.id}
                onClick={() => {
                  onInstanceChange(instance)
                  setIsOpen(false)
                }}
                className={`w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-700 transition text-left ${
                  selectedInstance?.id === instance.id ? 'bg-slate-700/50' : ''
                }`}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-white">{instance.name}</span>
                    {instance.is_running ? (
                      <span className="text-xs bg-green-600/20 text-green-400 px-1.5 py-0.5 rounded">Running</span>
                    ) : (
                      <span className="text-xs bg-slate-600/30 text-slate-500 px-1.5 py-0.5 rounded">Stopped</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 flex items-center gap-2">
                    <span className="text-blue-400">{formatPromptName(instance.prompt_name)}</span>
                    <span className="text-slate-500">•</span>
                    <span className="font-mono text-slate-500">{formatInstanceId(instance.id)}</span>
                  </div>
                </div>
                {selectedInstance?.id === instance.id && (
                  <Check className="w-4 h-4 text-green-400" />
                )}
              </button>
            ))
          )}
          <div className="border-t border-slate-700">
            <button
              onClick={() => {
                setIsOpen(false)
                // TODO: Open create instance modal
              }}
              className="w-full flex items-center gap-2 px-4 py-3 hover:bg-slate-700 transition text-slate-400 hover:text-white"
            >
              <Plus className="w-4 h-4" />
              <span className="text-sm">Create New Instance</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


'use client'

import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Play, Square, Settings, Clock, Wifi, WifiOff, RefreshCw, Skull, Save } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/shared'
import { useBotState } from '@/lib/context/BotStateContext'
import { useRealtime } from '@/hooks/useRealtime'

interface InstanceHeaderProps {
  instanceId: string
  onSettingsClick: () => void
}

interface ControlStatus {
  success: boolean
  running: boolean
  message: string
  instance_id?: string
  pid?: number | null
  uptime_seconds?: number
  logs?: string[]
}

interface Instance {
  id: string
  name: string
  is_running: number | boolean
  prompt_name?: string
}

interface ConfigItem {
  key: string
  value: string
}

function formatUptime(seconds: number | null): string {
  if (!seconds) return '0m'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export function InstanceHeader({ instanceId, onSettingsClick }: InstanceHeaderProps) {
  // Use shared context for logs persistence
  const { setLogs } = useBotState()

  // Use socket for real-time status updates
  const { socket } = useRealtime()

  const [instance, setInstance] = useState<Instance | null>(null)
  const [controlStatus, setControlStatus] = useState<ControlStatus | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [dryRun, setDryRun] = useState(true)
  const [useTestnet, setUseTestnet] = useState(false)
  const [instanceName, setInstanceName] = useState('')
  const [instanceNameSaving, setInstanceNameSaving] = useState(false)
  const [instanceLoaded, setInstanceLoaded] = useState(false)

  // Fetch instance and config (once on mount)
  const fetchInstanceData = useCallback(async () => {
    try {
      const [instanceRes, configRes] = await Promise.all([
        fetch('/api/bot/instances?summary=true'),
        fetch(`/api/bot/config?instance_id=${instanceId}`)
      ])

      if (instanceRes.ok) {
        const data = await instanceRes.json()
        const inst = data.instances?.find((i: Instance) => i.id === instanceId)
        if (inst) {
          setInstance(inst)
          if (!instanceLoaded) {
            setInstanceName(inst.name)
            setInstanceLoaded(true)
          }
        }
      }

      if (configRes.ok) {
        const data = await configRes.json()
        if (data.config) {
          const configs = data.config as ConfigItem[]
          const paperConfig = configs.find(c => c.key === 'trading.paper_trading')
          const testnetConfig = configs.find(c => c.key === 'bybit.use_testnet')
          if (paperConfig) setDryRun(paperConfig.value === 'true')
          if (testnetConfig) setUseTestnet(testnetConfig.value === 'true')
        }
      }
    } catch (error) {
      console.error('Failed to fetch instance data:', error)
    }
  }, [instanceId, instanceLoaded])

  // Fetch control status (for running state and logs)
  const fetchControlStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/control')
      if (res.ok) {
        const data = await res.json() as ControlStatus
        setControlStatus(data)
        // Update logs in context
        if (data.logs && data.logs.length > 0) {
          setLogs(data.logs)
        }
      }
    } catch (err) {
      console.error('Failed to fetch control status:', err)
    }
  }, [setLogs])

  // Initial load
  useEffect(() => {
    fetchInstanceData()
    fetchControlStatus()
  }, [fetchInstanceData, fetchControlStatus])

  // Poll for control status (running state + logs)
  useEffect(() => {
    const interval = setInterval(fetchControlStatus, 3000)
    return () => clearInterval(interval)
  }, [fetchControlStatus])

  // Listen for real-time instance status changes via socket
  useEffect(() => {
    if (!socket) return

    const handleInstanceStatus = (data: { instanceId: string; isRunning: boolean; reason?: string }) => {
      // Update status immediately when we get a socket event for this instance
      if (data.instanceId === instanceId) {
        setControlStatus(prev => prev ? {
          ...prev,
          running: data.isRunning,
          instance_id: data.isRunning ? instanceId : undefined,
        } : null)
        // Also re-fetch to get full status
        fetchControlStatus()
      }
    }

    socket.on('instance_status', handleInstanceStatus)

    return () => {
      socket.off('instance_status', handleInstanceStatus)
    }
  }, [socket, instanceId, fetchControlStatus])

  const updateConfigValue = async (key: string, value: string) => {
    try {
      await fetch('/api/bot/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: [{ key, value }], instance_id: instanceId })
      })
    } catch (err) {
      console.error(`Failed to update ${key}:`, err)
    }
  }

  const handleBotAction = async (action: 'start' | 'stop' | 'kill') => {
    setActionLoading(true)
    try {
      const res = await fetch('/api/bot/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          paper_trading: dryRun,
          testnet: useTestnet,
          instance_id: instanceId
        })
      })
      const data = await res.json() as ControlStatus
      setControlStatus(data)
      // Update logs if returned
      if (data.logs && data.logs.length > 0) {
        setLogs(data.logs)
      }
      // Refresh instance data
      setTimeout(() => {
        fetchInstanceData()
        fetchControlStatus()
      }, 500)
    } catch (error) {
      console.error(`Failed to ${action} bot:`, error)
    } finally {
      setActionLoading(false)
    }
  }

  const saveInstanceName = async () => {
    if (!instance || instanceName.trim() === '' || instanceName === instance.name) return
    try {
      setInstanceNameSaving(true)
      const res = await fetch('/api/bot/instances', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: instanceId, name: instanceName.trim() })
      })
      if (res.ok) {
        setInstance({ ...instance, name: instanceName.trim() })
      }
    } catch (err) {
      console.error('Failed to save instance name:', err)
    } finally {
      setInstanceNameSaving(false)
    }
  }

  // Check if running for this specific instance
  const isRunning = controlStatus?.running && controlStatus.instance_id === instanceId
  const isPaperTrading = dryRun

  return (
    <div className="bg-slate-800 border-b border-slate-700 px-4 py-3">
      <div className="flex items-center justify-between">
        {/* Left: Back + Instance Name + Status */}
        <div className="flex items-center gap-4">
          <Link href="/instances">
            <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white">
              <ArrowLeft size={16} className="mr-1" />
              Back
            </Button>
          </Link>

          <div className="flex items-center gap-3">
            {/* Editable instance name */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder="Instance name..."
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white w-36 focus:outline-none focus:border-sky-500"
                disabled={isRunning}
              />
              <button
                onClick={saveInstanceName}
                disabled={instanceNameSaving || instanceName === instance?.name || instanceName.trim() === '' || isRunning}
                className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition"
                title="Save instance name"
              >
                {instanceNameSaving ? (
                  <RefreshCw className="w-4 h-4 text-slate-400 animate-spin" />
                ) : (
                  <Save className="w-4 h-4 text-slate-400" />
                )}
              </button>
            </div>
            <StatusBadge status={isRunning ? 'running' : 'stopped'} />
            {isPaperTrading && <StatusBadge status="paper" size="sm" />}
          </div>
        </div>

        {/* Right: Mode Toggles + Uptime + Connection + Actions */}
        <div className="flex items-center gap-3">
          {/* Testnet/Mainnet Toggle */}
          <div className="flex items-center gap-2 bg-slate-700 rounded-lg px-2 py-1.5">
            <span className="text-[10px] text-slate-400 uppercase tracking-wide">Network</span>
            <div className="flex">
              <button
                onClick={() => { setUseTestnet(true); updateConfigValue('bybit.use_testnet', 'true') }}
                disabled={isRunning}
                className={`px-2 py-1 text-xs font-medium rounded-l transition ${
                  useTestnet ? 'bg-blue-600 text-white' : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Testnet
              </button>
              <button
                onClick={() => { setUseTestnet(false); updateConfigValue('bybit.use_testnet', 'false') }}
                disabled={isRunning}
                className={`px-2 py-1 text-xs font-medium rounded-r transition ${
                  !useTestnet ? 'bg-purple-600 text-white' : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Mainnet
              </button>
            </div>
          </div>

          {/* Dry Run / Hot Toggle */}
          <div className="flex items-center gap-2 bg-slate-700 rounded-lg px-2 py-1.5">
            <span className="text-[10px] text-slate-400 uppercase tracking-wide">Mode</span>
            <div className="flex">
              <button
                onClick={() => { setDryRun(true); updateConfigValue('trading.paper_trading', 'true') }}
                disabled={isRunning}
                className={`px-2 py-1 text-xs font-medium rounded-l transition ${
                  dryRun ? 'bg-amber-600 text-white' : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Dry Run
              </button>
              <button
                onClick={() => { setDryRun(false); updateConfigValue('trading.paper_trading', 'false') }}
                disabled={isRunning}
                className={`px-2 py-1 text-xs font-medium rounded-r transition ${
                  !dryRun ? 'bg-red-600 text-white' : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                Hot
              </button>
            </div>
          </div>

          <div className="h-8 w-px bg-slate-600"></div>

          {/* Uptime */}
          {isRunning && controlStatus?.uptime_seconds && (
            <div className="flex items-center gap-1.5 text-slate-400 text-sm">
              <Clock size={14} />
              <span>{formatUptime(controlStatus.uptime_seconds)}</span>
            </div>
          )}

          {/* Connection Status - based on config, not status */}
          <div className="flex items-center gap-1.5 text-sm">
            {isRunning ? (
              useTestnet ? (
                <><Wifi size={14} className="text-yellow-400" /><span className="text-yellow-400">Testnet</span></>
              ) : (
                <><Wifi size={14} className="text-green-400" /><span className="text-green-400">Mainnet</span></>
              )
            ) : (
              <><WifiOff size={14} className="text-slate-500" /><span className="text-slate-500">Offline</span></>
            )}
          </div>

          {/* Settings Button */}
          <Button variant="outline" size="sm" onClick={onSettingsClick}>
            <Settings size={14} className="mr-1" />
            Settings
          </Button>

          {/* Action Buttons - Always show all buttons */}
          <Button
            size="sm"
            onClick={() => handleBotAction('start')}
            disabled={actionLoading || isRunning}
            className={dryRun ? 'bg-amber-600 hover:bg-amber-700 disabled:opacity-50' : 'bg-green-600 hover:bg-green-700 disabled:opacity-50'}
          >
            {isRunning || actionLoading ? <RefreshCw className="w-4 h-4 animate-spin mr-1" /> : <Play size={14} className="mr-1" />}
            {isRunning ? 'Running' : (dryRun ? 'Start (Dry Run)' : 'Start (LIVE)')}
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={() => handleBotAction('stop')}
            disabled={actionLoading || !isRunning}
            className="bg-amber-600 hover:bg-amber-700 disabled:opacity-50"
          >
            {actionLoading && isRunning ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square size={14} className="mr-1" />}
            Stop
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              if (confirm('⚠️ KILL SWITCH: This will immediately terminate the bot!\n\nAre you sure?')) {
                handleBotAction('kill')
              }
            }}
            disabled={actionLoading || !isRunning}
            className="disabled:opacity-50"
          >
            <Skull size={14} className="mr-1" />
            Kill
          </Button>

          {/* PID Info */}
          {isRunning && controlStatus?.pid && (
            <span className="text-xs text-slate-500 tabular-nums">PID: {controlStatus.pid}</span>
          )}
        </div>
      </div>
    </div>
  )
}


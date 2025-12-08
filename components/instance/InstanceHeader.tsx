'use client'

import { useState, useEffect, useCallback } from 'react'
import { ArrowLeft, Play, Square, Settings, Clock, Wifi, WifiOff, RefreshCw, Skull, Save, CheckCircle, X, AlertTriangle } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/shared'
import { useBotState } from '@/lib/context/BotStateContext'
import { useRealtime } from '@/hooks/useRealtime'

interface InstanceHeaderProps {
  instanceId: string
  onSettingsClick: () => void
}

interface HealthCheck {
  service: string
  status: 'ok' | 'error' | 'timeout'
  latency?: number
  error?: string
}

interface HealthStatus {
  overall: 'healthy' | 'degraded' | 'checking'
  timestamp?: string
  checks: HealthCheck[]
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
  const [healthStatus, setHealthStatus] = useState<HealthStatus>({ overall: 'checking', checks: [] })
  const [showHealthModal, setShowHealthModal] = useState(false)

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
      const res = await fetch(`/api/bot/control?instance_id=${instanceId}`)
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
  }, [instanceId, setLogs])

  // Fetch health status
  const fetchHealthStatus = useCallback(async () => {
    try {
      setHealthStatus(prev => ({ ...prev, overall: 'checking' }))
      const res = await fetch('/api/bot/health')
      const data = await res.json()
      setHealthStatus(data)
    } catch (err) {
      console.error('Failed to fetch health status:', err)
      setHealthStatus({
        overall: 'degraded',
        timestamp: new Date().toISOString(),
        checks: [{ service: 'Health API', status: 'error', error: 'Failed to reach health endpoint' }]
      })
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchInstanceData()
    fetchControlStatus()
    fetchHealthStatus()
  }, [fetchInstanceData, fetchControlStatus, fetchHealthStatus])

  // Poll for control status (running state + logs)
  useEffect(() => {
    const interval = setInterval(fetchControlStatus, 3000)
    return () => clearInterval(interval)
  }, [fetchControlStatus])

  // Poll for health status every 60 seconds
  useEffect(() => {
    const interval = setInterval(fetchHealthStatus, 60000)
    return () => clearInterval(interval)
  }, [fetchHealthStatus])

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
    <>
    <div className="bg-slate-800 border-b border-slate-700 px-4 py-3">
      {/* Responsive flex container */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Back + Instance Name + Status */}
        <div className="flex items-center gap-2 sm:gap-4 min-w-0">
          <Link href="/instances" className="shrink-0">
            <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white px-2 sm:px-3">
              <ArrowLeft size={16} className="sm:mr-1" />
              <span className="hidden sm:inline">Back</span>
            </Button>
          </Link>

          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            {/* Editable instance name */}
            <div className="flex items-center gap-1 sm:gap-2 min-w-0">
              <input
                type="text"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
                placeholder="Instance name..."
                className="bg-slate-700 border border-slate-600 rounded px-2 sm:px-3 py-1.5 text-sm text-white w-24 sm:w-36 focus:outline-none focus:border-sky-500"
                disabled={isRunning}
              />
              <button
                onClick={saveInstanceName}
                disabled={instanceNameSaving || instanceName === instance?.name || instanceName.trim() === '' || isRunning}
                className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed transition shrink-0"
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

        {/* Right: Mode Toggles + Health + Actions */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
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

          {/* Network Health Indicator - matches BotDashboard */}
          <button
            onClick={() => { setShowHealthModal(true); fetchHealthStatus() }}
            className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg transition ${
              healthStatus.overall === 'healthy' ? 'bg-green-900/30 hover:bg-green-900/50' :
              healthStatus.overall === 'checking' ? 'bg-slate-700 hover:bg-slate-600' :
              'bg-red-900/30 hover:bg-red-900/50'
            }`}
            title="Network Health"
          >
            {healthStatus.overall === 'healthy' ? (
              <Wifi className="w-4 h-4 text-green-400" />
            ) : healthStatus.overall === 'checking' ? (
              <Wifi className="w-4 h-4 text-slate-400 animate-pulse" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-400" />
            )}
            <span className={`text-xs font-medium ${
              healthStatus.overall === 'healthy' ? 'text-green-400' :
              healthStatus.overall === 'checking' ? 'text-slate-400' : 'text-red-400'
            }`}>
              {healthStatus.overall === 'checking' ? '...' : `${healthStatus.checks.filter(c => c.status === 'ok').length}/${healthStatus.checks.length}`}
            </span>
          </button>

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
            className="bg-amber-600 hover:bg-amber-700"
          >
            <Square size={14} className="mr-1" />
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
          >
            <Skull size={14} className="mr-1" />
            Kill
          </Button>

          {/* PID Info */}
          {isRunning && controlStatus?.pid && (
            <span className="text-xs text-slate-500 tabular-nums hidden sm:inline">PID: {controlStatus.pid}</span>
          )}
        </div>
      </div>
    </div>

    {/* Health Check Modal */}
    {showHealthModal && (
      <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
        <div className="bg-slate-800 rounded-xl w-full max-w-lg flex flex-col shadow-2xl border border-slate-700">
          {/* Modal Header */}
          <div className="flex items-center justify-between p-4 border-b border-slate-700">
            <div className="flex items-center gap-3">
              {healthStatus.overall === 'healthy' ? (
                <Wifi className="w-5 h-5 text-green-400" />
              ) : healthStatus.overall === 'checking' ? (
                <Wifi className="w-5 h-5 text-slate-400 animate-pulse" />
              ) : (
                <WifiOff className="w-5 h-5 text-red-400" />
              )}
              <h2 className="text-lg font-bold text-white">Network Health</h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchHealthStatus}
                className="p-2 rounded bg-slate-700 hover:bg-slate-600 transition"
                title="Refresh"
              >
                <RefreshCw className={`w-4 h-4 text-slate-300 ${healthStatus.overall === 'checking' ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={() => setShowHealthModal(false)}
                className="p-2 rounded bg-slate-700 hover:bg-slate-600 transition"
              >
                <X className="w-4 h-4 text-slate-300" />
              </button>
            </div>
          </div>

          {/* Health Check Results */}
          <div className="p-4 space-y-3">
            {healthStatus.checks.length === 0 ? (
              <div className="text-center text-slate-400 py-8">
                <Wifi className="w-8 h-8 mx-auto mb-2 animate-pulse" />
                <p>Checking network connectivity...</p>
              </div>
            ) : (
              healthStatus.checks.map((check, i) => (
                <div
                  key={i}
                  className={`flex items-center justify-between p-3 rounded-lg border ${
                    check.status === 'ok' ? 'bg-green-900/20 border-green-700/50' :
                    check.status === 'timeout' ? 'bg-amber-900/20 border-amber-700/50' :
                    'bg-red-900/20 border-red-700/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {check.status === 'ok' ? (
                      <CheckCircle className="w-5 h-5 text-green-400" />
                    ) : check.status === 'timeout' ? (
                      <Clock className="w-5 h-5 text-amber-400" />
                    ) : (
                      <AlertTriangle className="w-5 h-5 text-red-400" />
                    )}
                    <div>
                      <div className="font-medium text-white">{check.service}</div>
                      {check.error && (
                        <div className="text-xs text-slate-400">{check.error}</div>
                      )}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-medium ${
                      check.status === 'ok' ? 'text-green-400' :
                      check.status === 'timeout' ? 'text-amber-400' : 'text-red-400'
                    }`}>
                      {check.status.toUpperCase()}
                    </div>
                    {check.latency !== undefined && (
                      <div className="text-xs text-slate-500">{check.latency}ms</div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-3 border-t border-slate-700 text-xs text-slate-500">
            <span>
              Overall: <span className={
                healthStatus.overall === 'healthy' ? 'text-green-400' :
                healthStatus.overall === 'checking' ? 'text-slate-400' : 'text-red-400'
              }>{healthStatus.overall}</span>
            </span>
            {healthStatus.timestamp && (
              <span>Last check: {new Date(healthStatus.timestamp).toLocaleTimeString()}</span>
            )}
          </div>
        </div>
      </div>
    )}
    </>
  )
}


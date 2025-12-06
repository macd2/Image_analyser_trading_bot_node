/**
 * ╔══════════════════════════════════════════════════════════════════════════════╗
 * ║                                                                              ║
 * ║  ⛔ DEPRECATED - DO NOT MODIFY THIS FILE ⛔                                  ║
 * ║                                                                              ║
 * ║  This dashboard component is DEPRECATED and kept for REFERENCE ONLY.        ║
 * ║                                                                              ║
 * ║  ⚠️  WARNING TO AI AGENTS / DEVELOPERS:                                     ║
 * ║  • DO NOT make any changes to this file                                     ║
 * ║  • DO NOT add new features here                                             ║
 * ║  • DO NOT fix bugs here (unless critical security issue)                    ║
 * ║  • DO NOT refactor this code                                                ║
 * ║  • DO NOT update dependencies or imports                                    ║
 * ║                                                                              ║
 * ║  ✅ USE INSTEAD:                                                             ║
 * ║  • /instances page - Main instance management                               ║
 * ║  • components/instance/InstancePage.tsx - New dashboard                     ║
 * ║  • components/instance/tabs/* - Tabbed interface components                 ║
 * ║                                                                              ║
 * ║  📍 ROUTES:                                                                  ║
 * ║  • OLD (this file): /bot/[instanceId]                                       ║
 * ║  • NEW (use this):  /instances/[id]?tab=overview                            ║
 * ║                                                                              ║
 * ║  🎯 BENEFITS OF NEW DASHBOARD:                                              ║
 * ║  • Better organization with separate tabs                                   ║
 * ║  • Improved UI/UX with modern design                                        ║
 * ║  • Better performance and maintainability                                   ║
 * ║  • Consistent with rest of application                                      ║
 * ║                                                                              ║
 * ║  📝 THIS FILE IS KEPT ONLY FOR:                                             ║
 * ║  • Reference during migration                                               ║
 * ║  • Backward compatibility (temporary)                                       ║
 * ║  • Code examples for new features                                           ║
 * ║                                                                              ║
 * ║  🗑️  SCHEDULED FOR REMOVAL: After full migration to /instances              ║
 * ║                                                                              ║
 * ╚══════════════════════════════════════════════════════════════════════════════╝
 */

'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Play, Wallet, Activity, Settings, AlertTriangle,
  RefreshCw, Clock, Zap, CheckCircle, Save,
  Skull, StopCircle, Maximize2, X, Info, Bug, Wifi, WifiOff, ArrowLeft
} from 'lucide-react'
import Link from 'next/link'
import { useBotState } from '@/lib/context/BotStateContext'
import LiveTradeChart from './LiveTradeChart'
import InstanceSelector, { Instance } from './InstanceSelector'
import StatsBar, { StatsScope } from './StatsBar'
import VncLoginModal from './VncLoginModal'

type LogLevel = 'all' | 'error' | 'warning' | 'info' | 'debug'

interface ParsedLog {
  raw: string
  level: LogLevel
  timestamp?: string
  message: string
}

function parseLogLevel(log: string): LogLevel {
  const lower = log.toLowerCase()
  // Check for Python logging format first: | INFO | or | WARNING | or | ERROR | or | DEBUG |
  if (/\|\s*error\s*\|/.test(lower) || lower.includes('exception') || lower.includes('traceback')) {
    return 'error'
  }
  if (/\|\s*warning\s*\|/.test(lower) || lower.includes('⚠️')) {
    return 'warning'
  }
  if (/\|\s*debug\s*\|/.test(lower)) {
    return 'debug'
  }
  if (/\|\s*info\s*\|/.test(lower)) {
    return 'info'
  }
  // Fallback for non-Python logs
  if (lower.includes('[error]') || lower.includes('error:')) {
    return 'error'
  }
  if (lower.includes('[warning]') || lower.includes('warning:')) {
    return 'warning'
  }
  if (lower.includes('[debug]')) {
    return 'debug'
  }
  return 'info'
}

function parseLog(log: string): ParsedLog {
  const level = parseLogLevel(log)
  // Try to extract timestamp like [2024-01-01T12:00:00.000Z] or 2024-01-01 12:00:00
  const timestampMatch = log.match(/\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\]?/)
  const timestamp = timestampMatch ? timestampMatch[1] : undefined
  const message = timestamp && timestampMatch ? log.replace(timestampMatch[0], '').trim() : log
  return { raw: log, level, timestamp, message }
}

function getLogColor(level: LogLevel): string {
  switch (level) {
    case 'error': return 'text-red-400'
    case 'warning': return 'text-amber-400'
    case 'debug': return 'text-purple-400'
    case 'info': return 'text-sky-300'
    default: return 'text-slate-300'
  }
}

function getLogBgColor(level: LogLevel): string {
  switch (level) {
    case 'error': return 'bg-red-950/30 border-l-2 border-red-500'
    case 'warning': return 'bg-amber-950/30 border-l-2 border-amber-500'
    case 'debug': return 'bg-purple-950/30 border-l-2 border-purple-500'
    default: return ''
  }
}

interface BotStatus {
  running: boolean
  mode: string
  network: string
  uptime_seconds: number | null
  wallet: { balance_usdt: number; available_usdt: number; equity_usdt: number }
  positions: Array<{ symbol: string; side: string; size: string; entryPrice: string; unrealisedPnl: string }>
  open_orders: Array<{ symbol: string; side: string; orderType: string; qty: string; price: string }>
  slots: { used: number; max: number; available: number }
  last_cycle: { timeframe: string; boundary_time: string; status: string } | null
  error: string | null
  pid?: number | null
}

interface ControlStatus {
  success: boolean
  running: boolean
  message: string
  uptime_seconds?: number
  logs?: string[]
  pid?: number | null
  instance_id?: string
}

interface Trade {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  exit_price: number | null
  pnl: number | null
  pnl_percent: number | null
  status: string
  confidence: number | null
  created_at: string
  stop_loss: number | null
  take_profit: number | null
  submitted_at: string | null
  filled_at: string | null
  closed_at: string | null
  timeframe: string | null
}

interface ConfigItem {
  key: string
  value: string
  type: 'string' | 'number' | 'boolean' | 'json'
  category: string
  description: string | null
}

interface BotDashboardProps {
  initialInstanceId?: string
}

export default function BotDashboard({ initialInstanceId }: BotDashboardProps) {
  // Use shared context for logs persistence across route changes
  const { logs, setLogs } = useBotState()

  // Instance state
  const [selectedInstance, setSelectedInstance] = useState<Instance | null>(null)
  const [instanceLoaded, setInstanceLoaded] = useState(false)
  const [statsScope, setStatsScope] = useState<StatsScope>('instance')
  const [instanceName, setInstanceName] = useState('')
  const [instanceNameSaving, setInstanceNameSaving] = useState(false)

  const [status, setStatus] = useState<BotStatus | null>(null)
  const [controlStatus, setControlStatus] = useState<ControlStatus | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [tradeStats, setTradeStats] = useState({ total: 0, winning: 0, losing: 0, win_rate: 0, total_pnl: 0 })
  const [config, setConfig] = useState<ConfigItem[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null)
  const [activeConfigCategory, setActiveConfigCategory] = useState('trading')
  const [dryRun, setDryRun] = useState(true)
  const [useTestnet, setUseTestnet] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [pendingChanges, setPendingChanges] = useState<Record<string, string>>({})
  const [savingSettings, setSavingSettings] = useState(false)
  const [availablePrompts, setAvailablePrompts] = useState<Array<{ name: string; description: string }>>([])
  const [promptSaving, setPromptSaving] = useState(false)
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logFilter, setLogFilter] = useState<LogLevel>('all')
  const [showHealthModal, setShowHealthModal] = useState(false)
  const [healthStatus, setHealthStatus] = useState<{
    overall: 'healthy' | 'degraded' | 'checking'
    timestamp?: string
    checks: Array<{
      service: string
      status: 'ok' | 'error' | 'timeout'
      latency?: number
      error?: string
    }>
  }>({ overall: 'checking', checks: [] })

  // Login state for manual TradingView login
  const [loginState, setLoginState] = useState<{
    state: 'idle' | 'waiting_for_login' | 'login_confirmed' | 'browser_opened'
    message: string | null
    browser_opened: boolean
    requires_action: boolean
  }>({ state: 'idle', message: null, browser_opened: false, requires_action: false })
  const [loginActionLoading, setLoginActionLoading] = useState(false)
  const [vncModalOpen, setVncModalOpen] = useState(false)

  // Parse and filter logs
  const parsedLogs = useMemo(() => logs.map(parseLog), [logs])
  const filteredLogs = useMemo(() => {
    if (logFilter === 'all') return parsedLogs
    return parsedLogs.filter(log => log.level === logFilter)
  }, [parsedLogs, logFilter])

  // Count logs by level
  const logCounts = useMemo(() => {
    const counts = { error: 0, warning: 0, info: 0, debug: 0 }
    parsedLogs.forEach(log => {
      if (log.level in counts) counts[log.level as keyof typeof counts]++
    })
    return counts
  }, [parsedLogs])

  // Fetch bot status data (not config - that's instance-specific)
  const fetchBotStatus = useCallback(async (instanceId?: string) => {
    try {
      const tradesUrl = instanceId
        ? `/api/bot/trades?limit=20&instance_id=${instanceId}`
        : '/api/bot/trades?limit=20';

      const [controlRes, statusRes, tradesRes, loginRes, promptsRes] = await Promise.all([
        fetch('/api/bot/control'),
        fetch('/api/bot/status'),
        fetch(tradesUrl),
        fetch('/api/bot/login'),
        fetch('/api/bot/prompts')
      ])

      const controlData = await controlRes.json() as ControlStatus
      const statusData = await statusRes.json()
      const tradesData = await tradesRes.json()
      const loginData = await loginRes.json()
      const promptsData = await promptsRes.json()

      setControlStatus(controlData)
      setStatus({ ...statusData, running: controlData.running, pid: controlData.pid })
      setTrades(tradesData.trades || [])
      setTradeStats(tradesData.stats || { total: 0, winning: 0, losing: 0, win_rate: 0, total_pnl: 0 })
      if (promptsData.success) {
        setAvailablePrompts(promptsData.prompts || [])
      }

      if (loginData.success) {
        setLoginState({
          state: loginData.state,
          message: loginData.message,
          browser_opened: loginData.browser_opened,
          requires_action: loginData.requires_action
        })
      }

      if (controlData.logs && controlData.logs.length > 0) {
        setLogs(controlData.logs)
      }
    } catch (err) {
      console.error('Failed to fetch bot status:', err)
    } finally {
      setLoading(false)
    }
  }, [setLogs])

  // Fetch instance-specific config
  const fetchInstanceConfig = useCallback(async (instanceId: string) => {
    try {
      const res = await fetch(`/api/bot/config?instance_id=${instanceId}`)
      const data = await res.json()
      if (data.config) {
        setConfig(data.config)
        // Sync toggle states from instance config
        const configItems = data.config as ConfigItem[]
        const paperTradingConfig = configItems.find(c => c.key === 'trading.paper_trading')
        const testnetConfig = configItems.find(c => c.key === 'bybit.use_testnet')
        if (paperTradingConfig) {
          setDryRun(paperTradingConfig.value === 'true')
        }
        if (testnetConfig) {
          setUseTestnet(testnetConfig.value === 'true')
        }
      }
    } catch (err) {
      console.error('Failed to fetch instance config:', err)
    }
  }, [])

  // Combined fetch for refreshes
  const fetchData = useCallback(async (instanceId?: string) => {
    await fetchBotStatus(instanceId)
    if (instanceId) {
      await fetchInstanceConfig(instanceId)
    }
  }, [fetchBotStatus, fetchInstanceConfig])

  // Initial fetch and polling for bot status
  useEffect(() => {
    const instanceId = selectedInstance?.id;
    fetchBotStatus(instanceId)
    const interval = setInterval(() => fetchBotStatus(instanceId), 3000)
    return () => clearInterval(interval)
  }, [fetchBotStatus, selectedInstance?.id])

  // Load initial instance if provided via URL
  useEffect(() => {
    if (initialInstanceId && !instanceLoaded) {
      // Fetch the instance data
      fetch('/api/bot/instances')
        .then(res => res.json())
        .then(data => {
          const instance = data.instances?.find((i: Instance) => i.id === initialInstanceId)
          if (instance) {
            setSelectedInstance(instance)
          }
          setInstanceLoaded(true)
        })
        .catch(err => {
          console.error('Failed to load initial instance:', err)
          setInstanceLoaded(true)
        })
    }
  }, [initialInstanceId, instanceLoaded])

  // Fetch instance config when instance changes
  useEffect(() => {
    if (selectedInstance) {
      setInstanceName(selectedInstance.name)
      fetchInstanceConfig(selectedInstance.id)
    } else {
      // Clear config when no instance selected
      setConfig([])
    }
  }, [selectedInstance, fetchInstanceConfig])

  // Save instance name
  const saveInstanceName = async () => {
    if (!selectedInstance || instanceName.trim() === '' || instanceName === selectedInstance.name) return

    try {
      setInstanceNameSaving(true)
      const res = await fetch('/api/bot/instances', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: selectedInstance.id, name: instanceName.trim() })
      })

      if (res.ok) {
        // Update the selected instance with new name
        setSelectedInstance({ ...selectedInstance, name: instanceName.trim() })
      }
    } catch (err) {
      console.error('Failed to save instance name:', err)
    } finally {
      setInstanceNameSaving(false)
    }
  }

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

  // Fetch health status on mount and every 60 seconds
  useEffect(() => {
    fetchHealthStatus()
    const interval = setInterval(fetchHealthStatus, 60000)
    return () => clearInterval(interval)
  }, [fetchHealthStatus])

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
          instance_id: selectedInstance?.id  // Pass instance ID to load per-instance config
        })
      })
      const data = await res.json() as ControlStatus
      if (data.logs) setLogs(data.logs)
      // Immediately update control status
      setControlStatus(data)
      if (status) {
        setStatus({ ...status, running: data.running, pid: data.pid })
      }
      // Fetch full data after a short delay
      setTimeout(() => fetchData(selectedInstance?.id), 500)
    } catch (err) {
      console.error(`Failed to ${action} bot:`, err)
    } finally {
      setActionLoading(false)
    }
  }

  const handleLoginConfirm = async () => {
    setLoginActionLoading(true)
    try {
      const res = await fetch('/api/bot/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'confirm_login' })
      })
      const data = await res.json()
      if (data.success) {
        // Update state locally, will be refreshed by polling
        setLoginState(prev => ({ ...prev, state: 'login_confirmed', message: 'Verifying login...' }))
      }
      // Fetch full data after a short delay
      setTimeout(() => fetchData(selectedInstance?.id), 1000)
    } catch (err) {
      console.error('Failed to confirm login:', err)
    } finally {
      setLoginActionLoading(false)
    }
  }

  const handleConfigChange = (key: string, value: string) => {
    setPendingChanges(prev => ({ ...prev, [key]: value }))
  }

  // Update a single config value immediately (for toggles)
  const updateConfigValue = async (key: string, value: string) => {
    if (!selectedInstance) return
    try {
      await fetch('/api/bot/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: [{ key, value }], instance_id: selectedInstance.id })
      })
    } catch (err) {
      console.error(`Failed to update ${key}:`, err)
    }
  }

  // Update instance prompt
  const handlePromptChange = async (promptName: string) => {
    if (!selectedInstance) return
    setPromptSaving(true)
    try {
      const res = await fetch('/api/bot/instances', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: selectedInstance.id, prompt_name: promptName })
      })
      const data = await res.json()
      if (data.success && data.instance) {
        setSelectedInstance(data.instance)
      }
    } catch (err) {
      console.error('Failed to update prompt:', err)
    } finally {
      setPromptSaving(false)
    }
  }

  const handleSaveSettings = async () => {
    if (!selectedInstance) return
    const updates = Object.entries(pendingChanges).map(([key, value]) => ({ key, value }))
    if (updates.length === 0) return

    setSavingSettings(true)
    try {
      const res = await fetch('/api/bot/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates, instance_id: selectedInstance.id })
      })
      const data = await res.json()
      // Update config directly from response for immediate feedback
      if (data.config) {
        setConfig(data.config)
      }
      setPendingChanges({})
    } catch (err) {
      console.error('Failed to update config:', err)
    } finally {
      setSavingSettings(false)
    }
  }

  const categories = [...new Set(config.map(c => c.category))]
  const filteredConfig = config.filter(c => c.category === activeConfigCategory)
  const hasPendingChanges = Object.keys(pendingChanges).length > 0

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <div className="text-slate-400">Loading bot data...</div>
      </div>
    )
  }

  // Determine if bot is running
  // Check if the running instance matches the selected instance
  const isRunning = selectedInstance
    ? (controlStatus?.running && controlStatus.instance_id === selectedInstance.id) || selectedInstance.is_running
    : (status?.running ?? false)

  return (
    <div className="p-6 space-y-6">
      {/* Header - Bot Control Bar */}
      <div className="bg-slate-800/50 rounded-xl p-4 space-y-4">
        {/* Row 1: Title + Instance Selector + Action Buttons */}
        <div className="flex items-center justify-between gap-4">
          {/* Left: Back Button + Title and Instance Selector */}
          <div className="flex items-center gap-4 flex-shrink-0">
            {/* Back button when viewing specific instance */}
            {initialInstanceId && (
              <Link
                href="/bot"
                className="p-2 rounded-lg bg-slate-700 hover:bg-slate-600 transition"
                title="Back to all instances"
              >
                <ArrowLeft className="w-5 h-5 text-slate-300" />
              </Link>
            )}
            <div className="flex items-center gap-2">
              <span className="text-2xl">🤖</span>
              <div>
                <h2 className="text-lg font-bold text-white leading-tight">
                  {selectedInstance ? selectedInstance.name : 'Bot Control'}
                </h2>
                <p className="text-slate-400 text-xs">
                  {selectedInstance ? 'Instance Details' : 'Manage your trading bot'}
                </p>
              </div>
            </div>
            {/* Only show instance selector if not viewing a specific instance */}
            {!initialInstanceId && (
              <InstanceSelector
                selectedInstance={selectedInstance}
                onInstanceChange={setSelectedInstance}
                disabled={isRunning}
              />
            )}
            {/* Instance Name Editor */}
            {selectedInstance && (
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
                  disabled={instanceNameSaving || instanceName === selectedInstance.name || instanceName.trim() === '' || isRunning}
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
            )}
          </div>

          {/* Right: Mode Toggles + Health + Refresh + Action Buttons */}
          <div className="flex items-center gap-3 flex-shrink-0">
            {/* Testnet/Mainnet Toggle */}
            <div className="flex items-center gap-2 bg-slate-700 rounded-lg px-2 py-1.5">
              <span className="text-[10px] text-slate-400 uppercase tracking-wide">Network</span>
              <div className="flex">
                <button
                  onClick={() => { setUseTestnet(true); updateConfigValue('bybit.use_testnet', 'true') }}
                  disabled={isRunning}
                  className={`px-2 py-1 text-xs font-medium rounded-l transition ${
                    useTestnet
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                  } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Testnet
                </button>
                <button
                  onClick={() => { setUseTestnet(false); updateConfigValue('bybit.use_testnet', 'false') }}
                  disabled={isRunning}
                  className={`px-2 py-1 text-xs font-medium rounded-r transition ${
                    !useTestnet
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
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
                    dryRun
                      ? 'bg-amber-600 text-white'
                      : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                  } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Dry Run
                </button>
                <button
                  onClick={() => { setDryRun(false); updateConfigValue('trading.paper_trading', 'false') }}
                  disabled={isRunning}
                  className={`px-2 py-1 text-xs font-medium rounded-r transition ${
                    !dryRun
                      ? 'bg-red-600 text-white'
                      : 'bg-slate-600 text-slate-400 hover:bg-slate-500'
                  } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  Hot
                </button>
              </div>
            </div>

            {/* Divider */}
            <div className="h-8 w-px bg-slate-600"></div>

            {/* Network Health Indicator */}
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
                {healthStatus.overall === 'checking' ? '...' : healthStatus.checks.filter(c => c.status === 'ok').length}/{healthStatus.checks.length}
              </span>
            </button>

            {/* Refresh Button */}
            <button
              onClick={() => fetchData(selectedInstance?.id)}
              className="p-2 rounded bg-slate-700 hover:bg-slate-600 transition"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 text-slate-300 ${actionLoading ? 'animate-spin' : ''}`} />
            </button>

            {/* Divider */}
            <div className="h-8 w-px bg-slate-600"></div>

            {/* Action Buttons - Fixed width container to prevent layout shift */}
            <div className="flex items-center gap-2 min-w-[260px] justify-end">
              {isRunning ? (
                <>
                  {/* Stop Button - Graceful */}
                  <button
                    onClick={() => handleBotAction('stop')}
                    disabled={actionLoading}
                    className="flex items-center gap-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition disabled:opacity-50 font-medium"
                    title="Graceful shutdown - waits for current operation to complete"
                  >
                    {actionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <StopCircle className="w-4 h-4" />}
                    <span>Stop</span>
                  </button>
                  {/* Kill Button - Immediate */}
                  <button
                    onClick={() => {
                      if (confirm('⚠️ KILL SWITCH: This will immediately terminate the bot!\n\nAny in-progress operations will be interrupted.\n\nAre you sure?')) {
                        handleBotAction('kill')
                      }
                    }}
                    disabled={actionLoading}
                    className="flex items-center gap-2 px-4 py-2 bg-red-700 hover:bg-red-800 text-white rounded-lg transition disabled:opacity-50 font-medium"
                    title="KILL SWITCH - Immediately terminate the bot"
                  >
                    <Skull className="w-4 h-4" />
                    <span>Kill</span>
                  </button>
                </>
              ) : (
                <button
                  onClick={() => handleBotAction('start')}
                  disabled={actionLoading}
                  className={`flex items-center gap-2 px-5 py-2 rounded-lg transition disabled:opacity-50 font-medium text-white ${
                    dryRun
                      ? 'bg-amber-600 hover:bg-amber-700'
                      : 'bg-green-600 hover:bg-green-700'
                  }`}
                >
                  {actionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  <span>{dryRun ? 'Start (Dry Run)' : 'Start (LIVE)'}</span>
                </button>
              )}
            </div>

            {/* PID Info */}
            {isRunning && status?.pid && (
              <span className="text-xs text-slate-500 tabular-nums">PID: {status.pid}</span>
            )}
          </div>
        </div>

        {/* Stats Bar */}
        <StatsBar
          scope={statsScope}
          scopeId={selectedInstance?.id}
          onScopeChange={setStatsScope}
          showScopeSelector={true}
        />
      </div>

      {/* Manual Login Required Banner */}
      {loginState.requires_action && (
        <div className="bg-amber-900/50 border border-amber-600 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 text-amber-400 animate-pulse" />
            <div>
              <h3 className="text-amber-200 font-semibold">🔐 Manual Login Required</h3>
              <p className="text-amber-300/80 text-sm">
                {loginState.message || 'TradingView session expired. Click below to login.'}
              </p>
              {loginState.browser_opened && (
                <p className="text-amber-400 text-xs mt-1">
                  ✓ Browser window opened - complete login, then click Confirm below
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!loginState.browser_opened && (
              <button
                onClick={() => setVncModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition font-medium"
              >
                <Maximize2 className="w-4 h-4" />
                Open Browser Login
              </button>
            )}
            {loginState.browser_opened && (
              <button
                onClick={handleLoginConfirm}
                disabled={loginActionLoading}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition disabled:opacity-50 font-medium"
              >
                {loginActionLoading ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <CheckCircle className="w-4 h-4" />
                )}
                Confirm Login
              </button>
            )}
            <button
              onClick={async () => {
                await fetch('/api/bot/login', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ action: 'reset' })
                })
                setLoginState({ state: 'idle', message: null, browser_opened: false, requires_action: false })
              }}
              className="p-2 rounded hover:bg-amber-800/50 transition"
              title="Dismiss"
            >
              <X className="w-4 h-4 text-amber-400" />
            </button>
          </div>
        </div>
      )}

      {/* Status Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatusCard
          icon={isRunning ? CheckCircle : AlertTriangle}
          label="Bot Status"
          value={isRunning ? 'Running' : 'Stopped'}
          sub={`${status?.mode || 'N/A'} • ${status?.network || 'N/A'}`}
          positive={isRunning}
        />
        <StatusCard
          icon={Wallet}
          label="Wallet Balance"
          value={`$${status?.wallet?.balance_usdt?.toFixed(2) || '0.00'}`}
          sub={`Available: $${status?.wallet?.available_usdt?.toFixed(2) || '0.00'}`}
          positive={true}
        />
        <StatusCard
          icon={Zap}
          label="Trade Slots"
          value={`${status?.slots?.used || 0} / ${status?.slots?.max || 3}`}
          sub={`${status?.slots?.available || 3} available`}
          positive={(status?.slots?.available || 0) > 0}
        />
        <StatusCard
          icon={Activity}
          label="Win Rate"
          value={`${tradeStats.win_rate.toFixed(1)}%`}
          sub={`${tradeStats.winning}W / ${tradeStats.losing}L`}
          positive={tradeStats.win_rate >= 50}
        />
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Positions & Trades */}
        <div className="lg:col-span-2 space-y-6">
          {/* Open Positions */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
              <Activity className="w-4 h-4" /> Open Positions ({status?.positions?.length || 0})
            </h3>
            {status?.positions && status.positions.length > 0 ? (
              <div className="space-y-2">
                {status.positions.map((pos, idx) => (
                  <div key={idx} className="flex items-center justify-between p-3 bg-slate-700/30 rounded border border-slate-600/30">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-white">{pos.symbol}</span>
                        <span className={`text-xs px-2 py-0.5 rounded ${pos.side === 'Buy' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                          {pos.side === 'Buy' ? 'LONG' : 'SHORT'}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">Size: {pos.size} @ ${parseFloat(pos.entryPrice).toFixed(2)}</div>
                    </div>
                    <div className={`text-right font-bold ${parseFloat(pos.unrealisedPnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {parseFloat(pos.unrealisedPnl) >= 0 ? '+' : ''}${parseFloat(pos.unrealisedPnl).toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-slate-500 text-sm p-4 text-center">No open positions</div>
            )}
          </div>

          {/* Recent Trades */}
          <div className="card">
            <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4" /> Recent Trades ({trades.filter(t => t.status !== 'rejected').length})
            </h3>
            {trades.filter(t => t.status !== 'rejected').length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 text-xs">
                      <th className="text-left py-2">Symbol</th>
                      <th className="text-left py-2">Side</th>
                      <th className="text-right py-2">Entry</th>
                      <th className="text-right py-2">P&L</th>
                      <th className="text-right py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.filter(t => t.status !== 'rejected').slice(0, 10).map((trade) => (
                      <tr
                        key={trade.id}
                        className="border-t border-slate-700/50 hover:bg-slate-800/50 cursor-pointer transition-colors"
                        onClick={() => setSelectedTrade(trade)}
                      >
                        <td className="py-2 font-mono font-bold text-white">{trade.symbol}</td>
                        <td className="py-2">
                          <span className={trade.side === 'Buy' ? 'text-green-400' : 'text-red-400'}>
                            {trade.side === 'Buy' ? '↑ LONG' : '↓ SHORT'}
                          </span>
                        </td>
                        <td className="py-2 text-right text-slate-300">${trade.entry_price.toFixed(2)}</td>
                        <td className="py-2 text-right">
                          {trade.pnl !== null ? (
                            <span className={trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                              {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                            </span>
                          ) : '-'}
                        </td>
                        <td className="py-2 text-right">
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            trade.status === 'filled' ? 'bg-green-900/50 text-green-400' :
                            trade.status === 'pending' ? 'bg-yellow-900/50 text-yellow-400' :
                            trade.status === 'closed' ? 'bg-slate-700 text-slate-300' :
                            'bg-slate-700 text-slate-400'
                          }`}>
                            {trade.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-slate-500 text-sm p-4 text-center">No trades yet</div>
            )}
          </div>
        </div>

        {/* Right: Config */}
        <div className="space-y-6">
          <div className="card">
            {/* Settings Header - Collapsible */}
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="w-full flex items-center justify-between text-sm font-bold text-white mb-3"
            >
              <span className="flex items-center gap-2">
                <Settings className="w-4 h-4" /> Configuration
                {hasPendingChanges && (
                  <span className="text-xs bg-amber-600 text-white px-1.5 py-0.5 rounded">
                    {Object.keys(pendingChanges).length} unsaved
                  </span>
                )}
              </span>
              <span className={`transition-transform ${showSettings ? 'rotate-180' : ''}`}>▼</span>
            </button>

            {showSettings && (
              <>
                {!selectedInstance ? (
                  <div className="p-4 text-center text-slate-400 text-sm">
                    Select an instance to view and edit settings
                  </div>
                ) : (
                <>
                {/* Category Tabs */}
                <div className="flex flex-wrap gap-1 mb-3">
                  {categories.map(cat => (
                    <button
                      key={cat}
                      onClick={() => setActiveConfigCategory(cat)}
                      className={`text-xs px-2.5 py-1.5 rounded-md transition capitalize ${
                        activeConfigCategory === cat
                          ? 'bg-blue-600 text-white'
                          : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>

                {/* Instance Prompt Selector - show in AI category */}
                {activeConfigCategory === 'ai' && selectedInstance && (
                  <div className="p-2.5 rounded-lg border bg-blue-900/20 border-blue-600/50 mb-3">
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <label className="text-xs text-slate-300 font-medium">
                        Instance Prompt
                      </label>
                      {promptSaving && <RefreshCw className="w-3 h-3 animate-spin text-blue-400" />}
                    </div>
                    <select
                      value={selectedInstance.prompt_name || ''}
                      onChange={(e) => handlePromptChange(e.target.value)}
                      disabled={promptSaving || isRunning}
                      className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none disabled:opacity-50"
                    >
                      <option value="">Select a prompt...</option>
                      {availablePrompts.map(p => (
                        <option key={p.name} value={p.name}>{p.name}</option>
                      ))}
                    </select>
                    <div className="text-[10px] text-slate-500 mt-1 leading-tight">
                      Prompt used for AI chart analysis (saved to instance)
                    </div>
                  </div>
                )}

                {/* Config Items - Grid Layout */}
                <div className="space-y-2 max-h-[400px] overflow-y-auto pr-1">
                  {filteredConfig.map(item => {
                    const shortKey = item.key.split('.').pop() || item.key
                    const currentValue = pendingChanges[item.key] ?? item.value
                    const isChanged = pendingChanges[item.key] !== undefined
                    const isBoolean = item.value === 'true' || item.value === 'false'

                    return (
                      <div key={item.key} className={`p-2.5 rounded-lg border transition ${
                        isChanged
                          ? 'bg-amber-900/20 border-amber-600/50'
                          : 'bg-slate-800/50 border-slate-700/50'
                      }`}>
                        <div className="flex items-center justify-between gap-2">
                          <label className="text-xs text-slate-300 font-medium flex-1" title={item.key}>
                            {shortKey.replace(/_/g, ' ')}
                          </label>
                          {isBoolean ? (
                            <button
                              onClick={() => handleConfigChange(item.key, currentValue === 'true' ? 'false' : 'true')}
                              className={`relative w-10 h-5 rounded-full transition ${
                                currentValue === 'true' ? 'bg-green-600' : 'bg-slate-600'
                              }`}
                            >
                              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${
                                currentValue === 'true' ? 'left-5' : 'left-0.5'
                              }`} />
                            </button>
                          ) : (
                            <input
                              type="text"
                              value={currentValue}
                              onChange={(e) => handleConfigChange(item.key, e.target.value)}
                              className="w-24 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-xs text-white text-right focus:border-blue-500 focus:outline-none"
                            />
                          )}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-1 leading-tight">{item.description}</div>
                      </div>
                    )
                  })}
                </div>

                {/* Save Button */}
                {hasPendingChanges && (
                  <div className="mt-3 pt-3 border-t border-slate-700 flex items-center justify-between">
                    <span className="text-xs text-amber-400">
                      {Object.keys(pendingChanges).length} setting(s) changed
                    </span>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setPendingChanges({})}
                        className="px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 rounded transition"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSaveSettings}
                        disabled={savingSettings}
                        className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 rounded transition font-medium flex items-center gap-1.5 disabled:opacity-50"
                      >
                        {savingSettings ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            Saving...
                          </>
                        ) : (
                          'Save Changes'
                        )}
                      </button>
                    </div>
                  </div>
                )}
                </>
                )}
              </>
            )}
          </div>

          {/* Logs Preview */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-bold text-white">Bot Logs</h3>
                {/* Log level counts */}
                <div className="flex items-center gap-2 text-xs">
                  {logCounts.error > 0 && (
                    <span className="px-1.5 py-0.5 bg-red-900/50 text-red-400 rounded">{logCounts.error} errors</span>
                  )}
                  {logCounts.warning > 0 && (
                    <span className="px-1.5 py-0.5 bg-amber-900/50 text-amber-400 rounded">{logCounts.warning} warn</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {logs.length > 0 && (
                  <button
                    onClick={() => setLogs([])}
                    className="text-xs text-slate-500 hover:text-slate-300"
                  >
                    Clear
                  </button>
                )}
                <button
                  onClick={() => setShowLogsModal(true)}
                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition"
                  title="Expand logs"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            <div className="bg-slate-900 rounded p-2 h-40 overflow-y-auto font-mono text-xs">
              {parsedLogs.length > 0 ? (
                parsedLogs.slice(-15).map((log, idx) => (
                  <div
                    key={idx}
                    className={`py-0.5 px-1 ${getLogColor(log.level)} ${getLogBgColor(log.level)}`}
                  >
                    {log.raw}
                  </div>
                ))
              ) : (
                <div className="text-slate-500 italic">No logs yet. Start the bot to see output.</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Logs Modal */}
      {showLogsModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl border border-slate-700">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center gap-4">
                <h2 className="text-lg font-bold text-white">Bot Logs</h2>
                <span className="text-xs text-slate-400">{logs.length} total entries</span>
              </div>
              <div className="flex items-center gap-3">
                {/* Filter Buttons */}
                <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
                  <button
                    onClick={() => setLogFilter('all')}
                    className={`px-3 py-1.5 text-xs rounded transition ${
                      logFilter === 'all' ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    All ({logs.length})
                  </button>
                  <button
                    onClick={() => setLogFilter('error')}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded transition ${
                      logFilter === 'error' ? 'bg-red-900/50 text-red-400' : 'text-slate-400 hover:text-red-400'
                    }`}
                  >
                    <AlertTriangle className="w-3 h-3" /> Error ({logCounts.error})
                  </button>
                  <button
                    onClick={() => setLogFilter('warning')}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded transition ${
                      logFilter === 'warning' ? 'bg-amber-900/50 text-amber-400' : 'text-slate-400 hover:text-amber-400'
                    }`}
                  >
                    <AlertTriangle className="w-3 h-3" /> Warn ({logCounts.warning})
                  </button>
                  <button
                    onClick={() => setLogFilter('info')}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded transition ${
                      logFilter === 'info' ? 'bg-sky-900/50 text-sky-400' : 'text-slate-400 hover:text-sky-400'
                    }`}
                  >
                    <Info className="w-3 h-3" /> Info ({logCounts.info})
                  </button>
                  <button
                    onClick={() => setLogFilter('debug')}
                    className={`flex items-center gap-1 px-3 py-1.5 text-xs rounded transition ${
                      logFilter === 'debug' ? 'bg-purple-900/50 text-purple-400' : 'text-slate-400 hover:text-purple-400'
                    }`}
                  >
                    <Bug className="w-3 h-3" /> Debug ({logCounts.debug})
                  </button>
                </div>
                <button
                  onClick={() => setLogs([])}
                  className="text-xs text-slate-400 hover:text-white px-2 py-1"
                >
                  Clear All
                </button>
                <button
                  onClick={() => setShowLogsModal(false)}
                  className="p-1.5 rounded hover:bg-slate-700 transition"
                >
                  <X className="w-5 h-5 text-slate-400" />
                </button>
              </div>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-4 bg-slate-900">
              <div className="font-mono text-sm space-y-0.5">
                {filteredLogs.length > 0 ? (
                  filteredLogs.map((log, idx) => (
                    <div
                      key={idx}
                      className={`py-1 px-2 rounded ${getLogColor(log.level)} ${getLogBgColor(log.level)}`}
                    >
                      {log.timestamp && (
                        <span className="text-slate-500 mr-2">[{log.timestamp}]</span>
                      )}
                      <span>{log.message}</span>
                    </div>
                  ))
                ) : (
                  <div className="text-slate-500 italic text-center py-8">
                    {logs.length > 0 ? `No ${logFilter} logs found` : 'No logs yet. Start the bot to see output.'}
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-3 border-t border-slate-700 text-xs text-slate-400">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-red-500"></span> Error</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-amber-500"></span> Warning</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-sky-500"></span> Info</span>
                <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-purple-500"></span> Debug</span>
              </div>
              <span>Showing {filteredLogs.length} of {logs.length} logs</span>
            </div>
          </div>
        </div>
      )}

      {/* Trade Chart Modal */}
      {selectedTrade && (
        <TradeChartModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
      )}

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

      {/* VNC Login Modal */}
      <VncLoginModal
        isOpen={vncModalOpen}
        onClose={() => setVncModalOpen(false)}
        onConfirm={handleLoginConfirm}
        loginState={loginState}
      />
    </div>
  )
}

// Status Card Component
function StatusCard({ icon: Icon, label, value, sub, positive }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  sub: string
  positive?: boolean
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${positive ? 'bg-green-900/30' : 'bg-slate-700'}`}>
          <Icon className={`w-5 h-5 ${positive ? 'text-green-400' : 'text-slate-400'}`} />
        </div>
        <div>
          <div className="text-xs text-slate-400">{label}</div>
          <div className="text-lg font-bold text-white">{value}</div>
          <div className="text-xs text-slate-500">{sub}</div>
        </div>
      </div>
    </div>
  )
}

// Trade Chart Modal Component
function TradeChartModal({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const [priceDecimals, setPriceDecimals] = useState<number>(2)

  // Fetch price precision from API when modal opens
  useEffect(() => {
    const fetchPrecision = async () => {
      try {
        const timestamp = new Date(trade.submitted_at || trade.filled_at || trade.created_at).getTime()
        const res = await fetch(
          `/api/bot/trade-candles?symbol=${trade.symbol}&timeframe=${trade.timeframe || '1h'}&timestamp=${timestamp}&before=1&after=1`
        )
        const data = await res.json()
        if (data.precision?.priceDecimals !== undefined) {
          setPriceDecimals(data.precision.priceDecimals)
        }
      } catch (err) {
        console.error('Failed to fetch precision:', err)
      }
    }
    fetchPrecision()
  }, [trade])

  const formatPrice = (price: number | null) => {
    if (price === null) return '-'
    return `$${price.toFixed(priceDecimals)}`
  }

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-lg max-w-6xl w-full max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-xl font-bold text-white">{trade.symbol}</h2>
            <span className={trade.side === 'Buy' ? 'text-green-400' : 'text-red-400'}>
              {trade.side === 'Buy' ? '↑ LONG' : '↓ SHORT'}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${
              trade.status === 'filled' ? 'bg-green-900/50 text-green-400' :
              trade.status === 'pending' ? 'bg-yellow-900/50 text-yellow-400' :
              trade.status === 'closed' ? 'bg-slate-700 text-slate-300' :
              'bg-slate-700 text-slate-400'
            }`}>
              {trade.status}
            </span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Trade Info */}
        <div className="grid grid-cols-4 gap-4 p-4 bg-slate-800/50">
          <div>
            <div className="text-xs text-slate-400">Entry Price</div>
            <div className="text-lg font-bold text-white">{formatPrice(trade.entry_price)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Stop Loss</div>
            <div className="text-lg font-bold text-red-400">{formatPrice(trade.stop_loss)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Take Profit</div>
            <div className="text-lg font-bold text-green-400">{formatPrice(trade.take_profit)}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">P&L</div>
            <div className={`text-lg font-bold ${trade.pnl !== null && trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {trade.pnl !== null ? `${trade.pnl >= 0 ? '+' : ''}$${trade.pnl.toFixed(priceDecimals)}` : '-'}
            </div>
          </div>
        </div>

        {/* Chart */}
        <div className="p-4">
          <LiveTradeChart trade={trade} height={500} />
        </div>
      </div>
    </div>
  )
}


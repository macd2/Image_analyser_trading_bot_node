'use client'

import { useState } from 'react'
import { Play, Square, Skull, ChevronRight, RefreshCw, FileText, Clock, Target, Activity, AlertCircle } from 'lucide-react'
import Link from 'next/link'
import { useBotState } from '@/lib/context/BotStateContext'

type LogLevel = 'error' | 'warning' | 'info' | 'debug' | 'all'

interface ParsedLog {
  raw: string
  level: LogLevel
  timestamp?: string
  message: string
}

function parseLogLevel(log: string): LogLevel {
  const lower = log.toLowerCase()
  if (/\|\s*error\s*\|/.test(lower) || lower.includes('[error]') || lower.includes('error:')) return 'error'
  if (/\|\s*warning\s*\|/.test(lower) || lower.includes('[warning]') || lower.includes('warning:')) return 'warning'
  if (/\|\s*debug\s*\|/.test(lower) || lower.includes('[debug]')) return 'debug'
  return 'info'
}

function parseLog(log: string): ParsedLog {
  const level = parseLogLevel(log)
  const timestampMatch = log.match(/\[?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\]?/)
  const timestamp = timestampMatch ? timestampMatch[1] : undefined
  const message = timestamp && timestampMatch ? log.replace(timestampMatch[0], '').trim() : log
  return { raw: log, level, timestamp, message }
}

export interface InstanceCardData {
  id: string
  name: string
  prompt_name: string | null
  timeframe?: string | null
  is_running: boolean
  current_run_id: string | null
  total_trades: number
  live_trades: number
  dry_run_trades: number
  win_count: number
  loss_count: number
  total_pnl: number
  win_rate: number
  expected_value: number
  avg_win: number
  avg_loss: number
  config: {
    use_testnet: boolean
    paper_trading: boolean
  }
  running_duration_hours?: number
  latest_cycle?: {
    charts_captured: number
    recommendations_generated: number
    trades_executed: number
  }
  // NEW: Detailed breakdown for live vs dry
  live_closed: number
  live_open: number
  live_wins: number
  live_losses: number
  live_pnl: number
  live_ev: number
  dry_closed: number
  dry_open: number
  dry_wins: number
  dry_losses: number
  dry_pnl: number
  dry_ev: number
  // Signal quality metrics
  last_cycle_symbols: string[]
  actionable_percent: number
  actionable_count: number
  total_recs: number
  avg_confidence: number
  avg_risk_reward: number
  // Recent logs
  recent_logs: { timestamp: string; level: string; message: string }[]
}

interface InstanceCardProps {
  instance: InstanceCardData
  onAction?: (instanceId: string, action: 'start' | 'stop' | 'kill') => Promise<void>
}

function RecentLogsSection({ instance }: { instance: InstanceCardData }) {
  const { logs } = useBotState()
  const liveLogs = logs[instance.id] || []

  // Parse live logs
  const parsedLiveLogs = liveLogs.map(parseLog).slice(-3) // last 3

  // Fallback to instance.recent_logs if no live logs
  const logsToDisplay = parsedLiveLogs.length > 0 ? parsedLiveLogs :
    instance.recent_logs?.slice(0, 3).map(log => ({
      raw: log.message,
      level: log.level as LogLevel,
      timestamp: log.timestamp,
      message: log.message
    })) || []

  if (logsToDisplay.length === 0) {
    return null
  }

  return (
    <div className="px-4 py-2 bg-slate-900/70">
      <div className="text-[10px] text-slate-500 font-medium uppercase tracking-wide mb-1.5">Recent Logs</div>
      <div className="space-y-1">
        {logsToDisplay.map((log, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <AlertCircle className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${
              log.level === 'error' ? 'text-red-400' :
              log.level === 'warning' ? 'text-amber-400' : 'text-slate-500'
            }`} />
            <span className="text-slate-500 shrink-0">
              {log.timestamp ? new Date(log.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) : '--:--'}
            </span>
            <span className="text-slate-400 truncate">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function InstanceCard({ instance, onAction }: InstanceCardProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const handleAction = async (action: 'start' | 'stop' | 'kill', e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!onAction) return
    if (action === 'kill' && !confirm('⚠️ KILL SWITCH: Immediately terminate this instance?')) return
    setActionLoading(action)
    try {
      await onAction(instance.id, action)
    } finally {
      setActionLoading(null)
    }
  }

  const isRunning = instance.is_running

  // Format running duration
  const formatDuration = (hours: number) => {
    if (hours < 1) return `${Math.round(hours * 60)}m`
    if (hours < 24) return `${hours.toFixed(1)}h`
    return `${(hours / 24).toFixed(1)}d`
  }

  // Format symbols list (deduplicate first)
  const formatSymbols = (symbols: string[]) => {
    if (!symbols || symbols.length === 0) return null
    // Deduplicate symbols
    const uniqueSymbols = Array.from(new Set(symbols))
    if (uniqueSymbols.length <= 3) return uniqueSymbols.join(', ')
    return `${uniqueSymbols.slice(0, 3).join(', ')} (+${uniqueSymbols.length - 3})`
  }

  // Calculate win rates per mode
  const liveClosedTotal = (instance.live_wins || 0) + (instance.live_losses || 0)
  const dryClosedTotal = (instance.dry_wins || 0) + (instance.dry_losses || 0)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-600 transition overflow-hidden group">
      {/* ═══════════════ SECTION 1: IDENTITY ═══════════════ */}
      <div className="p-4 border-b border-slate-700">
        {/* Row 1: Name + Status */}
        <div className="flex items-center justify-between gap-3 mb-3">
          <Link href={`/instances/${instance.id}`} className="flex-1 min-w-0">
            <h3 className="font-bold text-white text-xl truncate hover:text-blue-400 transition">
              {instance.name}
            </h3>
          </Link>
          {isRunning ? (
            <span className="shrink-0 px-3 py-1 text-sm font-medium bg-green-600/20 text-green-400 rounded-full flex items-center gap-1.5">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              Running
              {instance.running_duration_hours !== undefined && (
                <span className="text-green-500/70 ml-1">({formatDuration(instance.running_duration_hours)})</span>
              )}
            </span>
          ) : (
            <span className="shrink-0 px-3 py-1 text-sm font-medium bg-slate-600/30 text-slate-400 rounded-full">
              Stopped
            </span>
          )}
        </div>

        {/* Row 2: Prompt */}
        <div className="flex items-center gap-2 text-sm text-slate-400 mb-2">
          <FileText className="w-4 h-4 text-slate-500 shrink-0" />
          <span className="text-blue-400 truncate">{instance.prompt_name || 'No prompt'}</span>
        </div>

        {/* Row 3: Config badges */}
        <div className="flex items-center gap-2 flex-wrap">
          {instance.timeframe && (
            <span className="px-2 py-1 text-xs bg-slate-700/50 text-slate-300 rounded flex items-center gap-1">
              <Clock className="w-3 h-3" /> {instance.timeframe}
            </span>
          )}
          <span className={`px-2 py-1 text-xs rounded font-medium ${
            instance.config.use_testnet ? 'bg-blue-600/20 text-blue-400' : 'bg-purple-600/20 text-purple-400'
          }`}>
            {instance.config.use_testnet ? 'TESTNET' : 'MAINNET'}
          </span>
          {instance.last_cycle_symbols && instance.last_cycle_symbols.length > 0 ? (
            <span
              className="px-2 py-1 text-xs bg-slate-700/50 text-slate-400 rounded cursor-help flex items-center gap-1"
              title={instance.last_cycle_symbols.join(', ')}
            >
              <Target className="w-3 h-3" /> {formatSymbols(instance.last_cycle_symbols)}
            </span>
          ) : (
            <span className="px-2 py-1 text-xs bg-slate-700/50 text-slate-500 rounded flex items-center gap-1 italic">
              <Target className="w-3 h-3" /> No recommendations for last cycle
            </span>
          )}
        </div>
      </div>

      {/* ═══════════════ SECTION 2: CONTROLS ═══════════════ */}
      <div className="px-4 py-3 bg-slate-900/30 border-b border-slate-700 flex items-center justify-between">
        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => handleAction('start', e)}
            disabled={actionLoading !== null || isRunning}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium flex items-center gap-1.5 transition disabled:opacity-40 ${
              instance.config.paper_trading
                ? 'bg-amber-600/20 text-amber-400 hover:bg-amber-600/40'
                : 'bg-green-600/20 text-green-400 hover:bg-green-600/40'
            }`}
          >
            {actionLoading === 'start' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Start
          </button>
          <button
            onClick={(e) => handleAction('stop', e)}
            disabled={actionLoading !== null}
            className="px-3 py-1.5 bg-slate-600/30 text-slate-300 hover:bg-slate-600/50 rounded-lg text-sm font-medium flex items-center gap-1.5 transition disabled:opacity-40"
          >
            {actionLoading === 'stop' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
            Stop
          </button>
          <button
            onClick={(e) => handleAction('kill', e)}
            disabled={actionLoading !== null}
            className="px-3 py-1.5 bg-red-600/20 text-red-400 hover:bg-red-600/40 rounded-lg text-sm font-medium flex items-center gap-1.5 transition disabled:opacity-40"
            title="Emergency Kill"
          >
            {actionLoading === 'kill' ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Skull className="w-4 h-4" />}
          </button>
        </div>

        {/* Mode Badge */}
        <span className={`px-3 py-1.5 text-sm font-bold rounded-lg ${
          instance.config.paper_trading
            ? 'bg-amber-600/30 text-amber-400 border border-amber-600/50'
            : 'bg-red-600/30 text-red-400 border border-red-600/50'
        }`}>
          {instance.config.paper_trading ? '🟡 DRY RUN' : '🔴 LIVE'}
        </span>
      </div>

      {/* ═══════════════ SECTION 3: PERFORMANCE STATS ═══════════════ */}
      <div className="border-b border-slate-700">
        {/* Stats Header */}
        <div className="grid grid-cols-5 bg-slate-900/50 px-3 py-2 text-[10px] text-slate-500 font-medium uppercase tracking-wide">
          <div></div>
          <div className="text-center">Trades</div>
          <div className="text-center">Win Rate</div>
          <div className="text-center">P&L</div>
          <div className="text-center">EV</div>
        </div>

        {/* Total Row */}
        <div className="grid grid-cols-5 px-3 py-2 items-center bg-slate-800/50">
          <div className="text-xs text-slate-400 font-medium">TOTAL</div>
          <div className="text-center text-lg font-bold text-white">{instance.total_trades}</div>
          <div className={`text-center text-lg font-bold ${instance.win_rate >= 50 ? 'text-green-400' : instance.win_rate > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
            {instance.win_count + instance.loss_count > 0 ? `${instance.win_rate.toFixed(0)}%` : '—'}
          </div>
          <div className={`text-center text-lg font-bold ${instance.total_pnl > 0 ? 'text-green-400' : instance.total_pnl < 0 ? 'text-red-400' : 'text-slate-400'}`}>
            {instance.total_pnl !== 0 ? `${instance.total_pnl > 0 ? '+' : ''}$${instance.total_pnl.toFixed(2)}` : '—'}
          </div>
          <div className={`text-center text-lg font-bold ${instance.expected_value > 0 ? 'text-green-400' : instance.expected_value < 0 ? 'text-red-400' : 'text-slate-400'}`}>
            {instance.win_count + instance.loss_count > 0 ? `${instance.expected_value > 0 ? '+' : ''}$${instance.expected_value.toFixed(2)}` : '—'}
          </div>
        </div>

        {/* Live Row */}
        <div className="grid grid-cols-5 px-3 py-1.5 items-center bg-green-900/10">
          <div className="text-xs text-green-400 font-medium flex items-center gap-1.5">
            <span className="w-2 h-2 bg-green-500 rounded-full"></span>
            LIVE
          </div>
          <div className="text-center text-xs text-green-400">
            {(instance.live_closed || 0) + (instance.live_open || 0)}
            <span className="text-green-600 ml-1">({instance.live_closed || 0}c /{instance.live_open || 0}o)</span>
          </div>
          <div className="text-center text-xs text-green-400">
            {liveClosedTotal > 0 ? `${instance.live_wins}W/${instance.live_losses}L` : '—'}
          </div>
          <div className={`text-center text-xs ${(instance.live_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {instance.live_pnl ? `${instance.live_pnl > 0 ? '+' : ''}$${instance.live_pnl.toFixed(2)}` : '—'}
          </div>
          <div className={`text-center text-xs ${(instance.live_ev || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {liveClosedTotal > 0 ? `${instance.live_ev > 0 ? '+' : ''}$${instance.live_ev.toFixed(2)}` : '—'}
          </div>
        </div>

        {/* Dry Row */}
        <div className="grid grid-cols-5 px-3 py-1.5 items-center bg-amber-900/10">
          <div className="text-xs text-amber-400 font-medium flex items-center gap-1.5">
            <span className="w-2 h-2 bg-amber-500 rounded-full"></span>
            DRY
          </div>
          <div className="text-center text-xs text-amber-400">
            {(instance.dry_closed || 0) + (instance.dry_open || 0)}
            <span className="text-amber-600 ml-1">({instance.dry_closed || 0}c /{instance.dry_open || 0}o)</span>
          </div>
          <div className="text-center text-xs text-amber-400">
            {dryClosedTotal > 0 ? `${instance.dry_wins}W/${instance.dry_losses}L` : '—'}
          </div>
          <div className={`text-center text-xs ${(instance.dry_pnl || 0) >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
            {instance.dry_pnl ? `${instance.dry_pnl > 0 ? '+' : ''}$${instance.dry_pnl.toFixed(2)}` : '—'}
          </div>
          <div className={`text-center text-xs ${(instance.dry_ev || 0) >= 0 ? 'text-amber-400' : 'text-red-400'}`}>
            {dryClosedTotal > 0 ? `${instance.dry_ev > 0 ? '+' : ''}$${instance.dry_ev.toFixed(2)}` : '—'}
          </div>
        </div>
      </div>

      {/* ═══════════════ SECTION 4: SIGNAL QUALITY ═══════════════ */}
      <div className="px-4 py-3 bg-slate-900/30 border-b border-slate-700">
        <div className="text-[10px] text-slate-500 font-medium uppercase tracking-wide mb-2">Signal Quality</div>
        <div className="flex items-center gap-6">
          <div className="text-sm">
            <span className="text-slate-500">Actionable:</span>{' '}
            <span className="text-white font-semibold">{instance.actionable_percent?.toFixed(0) || 0}%</span>
            <span className="text-slate-600 text-xs ml-1">({instance.actionable_count || 0}/{instance.total_recs || 0})</span>
          </div>
          <div className="text-sm">
            <span className="text-slate-500">Avg Conf:</span>{' '}
            <span className="text-white font-semibold">{instance.avg_confidence?.toFixed(2) || '—'}</span>
          </div>
          <div className="text-sm">
            <span className="text-slate-500">Avg R:R:</span>{' '}
            <span className="text-white font-semibold">{instance.avg_risk_reward ? `${instance.avg_risk_reward.toFixed(1)}:1` : '—'}</span>
          </div>
        </div>
      </div>

      {/* ═══════════════ SECTION 5: LAST CYCLE ═══════════════ */}
      {instance.latest_cycle && (
        <Link href={`/instances/${instance.id}`} className="block">
          <div className="px-4 py-2 bg-slate-900/50 border-b border-slate-700/50 flex items-center gap-4 text-xs text-slate-500 hover:bg-slate-700/30 transition">
            <Activity className="w-4 h-4" />
            <span className="font-medium">Last Cycle:</span>
            <span className="text-slate-400">{instance.latest_cycle.charts_captured} charts</span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-400">{instance.latest_cycle.recommendations_generated} recs</span>
            <span className="text-slate-600">•</span>
            <span className="text-slate-400">{instance.latest_cycle.trades_executed} trades</span>
            <ChevronRight className="w-4 h-4 ml-auto text-slate-600 group-hover:text-slate-400 transition" />
          </div>
        </Link>
      )}

      {/* ═══════════════ SECTION 6: RECENT LOGS ═══════════════ */}
      <RecentLogsSection instance={instance} />
    </div>
  )
}


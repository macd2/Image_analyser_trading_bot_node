'use client'

import { useState, useEffect, useMemo, useRef } from 'react'
import { Activity, Clock, Maximize2, AlertTriangle, CheckCircle, RefreshCw, X } from 'lucide-react'
import { LoadingState, ErrorState } from '@/components/shared'
import TradeChartModal from '@/components/shared/TradeChartModal'
import StatsBar, { StatsScope } from '@/components/StatsBar'
import { useBotState } from '@/lib/context/BotStateContext'
import { useRealtime } from '@/hooks/useRealtime'
import VncLoginModal from '@/components/VncLoginModal'

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

interface OverviewTabProps {
  instanceId: string
}

interface BotStatus {
  running: boolean
  wallet: { balance_usdt: number; available_usdt: number; equity_usdt: number }
  positions: Array<{ symbol: string; side: string; size: string; entryPrice: string; unrealisedPnl: string }>
  slots: { used: number; max: number }
  last_cycle: { timeframe: string; boundary_time: string; status: string } | null
}

interface Trade {
  id: string
  symbol: string
  side: 'Buy' | 'Sell'
  entry_price: number
  stop_loss: number | null
  take_profit: number | null
  exit_price: number | null
  status: string
  pnl: number | null
  submitted_at: string | null
  filled_at: string | null
  closed_at: string | null
  created_at: string
  timeframe: string | null
}

export function OverviewTab({ instanceId }: OverviewTabProps) {
  // Use shared context for logs
  const { logs, addLog, setLogs } = useBotState()

  // Connect to Socket.IO for real-time updates
  const { socket } = useRealtime()

  const [status, setStatus] = useState<BotStatus | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null)
  const [statsScope, setStatsScope] = useState<StatsScope>('instance')
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logFilter, setLogFilter] = useState<LogLevel>('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [loginState, setLoginState] = useState<{
    state: 'idle' | 'waiting_for_login' | 'login_confirmed' | 'browser_opened'
    message: string | null
    browser_opened: boolean
    requires_action: boolean
    can_confirm: boolean
  }>({ state: 'idle', message: null, browser_opened: false, requires_action: false, can_confirm: false })
  const [loginActionLoading, setLoginActionLoading] = useState(false)
  const [vncModalOpen, setVncModalOpen] = useState(false)

  // Track logs length in ref to avoid stale closure in fetchData
  const logsLengthRef = useRef(logs.length)
  useEffect(() => { logsLengthRef.current = logs.length }, [logs.length])

  // Refs for auto-scroll
  const logsPreviewRef = useRef<HTMLDivElement>(null)
  const logsModalRef = useRef<HTMLDivElement>(null)

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

  // Auto-scroll effect for logs
  useEffect(() => {
    if (autoScroll) {
      if (logsPreviewRef.current) {
        logsPreviewRef.current.scrollTop = logsPreviewRef.current.scrollHeight
      }
      if (logsModalRef.current) {
        logsModalRef.current.scrollTop = logsModalRef.current.scrollHeight
      }
    }
  }, [logs, autoScroll, filteredLogs])

  const fetchData = async () => {
    try {
      const [statusRes, tradesRes, controlRes, loginRes] = await Promise.all([
        fetch('/api/bot/status'),
        fetch(`/api/bot/trades?limit=20&instance_id=${instanceId}`),
        fetch('/api/bot/control'),
        fetch('/api/bot/login')
      ])

      if (!statusRes.ok || !tradesRes.ok) {
        throw new Error('Failed to fetch data')
      }

      const statusData = await statusRes.json()
      const tradesData = await tradesRes.json()
      const controlData = controlRes.ok ? await controlRes.json() : null
      const loginData = loginRes.ok ? await loginRes.json() : null

      setStatus(statusData)
      setTrades(tradesData.trades || [])

      // Update login state
      if (loginData) {
        setLoginState(loginData)
      }

      // Always sync logs from bot control API
      // This ensures logs are updated even if socket events were missed
      if (controlData?.logs && controlData.logs.length > 0) {
        // If API has more logs than we have, use API logs as the source of truth
        // Use ref to avoid stale closure issue with interval
        if (controlData.logs.length > logsLengthRef.current) {
          setLogs(controlData.logs)
        }
      }

      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
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
        setLoginState(prev => ({ ...prev, state: 'login_confirmed', message: 'Verifying login...' }))
      }
      // Refresh data after a short delay
      setTimeout(() => fetchData(), 1000)
    } catch (err) {
      console.error('Failed to confirm login:', err)
    } finally {
      setLoginActionLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    // Poll every 2 seconds for faster log updates
    const interval = setInterval(fetchData, 2000)
    return () => clearInterval(interval)
  }, [instanceId])

  // Listen for live logs via Socket.IO
  useEffect(() => {
    if (!socket) return

    const handleLog = (data: { log: string; instanceId?: string; timestamp: number }) => {
      // Only add logs for this instance (or all logs if no instanceId specified)
      if (!data.instanceId || data.instanceId === instanceId) {
        addLog(data.log)
      }
    }

    socket.on('bot_log', handleLog)

    return () => {
      socket.off('bot_log', handleLog)
    }
  }, [socket, instanceId, addLog])

  if (loading) return <LoadingState text="Loading overview..." />
  if (error) return <ErrorState message={error} onRetry={fetchData} />

  const unrealizedPnl = status?.positions?.reduce((sum, p) => sum + parseFloat(p.unrealisedPnl || '0'), 0) || 0
  const positionCount = status?.positions?.length || 0

  return (
    <div className="p-4 space-y-4">
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
                setLoginState({ state: 'idle', message: null, browser_opened: false, requires_action: false, can_confirm: false })
              }}
              className="p-2 rounded hover:bg-amber-800/50 transition"
              title="Dismiss"
            >
              <X className="w-4 h-4 text-amber-400" />
            </button>
          </div>
        </div>
      )}

      {/* Row 1: Performance Stats + Account Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Performance Stats - spans 3 cols */}
        <div className="lg:col-span-3 bg-slate-800/50 rounded-lg p-3">
          <StatsBar
            scope={statsScope}
            scopeId={instanceId}
            onScopeChange={setStatsScope}
            showScopeSelector={true}
          />
        </div>
        {/* Account Summary - compact */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="text-xs text-slate-400 mb-1">Account</div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-slate-500">Balance:</span>
              <span className="text-white ml-1 font-mono">${status?.wallet?.balance_usdt?.toFixed(0) || '0'}</span>
            </div>
            <div>
              <span className="text-slate-500">Equity:</span>
              <span className="text-white ml-1 font-mono">${status?.wallet?.equity_usdt?.toFixed(0) || '0'}</span>
            </div>
            <div>
              <span className="text-slate-500">Available:</span>
              <span className="text-green-400 ml-1 font-mono">${status?.wallet?.available_usdt?.toFixed(0) || '0'}</span>
            </div>
            <div>
              <span className="text-slate-500">Slots:</span>
              <span className="text-white ml-1">{status?.slots?.used || 0}/{status?.slots?.max || 0}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Open Positions (PRIORITY) + Bot Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Open Positions - 2/3 width */}
        <div className="lg:col-span-2 bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" />
              Open Positions
              {positionCount > 0 && (
                <span className="px-1.5 py-0.5 text-xs bg-blue-600/30 text-blue-400 rounded">{positionCount}</span>
              )}
            </h3>
            {unrealizedPnl !== 0 && (
              <span className={`text-sm font-bold ${unrealizedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                Unrealized: {unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(2)}
              </span>
            )}
          </div>
          {positionCount > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-xs border-b border-slate-700">
                    <th className="text-left py-1.5 font-medium">Symbol</th>
                    <th className="text-left py-1.5 font-medium">Side</th>
                    <th className="text-right py-1.5 font-medium">Size</th>
                    <th className="text-right py-1.5 font-medium">Entry</th>
                    <th className="text-right py-1.5 font-medium">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {status?.positions?.map((pos, idx) => (
                    <tr key={idx} className="border-b border-slate-700/50 hover:bg-slate-700/20">
                      <td className="py-1.5 font-mono font-bold text-white">{pos.symbol}</td>
                      <td className="py-1.5">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${pos.side === 'Buy' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                          {pos.side === 'Buy' ? 'LONG' : 'SHORT'}
                        </span>
                      </td>
                      <td className="py-1.5 text-right text-slate-300 font-mono">{pos.size}</td>
                      <td className="py-1.5 text-right text-slate-300 font-mono">${parseFloat(pos.entryPrice).toFixed(2)}</td>
                      <td className={`py-1.5 text-right font-bold font-mono ${parseFloat(pos.unrealisedPnl) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {parseFloat(pos.unrealisedPnl) >= 0 ? '+' : ''}${parseFloat(pos.unrealisedPnl).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-slate-500 text-sm py-4 text-center border border-dashed border-slate-700 rounded">
              No open positions
            </div>
          )}
        </div>

        {/* Bot Status + Last Cycle */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-3">
          <div>
            <div className="flex items-center gap-2 text-slate-400 mb-2">
              <Clock size={14} />
              <span className="text-xs font-medium">Last Cycle</span>
            </div>
            {status?.last_cycle ? (
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Timeframe:</span>
                  <span className="text-white font-mono">{status.last_cycle.timeframe}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Time:</span>
                  <span className="text-white font-mono">{status.last_cycle.boundary_time}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Status:</span>
                  <span className={status.last_cycle.status === 'completed' ? 'text-green-400' : 'text-yellow-400'}>
                    {status.last_cycle.status}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-slate-500 text-xs">Start the bot to begin trading</div>
            )}
          </div>

          {/* Bot Logs Preview - Compact */}
          <div className="border-t border-slate-700 pt-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-slate-400">Bot Output</span>
              <div className="flex items-center gap-1.5">
                {logCounts.error > 0 && (
                  <span className="px-1 py-0.5 text-[10px] bg-red-900/50 text-red-400 rounded">{logCounts.error}</span>
                )}
                {logCounts.warning > 0 && (
                  <span className="px-1 py-0.5 text-[10px] bg-amber-900/50 text-amber-400 rounded">{logCounts.warning}</span>
                )}
                <span className="text-[10px] text-slate-600">{parsedLogs.length}</span>
                <button onClick={() => setShowLogsModal(true)} className="text-slate-500 hover:text-white">
                  <Maximize2 size={12} />
                </button>
              </div>
            </div>
            <div
              ref={logsPreviewRef}
              className="bg-slate-900 rounded p-1.5 h-24 overflow-y-auto font-mono text-[10px] scroll-smooth"
            >
              {parsedLogs.length > 0 ? (
                parsedLogs.slice(-15).map((log, idx) => (
                  <div key={idx} className={`py-0.5 whitespace-nowrap ${getLogColor(log.level)}`}>{log.raw}</div>
                ))
              ) : (
                <div className="text-slate-600 italic">Waiting for output...</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Row 3: Recent Trades - Full Width */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
        <h3 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
          <Clock className="w-4 h-4 text-slate-400" /> Recent Trades
          <span className="text-xs text-slate-500 font-normal">({trades.filter(t => t.status !== 'rejected').length})</span>
        </h3>
        {trades.filter(t => t.status !== 'rejected').length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-xs border-b border-slate-700">
                  <th className="text-left py-1.5 font-medium">Symbol</th>
                  <th className="text-left py-1.5 font-medium">Side</th>
                  <th className="text-right py-1.5 font-medium">Entry</th>
                  <th className="text-right py-1.5 font-medium">P&L</th>
                  <th className="text-right py-1.5 font-medium">Status</th>
                  <th className="text-right py-1.5 font-medium">Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.filter(t => t.status !== 'rejected').slice(0, 8).map((trade) => (
                  <tr
                    key={trade.id}
                    className="border-b border-slate-700/50 hover:bg-slate-700/20 cursor-pointer"
                    onClick={() => setSelectedTrade(trade)}
                  >
                    <td className="py-1.5 font-mono font-bold text-white">{trade.symbol}</td>
                    <td className="py-1.5">
                      <span className={`text-xs ${trade.side === 'Buy' ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.side === 'Buy' ? '↑ LONG' : '↓ SHORT'}
                      </span>
                    </td>
                    <td className="py-1.5 text-right text-slate-300 font-mono">${trade.entry_price.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono">
                      {trade.pnl !== null ? (
                        <span className={trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                          {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                        </span>
                      ) : <span className="text-slate-500">-</span>}
                    </td>
                    <td className="py-1.5 text-right">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        trade.status === 'filled' || trade.status === 'paper_trade' ? 'bg-green-900/50 text-green-400' :
                        trade.status === 'pending' ? 'bg-yellow-900/50 text-yellow-400' :
                        trade.status === 'closed' ? 'bg-slate-600 text-slate-300' :
                        'bg-slate-700 text-slate-400'
                      }`}>
                        {trade.status === 'paper_trade' ? 'PAPER' : trade.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-1.5 text-right text-xs text-slate-500">
                      {trade.created_at ? new Date(trade.created_at).toLocaleTimeString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-slate-500 text-sm py-4 text-center border border-dashed border-slate-700 rounded">
            No trades yet
          </div>
        )}
      </div>

      {/* Logs Modal */}
      {showLogsModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl border border-slate-700">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center gap-4">
                <h2 className="text-lg font-bold text-white">Bot Logs</h2>
                <span className="text-xs text-slate-400">{logs.length} total entries</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1 bg-slate-900 rounded-lg p-1">
                  {(['all', 'error', 'warning', 'info', 'debug'] as LogLevel[]).map((level) => (
                    <button
                      key={level}
                      onClick={() => setLogFilter(level)}
                      className={`px-3 py-1.5 text-xs rounded transition ${
                        logFilter === level ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                      {level !== 'all' && logCounts[level] > 0 && (
                        <span className={`ml-1 ${getLogColor(level)}`}>({logCounts[level]})</span>
                      )}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setAutoScroll(!autoScroll)}
                  className={`px-2 py-1 text-xs rounded transition ${autoScroll ? 'bg-green-900/50 text-green-400' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  {autoScroll ? '⏬ Auto' : '⏸ Paused'}
                </button>
                <button onClick={() => setLogs([])} className="text-xs text-slate-500 hover:text-slate-300">Clear</button>
                <button onClick={() => setShowLogsModal(false)} className="p-1.5 rounded hover:bg-slate-700 transition text-slate-400 hover:text-white">✕</button>
              </div>
            </div>
            <div
              ref={logsModalRef}
              className="flex-1 overflow-y-auto p-4 bg-slate-900 font-mono text-xs scroll-smooth"
            >
              {filteredLogs.length > 0 ? (
                filteredLogs.map((log, idx) => (
                  <div key={idx} className={`py-0.5 px-1 ${getLogColor(log.level)} ${getLogBgColor(log.level)}`}>
                    {log.raw}
                  </div>
                ))
              ) : (
                <div className="text-slate-500 italic text-center py-8">No logs matching filter</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Trade Chart Modal - Using shared component */}
      <TradeChartModal
        isOpen={selectedTrade !== null}
        onClose={() => setSelectedTrade(null)}
        trade={selectedTrade}
        mode={selectedTrade?.status === 'closed' ? 'historical' : 'live'}
      />

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


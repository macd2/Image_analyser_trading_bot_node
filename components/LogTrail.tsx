'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Activity, RefreshCw, Clock, TrendingUp, AlertCircle, CheckCircle, Loader2,
  ChevronDown, ChevronRight, Search, Zap, Package, Play, Square, Eye, Image, Server, Copy, Check
} from 'lucide-react'

// ============================================================
// TYPES
// ============================================================

interface Execution {
  id: string
  trade_id: string
  symbol: string
  exec_type: string | null
  exec_qty: number
  exec_price: number
  exec_pnl: number | null
  exec_time: string
}

interface Trade {
  id: string
  recommendation_id: string
  symbol: string
  side: string
  entry_price: number
  exit_price: number | null
  quantity: number
  pnl: number | null
  pnl_percent: number | null
  status: string
  rejection_reason: string | null
  created_at: string
  executions: Execution[]
}

interface Recommendation {
  id: string
  cycle_id: string
  symbol: string
  recommendation: string
  confidence: number
  entry_price: number | null
  stop_loss: number | null
  take_profit: number | null
  risk_reward: number | null
  chart_path: string | null
  raw_response: string | null
  model_name: string | null
  prompt_name: string | null
  created_at: string
  trades: Trade[]
}

interface Cycle {
  id: string
  run_id: string | null
  timeframe: string
  cycle_number: number
  boundary_time: string
  status: string
  charts_captured: number
  analyses_completed: number
  recommendations_generated: number
  trades_executed: number
  started_at: string
  completed_at: string | null
  recommendations: Recommendation[]
}

interface Run {
  id: string
  instance_id: string | null
  started_at: string
  ended_at: string | null
  status: 'running' | 'stopped' | 'crashed' | 'completed'
  stop_reason: string | null
  timeframe: string | null
  paper_trading: number
  min_confidence: number | null
  max_leverage: number | null
  total_cycles: number
  total_recommendations: number
  total_trades: number
  total_pnl: number
  win_count: number
  loss_count: number
  cycles: Cycle[]
}

interface Instance {
  id: string
  name: string
  prompt_name: string | null
  timeframe: string | null
  is_active: number
  runs: Run[]
  total_cycles: number
  total_recommendations: number
  total_trades: number
  total_pnl: number
  win_count: number
  loss_count: number
}

interface Stats {
  runs: number
  cycles: number
  recommendations: number
  trades: number
  executions: number
  winRate: number
  totalPnl: number
}

// ============================================================
// MAIN COMPONENT
// ============================================================

export default function LogTrail() {
  const [instances, setInstances] = useState<Instance[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [expandedInstances, setExpandedInstances] = useState<Set<string>>(new Set())
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set())
  const [expandedCycles, setExpandedCycles] = useState<Set<string>>(new Set())
  const [expandedRecs, setExpandedRecs] = useState<Set<string>>(new Set())
  const [expandedTrades, setExpandedTrades] = useState<Set<string>>(new Set())
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedRec, setSelectedRec] = useState<Recommendation | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopyId = useCallback((id: string) => {
    navigator.clipboard.writeText(id)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }, [])

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch('/api/bot/logs?type=hierarchy&limit=20')
      const data = await res.json()
      if (data.data) setInstances(data.data)
      if (data.stats) setStats(data.stats)
    } catch (err) {
      console.error('Failed to fetch logs:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    if (autoRefresh) {
      const interval = setInterval(fetchData, 10000)
      return () => clearInterval(interval)
    }
    return undefined
  }, [autoRefresh, fetchData])

  const toggleInstance = (id: string) => {
    setExpandedInstances(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleRun = (id: string) => {
    setExpandedRuns(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleCycle = (id: string) => {
    setExpandedCycles(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleRec = (id: string) => {
    setExpandedRecs(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleTrade = (id: string) => {
    setExpandedTrades(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // Filter instances by search term
  const filteredInstances = instances.filter(instance => {
    if (!searchTerm) return true
    const s = searchTerm.toLowerCase()
    // Search in instance name or ID
    if (instance.name.toLowerCase().includes(s)) return true
    if (instance.id.toLowerCase().includes(s)) return true
    // Search in runs/cycles/recommendations/trades
    return instance.runs.some(run =>
      run.id.toLowerCase().includes(s) ||
      run.cycles.some(c =>
        c.recommendations.some(r =>
          r.symbol.toLowerCase().includes(s) ||
          r.recommendation.toLowerCase().includes(s)
        )
      )
    )
  })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Activity className="w-6 h-6 text-blue-400" />
            Log Trail
          </h2>
          <p className="text-slate-400 text-sm">Complete audit trail grouped by instance → run → cycle</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-blue-500"
            />
            Auto-refresh
          </label>
          <button
            onClick={fetchData}
            className="p-2 rounded bg-slate-700 hover:bg-slate-600 transition"
          >
            <RefreshCw className={`w-4 h-4 text-slate-300 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="grid grid-cols-7 gap-3">
          <StatBox label="Instances" value={filteredInstances.length} color="teal" />
          <StatBox label="Cycles" value={stats.cycles} color="blue" />
          <StatBox label="Recommendations" value={stats.recommendations} color="purple" />
          <StatBox label="Trades" value={stats.trades} color="green" />
          <StatBox label="Executions" value={stats.executions} color="orange" />
          <StatBox label="Win Rate" value={`${(stats.winRate * 100).toFixed(1)}%`} color="cyan" />
          <StatBox
            label="Total P&L"
            value={`$${stats.totalPnl.toFixed(2)}`}
            color={stats.totalPnl >= 0 ? 'green' : 'red'}
          />
        </div>
      )}

      {/* Search */}
      <div className="flex items-center gap-3 bg-slate-800/50 rounded-lg p-3">
        <Search className="w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="Search by instance name, run ID, symbol, or recommendation..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="flex-1 bg-transparent text-white placeholder-slate-400 focus:outline-none"
        />
      </div>

      {/* Hierarchical View - Starting with Instances (Level 0) */}
      <div className="space-y-3 max-h-[700px] overflow-y-auto pr-2">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3">
            <Loader2 size={32} className="animate-spin text-blue-400" />
            <span className="text-slate-400 text-sm">Loading instances...</span>
          </div>
        ) : filteredInstances.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>No instances found</p>
          </div>
        ) : (
          filteredInstances.map(instance => (
            <InstanceCard
              key={instance.id}
              instance={instance}
              expanded={expandedInstances.has(instance.id)}
              onToggle={() => toggleInstance(instance.id)}
              expandedRuns={expandedRuns}
              toggleRun={toggleRun}
              expandedCycles={expandedCycles}
              toggleCycle={toggleCycle}
              expandedRecs={expandedRecs}
              toggleRec={toggleRec}
              expandedTrades={expandedTrades}
              toggleTrade={toggleTrade}
              onViewRec={setSelectedRec}
            />
          ))
        )}
      </div>

      {/* Recommendation Detail Modal */}
      {selectedRec && (
        <RecommendationModal
          rec={selectedRec}
          onClose={() => setSelectedRec(null)}
          copiedId={copiedId}
          onCopyId={handleCopyId}
        />
      )}
    </div>
  )
}

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function formatTime(ts: string) {
  const d = new Date(ts)
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

function formatDuration(start: string, end: string | null) {
  if (!end) return 'Running...'
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const mins = Math.floor(ms / 60000)
  const hours = Math.floor(mins / 60)
  if (hours > 0) return `${hours}h ${mins % 60}m`
  return `${mins}m`
}

// ============================================================
// STAT BOX
// ============================================================

function StatBox({ label, value, color }: { label: string; value: string | number; color: string }) {
  const colorClasses: Record<string, string> = {
    indigo: 'text-indigo-400',
    blue: 'text-blue-400',
    purple: 'text-purple-400',
    green: 'text-green-400',
    amber: 'text-amber-400',
    cyan: 'text-cyan-400',
    red: 'text-red-400',
    teal: 'text-teal-400',
  }
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 text-center">
      <div className={`text-lg font-bold ${colorClasses[color] || 'text-white'}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  )
}

// ============================================================
// INSTANCE CARD (Level 0)
// ============================================================

interface InstanceCardProps {
  instance: Instance
  expanded: boolean
  onToggle: () => void
  expandedRuns: Set<string>
  toggleRun: (id: string) => void
  expandedCycles: Set<string>
  toggleCycle: (id: string) => void
  expandedRecs: Set<string>
  toggleRec: (id: string) => void
  expandedTrades: Set<string>
  toggleTrade: (id: string) => void
  onViewRec: (rec: Recommendation) => void
}

function InstanceCard({ instance, expanded, onToggle, expandedRuns, toggleRun, expandedCycles, toggleCycle, expandedRecs, toggleRec, expandedTrades, toggleTrade, onViewRec }: InstanceCardProps) {
  const hasRunningRun = instance.runs.some(r => r.status === 'running')
  const winRate = (instance.win_count + instance.loss_count) > 0
    ? (instance.win_count / (instance.win_count + instance.loss_count) * 100).toFixed(0)
    : '0'

  return (
    <div className="border border-teal-500/40 rounded-lg overflow-hidden bg-slate-900/40">
      {/* Instance Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-4 hover:bg-slate-800/30 transition text-left"
      >
        <Server className="w-5 h-5 text-teal-400" />
        <span className="text-teal-300 font-bold">{instance.name}</span>
        <span className="font-mono text-xs text-slate-500">{instance.id.slice(0, 8)}...</span>
        {hasRunningRun && (
          <span className="px-2 py-0.5 text-[10px] font-medium uppercase rounded border bg-green-500/20 text-green-400 border-green-500/30">
            <Play className="w-3 h-3 inline mr-1" />
            Active
          </span>
        )}
        {instance.timeframe && <span className="text-xs text-slate-500">{instance.timeframe}</span>}
        <span className="flex-1" />
        <div className="flex items-center gap-4 text-xs">
          <span className="text-indigo-400">{instance.runs.length} runs</span>
          <span className="text-blue-400">{instance.total_cycles} cycles</span>
          <span className="text-purple-400">{instance.total_recommendations} recs</span>
          <span className="text-green-400">{instance.total_trades} trades</span>
          <span className="text-cyan-400">{winRate}% win</span>
          <span className={instance.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
            ${instance.total_pnl.toFixed(2)}
          </span>
        </div>
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </button>

      {/* Runs (Level 1) */}
      {expanded && (
        <div className="border-t border-slate-700/50 pl-4">
          {instance.runs.length === 0 ? (
            <div className="p-4 text-slate-500 text-sm">No runs yet</div>
          ) : (
            instance.runs.map(run => (
              <RunCard
                key={run.id}
                run={run}
                expanded={expandedRuns.has(run.id)}
                onToggle={() => toggleRun(run.id)}
                expandedCycles={expandedCycles}
                toggleCycle={toggleCycle}
                expandedRecs={expandedRecs}
                toggleRec={toggleRec}
                expandedTrades={expandedTrades}
                toggleTrade={toggleTrade}
                onViewRec={onViewRec}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// RUN CARD (Level 1)
// ============================================================

interface RunCardProps {
  run: Run
  expanded: boolean
  onToggle: () => void
  expandedCycles: Set<string>
  toggleCycle: (id: string) => void
  expandedRecs: Set<string>
  toggleRec: (id: string) => void
  expandedTrades: Set<string>
  toggleTrade: (id: string) => void
  onViewRec: (rec: Recommendation) => void
}

function RunCard({ run, expanded, onToggle, expandedCycles, toggleCycle, expandedRecs, toggleRec, expandedTrades, toggleTrade, onViewRec }: RunCardProps) {
  const statusColors: Record<string, string> = {
    running: 'bg-green-500/20 text-green-400 border-green-500/30',
    stopped: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
    crashed: 'bg-red-500/20 text-red-400 border-red-500/30',
    completed: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  }

  // Calculate selected/rejected/executed counts from all cycles
  const allTrades = run.cycles.flatMap(cycle => cycle.recommendations.flatMap(rec => rec.trades))
  const selectedCount = allTrades.length // Total trade attempts (selected signals)
  const rejectedCount = allTrades.filter(t => t.status === 'rejected').length
  const executedCount = allTrades.filter(t => t.status !== 'rejected' && t.status !== 'cancelled' && t.status !== 'error').length

  const winRate = (run.win_count + run.loss_count) > 0
    ? (run.win_count / (run.win_count + run.loss_count) * 100).toFixed(0)
    : '0'

  return (
    <div className="border-b border-indigo-500/20 bg-slate-900/20">
      {/* Run Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-3 hover:bg-slate-800/30 transition text-left"
      >
        <Package className="w-4 h-4 text-indigo-400" />
        <span className="font-mono text-indigo-300 text-sm">{run.id.slice(0, 12)}...</span>
        <span className={`px-2 py-0.5 text-[10px] font-medium uppercase rounded border ${statusColors[run.status]}`}>
          {run.status === 'running' && <Play className="w-3 h-3 inline mr-1" />}
          {run.status === 'stopped' && <Square className="w-3 h-3 inline mr-1" />}
          {run.status}
        </span>
        <span className="text-xs text-slate-500">
          {run.timeframe} • {run.paper_trading ? 'Paper' : 'Live'}
        </span>
        <span className="flex-1" />
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-400">{run.total_cycles} cycles</span>
          <span className="text-purple-400">{run.total_recommendations} recs</span>
          <span title={`${selectedCount} selected / ${rejectedCount} rejected / ${executedCount} executed`}>
            <span className="text-amber-400">{selectedCount}</span>
            <span className="text-slate-500">/</span>
            <span className="text-red-400">{rejectedCount}</span>
            <span className="text-slate-500">/</span>
            <span className="text-green-400">{executedCount}</span>
          </span>
          <span className="text-cyan-400">{winRate}%</span>
          <span className={run.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
            ${run.total_pnl.toFixed(2)}
          </span>
        </div>
        <span className="text-xs text-slate-500">{formatTime(run.started_at)}</span>
        <span className="text-xs text-slate-600">{formatDuration(run.started_at, run.ended_at)}</span>
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </button>

      {/* Cycles */}
      {expanded && (
        <div className="border-t border-slate-700/50 pl-6">
          {run.cycles.length === 0 ? (
            <div className="p-4 text-slate-500 text-sm">No cycles yet</div>
          ) : (
            run.cycles.map(cycle => (
              <CycleCard
                key={cycle.id}
                cycle={cycle}
                expanded={expandedCycles.has(cycle.id)}
                onToggle={() => toggleCycle(cycle.id)}
                expandedRecs={expandedRecs}
                toggleRec={toggleRec}
                expandedTrades={expandedTrades}
                toggleTrade={toggleTrade}
                onViewRec={onViewRec}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// CYCLE CARD
// ============================================================

interface CycleCardProps {
  cycle: Cycle
  expanded: boolean
  onToggle: () => void
  expandedRecs: Set<string>
  toggleRec: (id: string) => void
  expandedTrades: Set<string>
  toggleTrade: (id: string) => void
  onViewRec: (rec: Recommendation) => void
}

function CycleCard({ cycle, expanded, onToggle, expandedRecs, toggleRec, expandedTrades, toggleTrade, onViewRec }: CycleCardProps) {
  const statusColor = cycle.status === 'completed' ? 'text-green-400' : cycle.status === 'failed' ? 'text-red-400' : 'text-amber-400'

  // Calculate actual executed vs rejected trades
  const allTrades = cycle.recommendations.flatMap(rec => rec.trades)
  const selectedCount = allTrades.length // Total trade attempts (selected signals)
  const rejectedCount = allTrades.filter(t => t.status === 'rejected').length
  const executedCount = allTrades.filter(t => t.status !== 'rejected' && t.status !== 'cancelled' && t.status !== 'error').length

  return (
    <div className="border-b border-slate-800/50">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-3 hover:bg-slate-800/20 transition text-left"
      >
        <Clock className="w-4 h-4 text-blue-400" />
        <span className="text-blue-300 font-medium">Cycle #{cycle.cycle_number}</span>
        <span className={`text-xs ${statusColor}`}>{cycle.status}</span>
        <span className="text-xs text-slate-500">{cycle.timeframe}</span>
        <span className="flex-1" />
        <div className="flex items-center gap-3 text-xs">
          <span className="text-slate-400">{cycle.charts_captured} charts</span>
          <span className="text-purple-400">{cycle.recommendations_generated} recs</span>
          <span className="text-amber-400" title="Signals selected for execution">{selectedCount} selected</span>
          <span className="text-red-400" title="Rejected trades">{rejectedCount} rejected</span>
          <span className="text-green-400" title="Successfully executed trades">{executedCount} executed</span>
        </div>
        <span className="text-xs text-slate-500">{formatTime(cycle.started_at)}</span>
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </button>

      {/* Recommendations */}
      {expanded && (
        <div className="pl-6 bg-slate-900/20">
          {cycle.recommendations.length === 0 ? (
            <div className="p-3 text-slate-500 text-sm">No recommendations</div>
          ) : (
            cycle.recommendations.map(rec => (
              <RecommendationCard
                key={rec.id}
                rec={rec}
                expanded={expandedRecs.has(rec.id)}
                onToggle={() => toggleRec(rec.id)}
                expandedTrades={expandedTrades}
                toggleTrade={toggleTrade}
                onView={() => onViewRec(rec)}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// RECOMMENDATION CARD
// ============================================================

interface RecommendationCardProps {
  rec: Recommendation
  expanded: boolean
  onToggle: () => void
  expandedTrades: Set<string>
  toggleTrade: (id: string) => void
  onView: () => void
}

function RecommendationCard({ rec, expanded, onToggle, expandedTrades, toggleTrade, onView }: RecommendationCardProps) {
  const recColor = rec.recommendation.toUpperCase() === 'BUY' || rec.recommendation.toUpperCase() === 'LONG'
    ? 'text-green-400'
    : rec.recommendation.toUpperCase() === 'SELL' || rec.recommendation.toUpperCase() === 'SHORT'
      ? 'text-red-400'
      : 'text-slate-400'

  // Check if this recommendation was selected for execution
  const wasSelected = rec.trades.length > 0
  const executedTrades = rec.trades.filter(t => t.status !== 'rejected' && t.status !== 'cancelled' && t.status !== 'error')
  const rejectedTrades = rec.trades.filter(t => t.status === 'rejected')
  const rejectionReason = rejectedTrades.length > 0 ? rejectedTrades[0].rejection_reason : null

  return (
    <div className="border-b border-slate-800/30">
      <div className="flex items-center gap-3 p-3 hover:bg-slate-800/10 transition">
        <button onClick={onToggle} className="flex items-center gap-3 flex-1 text-left">
          <TrendingUp className="w-4 h-4 text-purple-400" />
          <span className="text-white font-medium">{rec.symbol}</span>
          <span className={`font-medium ${recColor}`}>{rec.recommendation}</span>
          <span className="text-xs text-slate-400">{(rec.confidence * 100).toFixed(0)}% conf</span>
          {rec.risk_reward && <span className="text-xs text-cyan-400">RR: {rec.risk_reward.toFixed(2)}</span>}
          <span className="flex-1" />

          {/* Selection status - show rejection and execution indicators */}
          {!wasSelected && (
            <span className="text-xs text-slate-500" title="Signal not selected for execution">Not selected</span>
          )}
          {rejectedTrades.length > 0 && (
            <span className="text-xs text-red-400" title={rejectionReason || 'Rejected'}>✗ Rejected</span>
          )}
          {executedTrades.length > 0 && (
            <span className="text-xs text-green-400" title="Successfully executed">✓ Executed</span>
          )}

          <span className="text-xs text-slate-500">{formatTime(rec.created_at)}</span>
          {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onView(); }}
          className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 transition"
          title="View full details"
        >
          <Eye className="w-3.5 h-3.5 text-slate-300" />
        </button>
      </div>

      {/* Trades */}
      {expanded && (
        <div className="pl-6 bg-slate-900/10">
          {rec.trades.length === 0 ? (
            <div className="p-3 text-slate-500 text-sm">Signal not selected for execution</div>
          ) : (
            <>
              {rejectedTrades.length > 0 && (
                <div className="p-3 bg-red-500/10 border-l-2 border-red-500 text-sm">
                  <div className="flex items-center gap-2 text-red-400 font-medium mb-1">
                    <AlertCircle className="w-4 h-4" />
                    <span>Trade Rejected</span>
                  </div>
                  <div className="text-slate-300 text-xs">{rejectionReason || 'No reason provided'}</div>
                </div>
              )}
              {executedTrades.map(trade => (
                <TradeCard
                  key={trade.id}
                  trade={trade}
                  expanded={expandedTrades.has(trade.id)}
                  onToggle={() => toggleTrade(trade.id)}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================
// TRADE CARD
// ============================================================

interface TradeCardProps {
  trade: Trade
  expanded: boolean
  onToggle: () => void
}

function TradeCard({ trade, expanded, onToggle }: TradeCardProps) {
  const sideColor = trade.side === 'Buy' ? 'text-green-400' : 'text-red-400'
  const pnlColor = (trade.pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="border-b border-slate-800/20">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-2 hover:bg-slate-800/10 transition text-left"
      >
        <Zap className="w-4 h-4 text-green-400" />
        <span className={`font-medium ${sideColor}`}>{trade.side}</span>
        <span className="text-xs text-slate-400">@ {trade.entry_price}</span>
        {trade.exit_price && <span className="text-xs text-slate-400">→ {trade.exit_price}</span>}
        <span className="text-xs text-slate-500">{trade.status}</span>
        <span className="flex-1" />
        {trade.pnl !== null && (
          <span className={`text-xs font-medium ${pnlColor}`}>
            ${trade.pnl.toFixed(2)} ({trade.pnl_percent?.toFixed(2)}%)
          </span>
        )}
        {trade.executions.length > 0 && (
          <span className="text-xs text-amber-400">{trade.executions.length} exec</span>
        )}
        {expanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
      </button>

      {/* Executions */}
      {expanded && trade.executions.length > 0 && (
        <div className="pl-6 bg-slate-900/5">
          {trade.executions.map(exec => (
            <div key={exec.id} className="flex items-center gap-3 p-2 text-xs border-b border-slate-800/10">
              <CheckCircle className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-slate-400">{exec.exec_type || 'Trade'}</span>
              <span className="text-white">{exec.exec_qty} @ {exec.exec_price}</span>
              {exec.exec_pnl !== null && (
                <span className={exec.exec_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  P&L: ${exec.exec_pnl.toFixed(2)}
                </span>
              )}
              <span className="flex-1" />
              <span className="text-slate-500">{formatTime(exec.exec_time)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================
// RECOMMENDATION MODAL (Trade Reproducibility)
// ============================================================

interface RecommendationModalProps {
  rec: Recommendation
  onClose: () => void
  copiedId: string | null
  onCopyId: (id: string) => void
}

function RecommendationModal({ rec, onClose, copiedId, onCopyId }: RecommendationModalProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'prompt' | 'response' | 'chart'>('overview')

  let rawData: Record<string, unknown> = {}
  try {
    if (rec.raw_response) {
      rawData = JSON.parse(rec.raw_response)
    }
  } catch {
    // Invalid JSON
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <TrendingUp className="w-5 h-5 text-purple-400" />
            <span className="text-white font-bold">{rec.symbol}</span>
            <span className={`font-medium ${
              rec.recommendation.toUpperCase() === 'BUY' || rec.recommendation.toUpperCase() === 'LONG'
                ? 'text-green-400' : rec.recommendation.toUpperCase() === 'SELL' || rec.recommendation.toUpperCase() === 'SHORT'
                  ? 'text-red-400' : 'text-slate-400'
            }`}>{rec.recommendation}</span>
            <span className="text-xs text-slate-400">{(rec.confidence * 100).toFixed(0)}% confidence</span>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">✕</button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-slate-700">
          {(['overview', 'prompt', 'response', 'chart'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm capitalize ${
                activeTab === tab
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {tab === 'chart' && <Image className="w-4 h-4 inline mr-1" />}
              {tab}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[60vh]">
          {activeTab === 'overview' && (
            <div className="grid grid-cols-2 gap-4">
              <InfoRow label="ID" value={rec.id} isCopyable onCopy={() => onCopyId(rec.id)} isCopied={copiedId === rec.id} />
              <InfoRow label="Cycle ID" value={rec.cycle_id} isCopyable onCopy={() => onCopyId(rec.cycle_id)} isCopied={copiedId === rec.cycle_id} />
              <InfoRow label="Symbol" value={rec.symbol} />
              <InfoRow label="Recommendation" value={rec.recommendation} />
              <InfoRow label="Confidence" value={`${(rec.confidence * 100).toFixed(1)}%`} />
              <InfoRow label="Entry Price" value={rec.entry_price?.toString() || 'N/A'} />
              <InfoRow label="Stop Loss" value={rec.stop_loss?.toString() || 'N/A'} />
              <InfoRow label="Take Profit" value={rec.take_profit?.toString() || 'N/A'} />
              <InfoRow label="Risk/Reward" value={rec.risk_reward?.toFixed(2) || 'N/A'} />
              <InfoRow label="Model" value={rec.model_name || 'N/A'} />
              <InfoRow label="Prompt" value={rec.prompt_name || 'N/A'} />
              <InfoRow label="Created" value={formatTime(rec.created_at)} />
            </div>
          )}

          {activeTab === 'prompt' && (
            <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-800/50 p-4 rounded-lg overflow-x-auto">
              {rawData.analysis_prompt as string || 'No prompt data available'}
            </pre>
          )}

          {activeTab === 'response' && (
            <pre className="text-xs text-slate-300 whitespace-pre-wrap bg-slate-800/50 p-4 rounded-lg overflow-x-auto">
              {rawData.model_raw_response as string || JSON.stringify(rawData, null, 2) || 'No response data available'}
            </pre>
          )}

          {activeTab === 'chart' && (
            <div className="space-y-3">
              {rec.chart_path ? (
                <>
                  {/* Info notice */}
                  <div className="bg-slate-800/50 rounded-lg p-3 text-sm">
                    <p className="text-slate-400 mb-1">
                      <span className="font-medium text-slate-300">Chart Path:</span> {rec.chart_path}
                    </p>
                    <p className="text-slate-500 text-xs">
                      Chart images are stored in the .backup folder for reproducibility.
                      Backup path: <code className="text-xs bg-slate-700 px-1.5 py-0.5 rounded">{rec.chart_path.replace(/([^/]+)\/([^/]+)$/, '$1/.backup/$2')}</code>
                    </p>
                  </div>

                  {/* Chart image */}
                  <div className="bg-slate-800/30 rounded-lg p-4">
                    <img
                      src={`/api/bot/chart-image?path=${encodeURIComponent(rec.chart_path)}`}
                      alt={`${rec.symbol} chart`}
                      className="w-full h-auto rounded border border-slate-700"
                      onError={(e) => {
                        const img = e.target as HTMLImageElement;
                        img.style.display = 'none';
                        const parent = img.parentElement;
                        if (parent && !parent.querySelector('.error-msg')) {
                          const errorDiv = document.createElement('div');
                          errorDiv.className = 'error-msg text-center text-slate-500 py-8';
                          errorDiv.innerHTML = '⚠️ Chart image not found';
                          parent.appendChild(errorDiv);
                        }
                      }}
                    />
                  </div>
                </>
              ) : (
                <p className="text-slate-500 text-center py-8">No chart path available</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function InfoRow({ label, value, isCopyable, onCopy, isCopied }: { label: string; value: string; isCopyable?: boolean; onCopy?: () => void; isCopied?: boolean }) {
  return (
    <div className="bg-slate-800/30 rounded p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="flex items-center gap-2">
        <div className="text-sm text-white font-mono truncate flex-1">{value}</div>
        {isCopyable && onCopy && (
          <button
            onClick={onCopy}
            className={`p-1 rounded transition-all shrink-0 ${
              isCopied
                ? 'bg-blue-600/50 text-blue-300'
                : 'hover:bg-blue-600/30 text-slate-500 hover:text-blue-400'
            }`}
            title="Copy ID"
          >
            {isCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          </button>
        )}
      </div>
    </div>
  )
}

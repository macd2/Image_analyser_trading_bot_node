'use client'

import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, RefreshCw, ChevronDown, ChevronRight, Clock, Activity, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { LoadingState, ErrorState } from '@/components/shared'
import { TradeDetailModal } from '@/components/instance/TradeDetailModal'

interface TradesTabProps {
  instanceId: string
}

interface TradeRow {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  fill_price: number | null;
  exit_price: number | null;
  stop_loss: number;
  take_profit: number;
  status: string;
  pnl: number | null;
  pnl_percent: number | null;
  confidence: number | null;
  rr_ratio: number | null;
  created_at: string;
  filled_at: string | null;
  closed_at: string | null;
  submitted_at: string | null;
  timeframe: string | null;
  dry_run: number;
  rejection_reason: string | null;
}

interface CycleWithTrades {
  cycle_id: string;
  started_at: string | null;
  ended_at: string | null;
  symbols_count: number;
  analyzed_count: number;
  trade_count: number;
  trades: TradeRow[];
}

interface RunWithCycles {
  run_id: string;
  started_at: string | null;
  ended_at: string | null;
  cycle_count: number;
  trade_count: number;
  cycles: CycleWithTrades[];
}

interface GroupedTradesData {
  runs: RunWithCycles[];
  stats: {
    total: number;
    winning: number;
    losing: number;
    win_rate: number;
    total_pnl_usd: number;
  };
}

function formatPrice(price: number | null): string {
  if (price === null) return '-'
  if (price >= 1000) return `$${price.toLocaleString()}`
  if (price >= 1) return `$${price.toFixed(2)}`
  return `$${price.toFixed(4)}`
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '-'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : new Date()
  const diffMs = endDate.getTime() - startDate.getTime()
  const mins = Math.floor(diffMs / 60000)
  const hours = Math.floor(mins / 60)
  if (hours > 0) return `${hours}h ${mins % 60}m`
  return `${mins}m`
}

export function TradesTab({ instanceId }: TradesTabProps) {
  const [data, setData] = useState<GroupedTradesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'filled' | 'pending' | 'rejected'>('all')
  const [expandedRuns, setExpandedRuns] = useState<Set<string>>(new Set())
  const [expandedCycles, setExpandedCycles] = useState<Set<string>>(new Set())
  const [selectedTrade, setSelectedTrade] = useState<TradeRow | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const refetch = useCallback(async () => {
    try {
      const res = await fetch(`/api/bot/trades?group_by_run=true&instance_id=${instanceId}&limit=20`)
      if (!res.ok) throw new Error('Failed to fetch trades')
      const json = await res.json()
      setData(json)
      setError(null)
      // Auto-expand first run
      if (json.runs?.length > 0 && expandedRuns.size === 0) {
        setExpandedRuns(new Set([json.runs[0].run_id]))
        if (json.runs[0].cycles?.length > 0) {
          setExpandedCycles(new Set([json.runs[0].cycles[0].cycle_id]))
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error')
    } finally {
      setLoading(false)
    }
  }, [instanceId, expandedRuns.size])

  useEffect(() => {
    refetch()
    const interval = setInterval(refetch, 5000)
    return () => clearInterval(interval)
  }, [refetch])

  if (loading && !data) return <LoadingState text="Loading trades..." />
  if (error) return <ErrorState message={error} onRetry={refetch} />

  const runs = data?.runs || []
  const stats = data?.stats || { total: 0, winning: 0, losing: 0, win_rate: 0, total_pnl_usd: 0 }

  const toggleRun = (runId: string) => {
    setExpandedRuns(prev => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else next.add(runId)
      return next
    })
  }

  const toggleCycle = (cycleId: string) => {
    setExpandedCycles(prev => {
      const next = new Set(prev)
      if (next.has(cycleId)) next.delete(cycleId)
      else next.add(cycleId)
      return next
    })
  }

  const filterTrades = (trades: TradeRow[]) => trades.filter(t => {
    if (filter === 'all') return true
    if (filter === 'filled') return ['filled', 'paper_trade', 'closed'].includes(t.status)
    if (filter === 'pending') return ['pending', 'submitted', 'new', 'open'].includes(t.status)
    if (filter === 'rejected') return ['rejected', 'cancelled', 'failed', 'error'].includes(t.status)
    return true
  })

  return (
    <>
      <TradeDetailModal isOpen={modalOpen} onClose={() => setModalOpen(false)} trade={selectedTrade} />
      <div className="p-6 space-y-4">
        {/* Stats Row */}
        <div className="grid grid-cols-5 gap-3">
        {[
          { label: 'Total', value: stats.total, color: 'text-blue-400' },
          { label: 'Winning', value: stats.winning, color: 'text-green-400' },
          { label: 'Losing', value: stats.losing, color: 'text-red-400' },
          { label: 'Win Rate', value: `${stats.win_rate.toFixed(1)}%`, color: 'text-purple-400' },
          { label: 'Total P&L', value: `$${stats.total_pnl_usd.toFixed(2)}`, color: stats.total_pnl_usd >= 0 ? 'text-green-400' : 'text-red-400' },
        ].map((stat, i) => (
          <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
            <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Filter + Refresh */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {(['all', 'filled', 'pending', 'rejected'] as const).map(f => (
            <Button key={f} variant={filter === f ? 'default' : 'outline'} size="sm" onClick={() => setFilter(f)}>
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </Button>
          ))}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setExpandedRuns(new Set(runs.map(r => r.run_id)))}>
            Expand All
          </Button>
          <Button variant="outline" size="sm" onClick={() => { setExpandedRuns(new Set()); setExpandedCycles(new Set()) }}>
            Collapse All
          </Button>
          <Button variant="ghost" size="sm" onClick={refetch}><RefreshCw size={14} /></Button>
        </div>
      </div>

      {/* Grouped Trades */}
      <div className="space-y-3">
        {runs.length === 0 ? (
          <Card className="bg-slate-800 border-slate-700"><CardContent className="py-8 text-center text-slate-500">No trades found</CardContent></Card>
        ) : runs.map(run => (
          <Card key={run.run_id} className="bg-slate-800 border-slate-700">
            {/* Run Header */}
            <button onClick={() => toggleRun(run.run_id)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-700/50 transition-colors">
              <div className="flex items-center gap-3">
                {expandedRuns.has(run.run_id) ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                <Activity size={16} className="text-blue-400" />
                <span className="font-mono text-sm text-white">Run {run.run_id.slice(0, 8)}</span>
                <span className="text-xs text-slate-500">{run.started_at ? new Date(run.started_at).toLocaleString() : ''}</span>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-slate-400">{run.cycle_count} cycles</span>
                <span className="bg-blue-900/50 text-blue-400 px-2 py-0.5 rounded">{run.trade_count} trades</span>
                <span className="text-slate-500">{formatDuration(run.started_at, run.ended_at)}</span>
              </div>
            </button>

            {/* Cycles */}
            {expandedRuns.has(run.run_id) && (
              <div className="border-t border-slate-700">
                {run.cycles.map(cycle => (
                  <div key={cycle.cycle_id} className="border-b border-slate-700/50 last:border-0">
                    {/* Cycle Header */}
                    <button onClick={() => toggleCycle(cycle.cycle_id)}
                      className="w-full flex items-center justify-between px-6 py-2 hover:bg-slate-700/30 transition-colors">
                      <div className="flex items-center gap-3">
                        {expandedCycles.has(cycle.cycle_id) ? <ChevronDown size={14} className="text-slate-500" /> : <ChevronRight size={14} className="text-slate-500" />}
                        <Clock size={14} className="text-purple-400" />
                        <span className="font-mono text-xs text-slate-300">Cycle {cycle.cycle_id.slice(0, 8)}</span>
                        <span className="text-xs text-slate-500">{cycle.started_at ? new Date(cycle.started_at).toLocaleTimeString() : ''}</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-slate-500">{cycle.symbols_count} symbols</span>
                        <span className="text-slate-500">{cycle.analyzed_count} analyzed</span>
                        <span className="bg-purple-900/50 text-purple-400 px-2 py-0.5 rounded">{cycle.trade_count} trades</span>
                      </div>
                    </button>

                    {/* Trades Table */}
                    {expandedCycles.has(cycle.cycle_id) && filterTrades(cycle.trades).length > 0 && (
                      <Table>
                        <TableHeader>
                          <TableRow className="border-slate-700 hover:bg-transparent">
                            <TableHead className="text-slate-400 pl-10">Symbol</TableHead>
                            <TableHead className="text-slate-400">Side</TableHead>
                            <TableHead className="text-slate-400">Entry</TableHead>
                            <TableHead className="text-slate-400">SL / TP</TableHead>
                            <TableHead className="text-slate-400">Confidence</TableHead>
                            <TableHead className="text-slate-400">P&L</TableHead>
                            <TableHead className="text-slate-400">Type / Status</TableHead>
                            <TableHead className="text-slate-400 text-center">Action</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filterTrades(cycle.trades).map(trade => (
                            <TableRow key={trade.id} className="border-slate-700/50 hover:bg-slate-700/30 cursor-pointer">
                              <TableCell className="font-mono text-white pl-10">{trade.symbol}</TableCell>
                              <TableCell>
                                <div className="flex items-center gap-1">
                                  {trade.side === 'Buy' ? <TrendingUp size={14} className="text-green-400" /> : <TrendingDown size={14} className="text-red-400" />}
                                  <span className={trade.side === 'Buy' ? 'text-green-400' : 'text-red-400'}>{trade.side}</span>
                                </div>
                              </TableCell>
                              <TableCell className="text-slate-300 text-sm">{formatPrice(trade.entry_price)}</TableCell>
                              <TableCell className="text-slate-300 text-sm">
                                <div className="text-red-400">{formatPrice(trade.stop_loss)}</div>
                                <div className="text-green-400">{formatPrice(trade.take_profit)}</div>
                              </TableCell>
                              <TableCell>
                                {trade.confidence ? (
                                  <div className="flex items-center gap-1">
                                    <div className={`w-12 h-6 rounded text-xs font-bold flex items-center justify-center ${
                                      trade.confidence >= 0.7 ? 'bg-green-900 text-green-300'
                                      : trade.confidence >= 0.5 ? 'bg-yellow-900 text-yellow-300'
                                      : 'bg-red-900 text-red-300'
                                    }`}>{(trade.confidence * 100).toFixed(0)}%</div>
                                  </div>
                                ) : <span className="text-slate-500">-</span>}
                              </TableCell>
                              <TableCell className={`font-bold text-sm ${trade.pnl !== null && trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {trade.pnl !== null ? `${trade.pnl >= 0 ? '+' : ''}${trade.pnl_percent?.toFixed(2)}%` : '-'}
                              </TableCell>
                              <TableCell>
                                <div className="flex flex-col gap-1">
                                  {/* Trade Type Badge (Paper vs Live) */}
                                  <span className={`text-xs px-2 py-0.5 rounded text-center ${
                                    trade.dry_run === 1 ? 'bg-yellow-900/50 text-yellow-400' : 'bg-blue-900/50 text-blue-400'
                                  }`}>
                                    {trade.dry_run === 1 ? '📄 Paper' : '💰 Live'}
                                  </span>
                                  {/* Status Badge */}
                                  <span className={`text-xs px-2 py-0.5 rounded text-center ${
                                    ['filled', 'paper_trade', 'closed'].includes(trade.status) ? 'bg-green-900/50 text-green-400'
                                    : ['rejected', 'cancelled', 'failed', 'error'].includes(trade.status) ? 'bg-red-900/50 text-red-400'
                                    : 'bg-slate-700/50 text-slate-400'
                                  }`}>{trade.status === 'paper_trade' ? 'Filled' : trade.status}</span>
                                </div>
                              </TableCell>
                              <TableCell className="text-center">
                                <button onClick={() => { setSelectedTrade(trade); setModalOpen(true); }} className="text-blue-400 hover:text-blue-300 transition-colors">
                                  <Eye size={16} />
                                </button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
    </>
  )
}


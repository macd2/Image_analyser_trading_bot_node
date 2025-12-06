'use client'

import { useState, useEffect, useMemo, useCallback } from 'react'
import { RefreshCw, Download, ChevronDown, ChevronRight, Clock, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { LoadingState, ErrorState } from '@/components/shared'

interface LogsTabProps {
  instanceId: string
}

type LogLevel = 'all' | 'error' | 'warning' | 'info' | 'debug'

interface ErrorLog {
  id: string
  timestamp: string
  level: string
  message: string
  component: string | null
  run_id: string | null
  cycle_id: string | null
}

interface RunWithLogs {
  run_id: string | null
  started_at: string | null
  ended_at: string | null
  log_count: number
  logs: ErrorLog[]
}

const levelColors: Record<LogLevel, string> = {
  all: 'text-slate-300',
  error: 'text-red-400',
  warning: 'text-amber-400',
  info: 'text-blue-400',
  debug: 'text-slate-400',
}

const levelLabels: Record<LogLevel, string> = {
  all: 'All',
  error: 'Errors',
  warning: 'Warnings',
  info: 'Info',
  debug: 'Debug',
}

export function LogsTab({ instanceId }: LogsTabProps) {
  const [runs, setRuns] = useState<RunWithLogs[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<LogLevel>('all')
  const [expandedRuns, setExpandedRuns] = useState<Set<string | null>>(new Set())
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchLogs = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true)
    try {
      const res = await fetch(`/api/bot/error-logs?instance_id=${instanceId}&limit=200&group_by_run=true`)
      if (res.ok) {
        const data = await res.json()
        if (data.runs) {
          setRuns(data.runs)
          // Auto-expand first run only on initial load
          if (loading && data.runs.length > 0) {
            setExpandedRuns(new Set([data.runs[0].run_id]))
          }
        }
      }
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch logs')
    } finally {
      setLoading(false)
      if (isManualRefresh) setRefreshing(false)
    }
  }, [instanceId, loading])

  useEffect(() => {
    fetchLogs()
    if (!autoRefresh) return
    const interval = setInterval(fetchLogs, 3000) // Refresh every 3 seconds
    return () => clearInterval(interval)
  }, [instanceId, autoRefresh, fetchLogs])

  const toggleRun = (runId: string | null) => {
    setExpandedRuns(prev => {
      const next = new Set(prev)
      if (next.has(runId)) {
        next.delete(runId)
      } else {
        next.add(runId)
      }
      return next
    })
  }

  const logCounts = useMemo(() => {
    const counts = { error: 0, warning: 0, info: 0, debug: 0 }
    runs.forEach(run => {
      run.logs.forEach(log => {
        const level = log.level.toLowerCase()
        if (level in counts) counts[level as keyof typeof counts]++
      })
    })
    return counts
  }, [runs])

  const totalLogs = runs.reduce((sum, r) => sum + r.log_count, 0)

  const downloadLogs = () => {
    const content = runs.flatMap(run =>
      run.logs.map(l =>
        `[${l.timestamp}] [${l.level}] [Run: ${run.run_id?.slice(0, 8) || 'N/A'}] ${l.component ? `[${l.component}] ` : ''}${l.message}`
      )
    ).join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `logs-${instanceId}-${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const formatDateTime = (iso: string | null) => {
    if (!iso) return 'N/A'
    const d = new Date(iso)
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  const formatDuration = (start: string | null, end: string | null) => {
    if (!start) return ''
    const startDate = new Date(start)
    const endDate = end ? new Date(end) : new Date()
    const diffMs = endDate.getTime() - startDate.getTime()
    const mins = Math.floor(diffMs / 60000)
    if (mins < 60) return `${mins}m`
    const hours = Math.floor(mins / 60)
    return `${hours}h ${mins % 60}m`
  }

  if (loading && runs.length === 0) return <LoadingState text="Loading logs..." />
  if (error && runs.length === 0) return <ErrorState message={error} onRetry={fetchLogs} />

  return (
    <div className="p-4 space-y-3 h-full flex flex-col">
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2 items-center">
          <span className="text-sm text-slate-400">{runs.length} runs, {totalLogs} logs</span>
          <div className="flex gap-1 ml-2">
            {(['all', 'error', 'warning', 'info', 'debug'] as const).map(level => (
              <Button
                key={level}
                variant={filter === level ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setFilter(level)}
                className="h-7 px-3 text-xs"
              >
                <span className={level !== 'all' ? levelColors[level] : ''}>
                  {levelLabels[level]}
                </span>
                {level !== 'all' && logCounts[level] > 0 && (
                  <span className="ml-1.5 text-slate-400">({logCounts[level]})</span>
                )}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant={autoRefresh ? 'default' : 'outline'}
            size="sm"
            className="h-7"
            onClick={() => setAutoRefresh(!autoRefresh)}
            title={autoRefresh ? 'Auto-refresh enabled (3s)' : 'Auto-refresh disabled'}
          >
            {autoRefresh ? '⏸️ Auto' : '▶️ Manual'}
          </Button>
          <Button variant="outline" size="sm" className="h-7" onClick={() => setExpandedRuns(new Set(runs.map(r => r.run_id)))}>
            Expand All
          </Button>
          <Button variant="outline" size="sm" className="h-7" onClick={() => setExpandedRuns(new Set())}>
            Collapse All
          </Button>
          <Button variant="outline" size="sm" className="h-7" onClick={downloadLogs}>
            <Download size={14} />
          </Button>
          <Button variant="outline" size="sm" className="h-7" onClick={() => fetchLogs(true)} disabled={refreshing}>
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </Button>
        </div>
      </div>

      {/* Runs */}
      <Card className="bg-slate-900 border-slate-700 flex-1 overflow-hidden">
        <CardContent className="p-0 h-full">
          <ScrollArea className="h-[calc(100vh-240px)]">
            <div className="space-y-1 p-2">
              {runs.length === 0 ? (
                <div className="text-slate-500 text-center py-8">
                  No error logs recorded for this instance
                </div>
              ) : (
                runs.map((run) => {
                  const isExpanded = expandedRuns.has(run.run_id)
                  const filteredLogs = filter === 'all'
                    ? run.logs
                    : run.logs.filter(l => l.level.toLowerCase() === filter)
                  const errorCount = run.logs.filter(l => l.level === 'ERROR').length
                  const warnCount = run.logs.filter(l => l.level === 'WARNING').length

                  return (
                    <div key={run.run_id || 'orphan'} className="border border-slate-700 rounded-lg overflow-hidden">
                      {/* Run Header */}
                      <button
                        onClick={() => toggleRun(run.run_id)}
                        className="w-full flex items-center justify-between p-2 bg-slate-800 hover:bg-slate-700/50 transition"
                      >
                        <div className="flex items-center gap-2">
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span className="font-mono text-xs text-slate-400">
                            {run.run_id ? run.run_id.slice(0, 8) : 'No Run ID'}
                          </span>
                          <div className="flex items-center gap-1 text-xs text-slate-500">
                            <Clock size={12} />
                            {formatDateTime(run.started_at)}
                            {run.ended_at && <span className="text-slate-600">→ {formatDateTime(run.ended_at)}</span>}
                            <span className="text-slate-600">({formatDuration(run.started_at, run.ended_at)})</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {errorCount > 0 && (
                            <span className="px-1.5 py-0.5 text-[10px] bg-red-900/50 text-red-400 rounded flex items-center gap-1">
                              <AlertCircle size={10} /> {errorCount}
                            </span>
                          )}
                          {warnCount > 0 && (
                            <span className="px-1.5 py-0.5 text-[10px] bg-amber-900/50 text-amber-400 rounded">
                              {warnCount} warn
                            </span>
                          )}
                          <span className="text-xs text-slate-500">{run.log_count} logs</span>
                        </div>
                      </button>

                      {/* Logs */}
                      {isExpanded && (
                        <div className="bg-slate-900/50 p-2 font-mono text-xs max-h-64 overflow-y-auto">
                          {filteredLogs.length === 0 ? (
                            <div className="text-slate-600 text-center py-2">
                              No {filter} logs in this run
                            </div>
                          ) : (
                            filteredLogs.map((log) => (
                              <div
                                key={log.id}
                                className={`${levelColors[log.level.toLowerCase() as LogLevel] || 'text-slate-300'} py-0.5 whitespace-pre-wrap break-all`}
                              >
                                <span className="text-slate-600">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                                {' '}<span className="font-bold">[{log.level}]</span>
                                {log.component && <span className="text-slate-500"> [{log.component}]</span>}
                                {' '}{log.message}
                              </div>
                            ))
                          )}
                        </div>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}


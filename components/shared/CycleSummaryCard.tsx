'use client'

import { useState, useEffect, useMemo } from 'react'
import { TrendingUp, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useRealtime } from '@/hooks/useRealtime'
import { useBotState } from '@/lib/context/BotStateContext'

interface CycleSummaryCardProps {
  instanceId: string
}

interface StepSummary {
  step: string
  emoji: string
  title: string
  logs: string[]
}

interface CycleSummaryData {
  cycleNumber: number
  cycleId: string
  timeframe: string
  mode: 'LIVE' | 'DRYRUN'
  duration: number
  status: 'success' | 'error' | 'running'
  symbolsAnalyzed: number
  recommendationsGenerated: number
  buySignals: number
  sellSignals: number
  holdSignals: number
  actionableSignals: number
  selectedForExecution: number
  tradesExecuted: number
  rejectedTrades: number
  errors: number
  steps: StepSummary[]
  timestamp: Date
}

export function CycleSummaryCard({ instanceId }: CycleSummaryCardProps) {
  useRealtime()
  const { logs } = useBotState()
  const [cycleSummary, setCycleSummary] = useState<CycleSummaryData | null>(null)
  const [expandedSections, setExpandedSections] = useState({
    symbols: true,
    recommendations: true,
    actionable: true,
    selected: true,
    executed: true,
    rejected: false,
    errors: false
  })

  const instanceLogs = useMemo(() => logs[instanceId] || [], [logs, instanceId])
  const [expandedSteps, setExpandedSteps] = useState<Record<string, boolean>>({})

  // Fetch latest cycle data from API
  useEffect(() => {
    const fetchLatestCycle = async () => {
      try {
        const res = await fetch(`/api/bot/latest-cycle?instance_id=${instanceId}`)
        if (res.ok) {
          const data = await res.json()
          if (data.cycle_id) {
            // Fetch cycle stats
            const statsRes = await fetch(`/api/bot/cycle-stats?cycle_id=${data.cycle_id}`)
            if (statsRes.ok) {
              const statsData = await statsRes.json()
              setCycleSummary({
                cycleNumber: 0,
                cycleId: data.cycle_id,
                timeframe: 'unknown',
                mode: 'LIVE',
                duration: 0,
                status: 'running',
                symbolsAnalyzed: statsData.charts_captured || 0,
                recommendationsGenerated: statsData.recommendations_generated || 0,
                buySignals: 0,
                sellSignals: 0,
                holdSignals: 0,
                actionableSignals: 0,
                selectedForExecution: 0,
                tradesExecuted: statsData.trades_executed || 0,
                rejectedTrades: 0,
                errors: 0,
                steps: [],
                timestamp: new Date()
              })
            }
          }
        }
      } catch (err) {
        console.error('Failed to fetch latest cycle:', err)
      }
    }

    fetchLatestCycle()
  }, [instanceId])

  // Parse cycle summary from logs (fallback)
  useEffect(() => {
    if (instanceLogs.length === 0) return

    // Look for the main cycle summary line
    const cycleSummaryLine = instanceLogs.find(log =>
      log.includes('📊 CYCLE #') && log.includes('COMPLETE')
    )

    if (!cycleSummaryLine) return

    // Extract cycle data from logs
    const cycleMatch = cycleSummaryLine.match(/CYCLE #(\d+).*\[([a-z0-9]+)\].*-\s*(LIVE|DRYRUN)/)
    const timeframeMatch = cycleSummaryLine.match(/(\d+h)/)

    if (!cycleMatch) return

    const cycleNumber = parseInt(cycleMatch[1])
    const cycleId = cycleMatch[2]
    const mode = cycleMatch[3] as 'LIVE' | 'DRYRUN'
    const timeframe = timeframeMatch ? timeframeMatch[1] : 'unknown'

    // Extract metrics from subsequent log lines
    let symbolsAnalyzed = 0
    let recommendationsGenerated = 0
    let buySignals = 0
    let sellSignals = 0
    let holdSignals = 0
    let actionableSignals = 0
    let selectedForExecution = 0
    let tradesExecuted = 0
    let rejectedTrades = 0
    let errors = 0
    let duration = 0

    instanceLogs.forEach(log => {
      // Match "├─ Symbols analyzed: 5"
      if (log.includes('Symbols analyzed:')) {
        const match = log.match(/Symbols analyzed:\s*(\d+)/)
        if (match) symbolsAnalyzed = parseInt(match[1])
      }
      // Match "├─ Recommendations generated: 3"
      if (log.includes('Recommendations generated:')) {
        const match = log.match(/Recommendations generated:\s*(\d+)/)
        if (match) recommendationsGenerated = parseInt(match[1])
      }
      // Match "├─ BUY: 2"
      if (log.includes('│  ├─ BUY:')) {
        const match = log.match(/BUY:\s*(\d+)/)
        if (match) buySignals = parseInt(match[1])
      }
      // Match "├─ SELL: 1"
      if (log.includes('│  ├─ SELL:')) {
        const match = log.match(/SELL:\s*(\d+)/)
        if (match) sellSignals = parseInt(match[1])
      }
      // Match "└─ HOLD: 0"
      if (log.includes('│  └─ HOLD:')) {
        const match = log.match(/HOLD:\s*(\d+)/)
        if (match) holdSignals = parseInt(match[1])
      }
      // Match "├─ Actionable signals: 3"
      if (log.includes('Actionable signals:')) {
        const match = log.match(/Actionable signals:\s*(\d+)/)
        if (match) actionableSignals = parseInt(match[1])
      }
      // Match "├─ Selected for execution: 2"
      if (log.includes('Selected for execution:')) {
        const match = log.match(/Selected for execution:\s*(\d+)/)
        if (match) selectedForExecution = parseInt(match[1])
      }
      // Match "├─ Trades executed: 2"
      if (log.includes('├─ Trades executed:')) {
        const match = log.match(/Trades executed:\s*(\d+)/)
        if (match) tradesExecuted = parseInt(match[1])
      }
      // Match "├─ Rejected trades: 0"
      if (log.includes('├─ Rejected trades:')) {
        const match = log.match(/Rejected trades:\s*(\d+)/)
        if (match) rejectedTrades = parseInt(match[1])
      }
      // Match "├─ Errors: 0"
      if (log.includes('├─ Errors:')) {
        const match = log.match(/Errors:\s*(\d+)/)
        if (match) errors = parseInt(match[1])
      }
      // Match "├─ Total duration: 12.5s"
      if (log.includes('Total duration:')) {
        const match = log.match(/Total duration:\s*([\d.]+)s/)
        if (match) duration = parseFloat(match[1])
      }
    })

    const status = errors === 0 ? 'success' : 'error'

    // Extract step summaries
    const steps: StepSummary[] = []
    const stepPatterns = [
      { step: '0', emoji: '🧹', title: 'Chart Cleanup', pattern: /🧹 STEP 0 COMPLETE/ },
      { step: '1', emoji: '📷', title: 'Capturing Charts', pattern: /📷 STEP 1 COMPLETE/ },
      { step: '1.5', emoji: '🔍', title: 'Checking Existing Recommendations', pattern: /🔍 STEP 1.5 COMPLETE/ },
      { step: '2', emoji: '🤖', title: 'Parallel Analysis', pattern: /🤖 STEP 2 COMPLETE/ },
      { step: '3', emoji: '📊', title: 'Collecting Recommendations', pattern: /📊 STEP 3 COMPLETE/ },
      { step: '4', emoji: '🏆', title: 'Ranking Signals by Quality', pattern: /🏆 STEP 4 COMPLETE/ },
      { step: '5', emoji: '📦', title: 'Checking Available Slots', pattern: /📦 STEP 5 COMPLETE/ },
      { step: '6', emoji: '🎯', title: 'Selecting Best Signals', pattern: /🎯 STEP 6 COMPLETE/ },
      { step: '7', emoji: '🚀', title: 'Executing Signals', pattern: /🚀 STEP 7 COMPLETE/ },
    ]

    stepPatterns.forEach(({ step, emoji, title, pattern }) => {
      const stepStartIdx = instanceLogs.findIndex(log => pattern.test(log))
      if (stepStartIdx !== -1) {
        const stepLogs: string[] = []
        for (let i = stepStartIdx; i < instanceLogs.length; i++) {
          const log = instanceLogs[i]
          // Stop when we hit the next step or final summary
          if (i > stepStartIdx && (log.includes('STEP') || log.includes('CYCLE #'))) break
          stepLogs.push(log)
        }
        steps.push({ step, emoji, title, logs: stepLogs })
      }
    })

    setCycleSummary({
      cycleNumber,
      cycleId,
      timeframe,
      mode,
      duration,
      status,
      symbolsAnalyzed,
      recommendationsGenerated,
      buySignals,
      sellSignals,
      holdSignals,
      actionableSignals,
      selectedForExecution,
      tradesExecuted,
      rejectedTrades,
      errors,
      steps,
      timestamp: new Date()
    })
  }, [instanceLogs])

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  if (!cycleSummary) {
    return (
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-slate-500" />
            Cycle Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-slate-500 text-sm text-center py-4">
            Waiting for cycle data...
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-blue-400" />
            Cycle Summary
            {cycleSummary.status === 'success' && (
              <span className="text-xs bg-green-900/50 text-green-400 px-2 py-0.5 rounded">✅ Success</span>
            )}
            {cycleSummary.status === 'error' && (
              <span className="text-xs bg-red-900/50 text-red-400 px-2 py-0.5 rounded">⚠️ Errors</span>
            )}
          </CardTitle>
          <div className="text-xs text-slate-400">
            Cycle #{cycleSummary.cycleNumber} • {cycleSummary.timeframe} • {cycleSummary.mode}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Header Stats */}
        <div className="grid grid-cols-4 gap-2 text-xs">
          <div className="bg-slate-700/50 rounded p-2">
            <div className="text-slate-400">Duration</div>
            <div className="text-white font-bold">{cycleSummary.duration.toFixed(1)}s</div>
          </div>
          <div className="bg-slate-700/50 rounded p-2">
            <div className="text-slate-400">Analyzed</div>
            <div className="text-white font-bold">{cycleSummary.symbolsAnalyzed}</div>
          </div>
          <div className="bg-slate-700/50 rounded p-2">
            <div className="text-slate-400">Recommendations</div>
            <div className="text-white font-bold">{cycleSummary.recommendationsGenerated}</div>
          </div>
          <div className="bg-slate-700/50 rounded p-2">
            <div className="text-slate-400">Executed</div>
            <div className="text-white font-bold">{cycleSummary.tradesExecuted}</div>
          </div>
        </div>

        {/* Step-by-Step Execution */}
        {cycleSummary.steps.length > 0 && (
          <div className="space-y-1 text-xs border-t border-slate-700 pt-3">
            <div className="text-slate-400 font-semibold mb-2">Execution Steps:</div>
            {cycleSummary.steps.map((stepData) => (
              <div key={stepData.step} className="bg-slate-700/20 rounded">
                <button
                  onClick={() => setExpandedSteps(prev => ({
                    ...prev,
                    [stepData.step]: !prev[stepData.step]
                  }))}
                  className="w-full flex items-center justify-between p-2 hover:bg-slate-700/40 transition"
                >
                  <span className="text-slate-300">
                    {stepData.emoji} STEP {stepData.step}: {stepData.title}
                  </span>
                  {expandedSteps[stepData.step] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>
                {expandedSteps[stepData.step] && (
                  <div className="px-2 pb-2 text-slate-400 border-t border-slate-700/50 pt-2 font-mono text-[11px] max-h-48 overflow-y-auto">
                    {stepData.logs.map((log, idx) => (
                      <div key={idx} className="text-slate-400 whitespace-pre-wrap break-words">
                        {log}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Collapsible Sections */}
        <div className="space-y-2 text-xs">
          {/* Recommendations */}
          <div className="bg-slate-700/30 rounded">
            <button
              onClick={() => toggleSection('recommendations')}
              className="w-full flex items-center justify-between p-2 hover:bg-slate-700/50 transition"
            >
              <span className="text-slate-300">📊 Recommendations</span>
              {expandedSections.recommendations ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
            {expandedSections.recommendations && (
              <div className="px-2 pb-2 text-slate-400 border-t border-slate-700/50 pt-2">
                <div className="flex gap-3">
                  <span>🟢 BUY: {cycleSummary.buySignals}</span>
                  <span>🔴 SELL: {cycleSummary.sellSignals}</span>
                  <span>⚪ HOLD: {cycleSummary.holdSignals}</span>
                </div>
              </div>
            )}
          </div>

          {/* Actionable Signals */}
          <div className="bg-slate-700/30 rounded">
            <button
              onClick={() => toggleSection('actionable')}
              className="w-full flex items-center justify-between p-2 hover:bg-slate-700/50 transition"
            >
              <span className="text-slate-300">🎯 Actionable Signals: {cycleSummary.actionableSignals}</span>
              {expandedSections.actionable ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>

          {/* Selected for Execution */}
          <div className="bg-slate-700/30 rounded">
            <button
              onClick={() => toggleSection('selected')}
              className="w-full flex items-center justify-between p-2 hover:bg-slate-700/50 transition"
            >
              <span className="text-slate-300">✅ Selected: {cycleSummary.selectedForExecution}</span>
              {expandedSections.selected ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>

          {/* Executed Trades */}
          <div className="bg-green-900/20 rounded border border-green-700/30">
            <button
              onClick={() => toggleSection('executed')}
              className="w-full flex items-center justify-between p-2 hover:bg-green-900/30 transition"
            >
              <span className="text-green-400">🚀 Trades Executed: {cycleSummary.tradesExecuted}</span>
              {expandedSections.executed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>

          {/* Rejected Trades */}
          {cycleSummary.rejectedTrades > 0 && (
            <div className="bg-amber-900/20 rounded border border-amber-700/30">
              <button
                onClick={() => toggleSection('rejected')}
                className="w-full flex items-center justify-between p-2 hover:bg-amber-900/30 transition"
              >
                <span className="text-amber-400">⚠️ Rejected: {cycleSummary.rejectedTrades}</span>
                {expandedSections.rejected ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            </div>
          )}

          {/* Errors */}
          {cycleSummary.errors > 0 && (
            <div className="bg-red-900/20 rounded border border-red-700/30">
              <button
                onClick={() => toggleSection('errors')}
                className="w-full flex items-center justify-between p-2 hover:bg-red-900/30 transition"
              >
                <span className="text-red-400">❌ Errors: {cycleSummary.errors}</span>
                {expandedSections.errors ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <div className="text-[10px] text-slate-500 text-center pt-2 border-t border-slate-700">
          Updated: {cycleSummary.timestamp.toLocaleTimeString()}
        </div>
      </CardContent>
    </Card>
  )
}


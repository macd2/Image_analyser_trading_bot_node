'use client'

import { useState, useEffect, useMemo } from 'react'
import { Camera, Eye, Shield, Zap, Coffee, Circle, CheckCircle, TrendingUp, BarChart3, Power, ChevronDown, ChevronUp, Clock } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useLogs } from '@/lib/context/LogsContext'
import { useRealtime } from '@/hooks/useRealtime'

interface UnifiedCycleCardProps {
  instanceId: string
}

interface CycleStatus {
  is_running: boolean
  current_cycle: {
    id: string
    cycle_number: number
    status: string
    started_at: string
    progress_percentage: number
    current_step: 'chart_capture' | 'analysis' | 'risk_management' | 'order_execution' | 'waiting'
    next_step_time: string | null
    steps: Array<{
      name: string
      status: 'completed' | 'current' | 'pending'
      description: string
    }>
  } | null
  cycle_stats: {
    total_cycles: number
    successful_cycles: number
    avg_cycle_duration_minutes: number
    last_cycle_completed: string | null
  }
}

interface SectionLogs {
  step0: string[]
  step1: string[]
  step1_5: string[]
  step2: string[]
  step3: string[]
  step4: string[]
  step5: string[]
  step6: string[]
  step7: string[]
  cycleSummary: string[]
}

const stepIcons = {
  chart_capture: Camera,
  analysis: Eye,
  risk_management: Shield,
  order_execution: Zap,
  waiting: Coffee
}

const stepColors = {
  chart_capture: 'text-blue-400',
  analysis: 'text-purple-400',
  risk_management: 'text-amber-400',
  order_execution: 'text-green-400',
  waiting: 'text-slate-400'
}

const stepBgColors = {
  chart_capture: 'bg-blue-400/30',
  analysis: 'bg-purple-400/30',
  risk_management: 'bg-amber-400/30',
  order_execution: 'bg-green-400/30',
  waiting: 'bg-slate-400/30'
}

export function UnifiedCycleCard({ instanceId }: UnifiedCycleCardProps) {
  useRealtime()
  const { logs } = useLogs()
  const [status, setStatus] = useState<CycleStatus | null>(null)
  const [, setLoading] = useState(true)
  const [, setError] = useState<string | null>(null)
  const [sectionLogs, setSectionLogs] = useState<SectionLogs>({
    step0: [], step1: [], step1_5: [], step2: [], step3: [], step4: [], step5: [], step6: [], step7: [], cycleSummary: []
  })
  const [expandedSections, setExpandedSections] = useState({
    step0: false, step1: false, step1_5: false, step2: false, step3: false, step4: false, step5: false, step6: false, step7: false, cycleSummary: true
  })

  const instanceLogs = useMemo(() => logs[instanceId] || [], [logs, instanceId])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 2000)
    return () => clearInterval(interval)
  }, [instanceId])

  useEffect(() => {
    if (instanceLogs.length === 0) return
    setSectionLogs(prev => ({
      ...prev,
      step0: instanceLogs.filter(log => log.includes('[STEP_0_SUMMARY]')),
      step1: instanceLogs.filter(log => log.includes('[STEP_1_SUMMARY]')),
      step1_5: instanceLogs.filter(log => log.includes('[STEP_1.5_SUMMARY]')),
      step2: instanceLogs.filter(log => log.includes('[STEP_2_SUMMARY]')),
      step3: instanceLogs.filter(log => log.includes('[STEP_3_SUMMARY]')),
      step4: instanceLogs.filter(log => log.includes('[STEP_4_SUMMARY]')),
      step5: instanceLogs.filter(log => log.includes('[STEP_5_SUMMARY]')),
      step6: instanceLogs.filter(log => log.includes('[STEP_6_SUMMARY]')),
      step7: instanceLogs.filter(log => log.includes('[STEP_7_SUMMARY]')),
      cycleSummary: instanceLogs.filter(log => log.includes('[CYCLE_SUMMARY]'))
    }))
  }, [instanceLogs])

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/bot/cycle-status?instance_id=${instanceId}`)
      if (!res.ok) throw new Error('Failed to fetch cycle status')
      const data = await res.json()
      setStatus(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }))
  }

  const formatLog = (log: string) => {
    return log.replace(/\[STEP_\d\.?\d?_SUMMARY\]|\[CYCLE_SUMMARY\]/, '').trim()
  }

  const isRunning = status?.is_running ?? false
  const currentCycle = status?.current_cycle
  const cycleStats = status?.cycle_stats

  const sections = [
    { key: 'step0' as const, emoji: '🧹', title: 'STEP 0: Chart Cleanup' },
    { key: 'step1' as const, emoji: '📷', title: 'STEP 1: Capturing Charts' },
    { key: 'step1_5' as const, emoji: '🔍', title: 'STEP 1.5: Checking Existing Recommendations' },
    { key: 'step2' as const, emoji: '🤖', title: 'STEP 2: Parallel Analysis' },
    { key: 'step3' as const, emoji: '📊', title: 'STEP 3: Collecting Recommendations' },
    { key: 'step4' as const, emoji: '🏆', title: 'STEP 4: Ranking Signals by Quality' },
    { key: 'step5' as const, emoji: '📦', title: 'STEP 5: Checking Available Slots' },
    { key: 'step6' as const, emoji: '🎯', title: 'STEP 6: Selecting Best Signals' },
    { key: 'step7' as const, emoji: '🚀', title: 'STEP 7: Executing Signals' },
    { key: 'cycleSummary' as const, emoji: '📋', title: 'Cycle Summary' }
  ]

  // Placeholder steps for when bot is not running
  const placeholderSteps = [
    { name: 'Chart Capture', status: 'pending' as const },
    { name: 'Analysis', status: 'pending' as const },
    { name: 'Risk Management', status: 'pending' as const },
    { name: 'Order Execution', status: 'pending' as const },
    { name: 'Waiting', status: 'pending' as const }
  ]

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-400" />
            Trading Cycle Status
          </CardTitle>
          <div className="text-xs text-slate-400">
            Cycle #{currentCycle?.cycle_number || 0} • {cycleStats?.total_cycles || 0} total
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-5 gap-4">
          {/* LEFT SECTION - Status & Progress */}
          <div className="col-span-2 space-y-4">
            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-400">Progress</span>
                <span className="text-white font-medium">{currentCycle?.progress_percentage || 0}%</span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500"
                  style={{ width: `${currentCycle?.progress_percentage || 0}%` }}
                />
              </div>
            </div>

            {/* Current Step Highlight */}
            {isRunning && currentCycle ? (
              <div 
                className={`p-3 rounded-lg transition-all duration-300 ${
                  stepBgColors[currentCycle.current_step]
                } border ${
                  stepColors[currentCycle.current_step].replace('text', 'border')
                }/30`}
                // 👇 ADD subtle scale & shadow on active state
                style={{ transform: 'scale(1.02)', boxShadow: '0 4px 12px rgba(0,0,0,0.25)' }}
              >
                <div className="flex items-center gap-3">
                  {(() => {
                    const Icon = stepIcons[currentCycle.current_step]
                    // 👇 ENHANCED ICON: larger, stronger pulse, colored glow
                    return (
                      <Icon 
                        className={`
                          w-6 h-6   /* ↑ 20% larger */
                          ${stepColors[currentCycle.current_step]}
                          animate-pulse-strong   /* ← custom stronger pulse (see below) */
                          drop-shadow-[0_0_10px_{${
                            stepColors[currentCycle.current_step]
                              .replace('text-', '')
                              .replace('-400', '-400/50')
                              .replace('-500', '-500/50')
                          }] 
                        `}
                      />
                    )
                  })()}
                  <div>
                    <div className="font-bold text-white text-sm tracking-wide">
                      {/* 👇 Uppercase + slight spacing for emphasis */}
                      {currentCycle.current_step.replace(/_/g, ' ').toUpperCase()}
                    </div>
                    <div className="text-xs text-slate-200 mt-0.5">
                      {currentCycle.steps.find(s => s.name.toLowerCase().includes(currentCycle.current_step.split('_')[0]))?.description || 'Processing...'}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-slate-700/30 border border-slate-600/30">
                <div className="flex items-center gap-3">
                  <Power className="w-5 h-5 text-slate-500" />
                  <div>
                    <div className="font-medium text-slate-400 text-sm">Bot Not Running</div>
                    <div className="text-xs text-slate-500">Start the bot to see cycle status</div>
                  </div>
                </div>
              </div>
            )}

            {/* Cycle Steps Grid */}
            <div className="space-y-2">
              <div className="text-xs text-slate-400">Cycle Steps</div>
              <div className="grid grid-cols-5 gap-1">
                {(currentCycle?.steps || placeholderSteps).map((step, index) => {
                  const stepKey = step.name.toLowerCase().replace(' ', '_') as keyof typeof stepIcons
                  const Icon = stepIcons[stepKey] || Circle

                  return (
                    <div
                      key={index}
                      className={`flex flex-col items-center p-2 rounded ${step.status === 'current' ? stepBgColors[stepKey] : 'bg-slate-700/30'} transition-all`}
                    >
                      <div className="relative">
                        <Icon className={`w-4 h-4 ${step.status === 'completed' ? 'text-green-400' : step.status === 'current' ? stepColors[stepKey] + ' animate-pulse drop-shadow-lg' : 'text-slate-500'}`} />
                        {step.status === 'completed' && (
                          <CheckCircle className="w-3 h-3 text-green-400 absolute -top-1 -right-1" />
                        )}
                      </div>
                      <div className="text-[10px] text-center mt-1 text-slate-300">
                        {step.name.split(' ')[0]}
                      </div>
                      <div className="text-[8px] text-slate-500 text-center mt-0.5">
                        {step.status === 'current' ? 'NOW' : step.status === 'completed' ? 'DONE' : 'PENDING'}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Stats */}
            <div className="border-t border-slate-700 pt-3 space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <TrendingUp className="w-3 h-3 text-green-400" />
                <div>
                  <div className="text-slate-400">Success Rate</div>
                  <div className="text-white font-medium">
                    {cycleStats && cycleStats.total_cycles > 0
                      ? Math.round((cycleStats.successful_cycles / cycleStats.total_cycles) * 100)
                      : 0}%
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <BarChart3 className="w-3 h-3 text-blue-400" />
                <div>
                  <div className="text-slate-400">Avg Duration</div>
                  <div className="text-white font-medium">
                    {cycleStats?.avg_cycle_duration_minutes || 0}m
                  </div>
                </div>
              </div>
              {cycleStats?.last_cycle_completed && (
                <div className="text-[10px] text-slate-500 text-center pt-2 border-t border-slate-700">
                  Last: {new Date(cycleStats.last_cycle_completed).toLocaleTimeString()}
                </div>
              )}
            </div>
          </div>

          {/* RIGHT SECTION - Step Details */}
          <div className="col-span-3 space-y-2 max-h-96 overflow-y-auto">
            {sections.map(section => {
              const hasLogs = sectionLogs[section.key].length > 0
              return (
                <div key={section.key} className="bg-slate-700/30 rounded">
                  <button
                    onClick={() => toggleSection(section.key)}
                    className="w-full flex items-center justify-between p-2 hover:bg-slate-700/50 transition"
                  >
                    <span className="text-slate-300 text-sm">{section.emoji} {section.title}</span>
                    {expandedSections[section.key] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </button>
                  {expandedSections[section.key] && (
                    <div className="px-2 pb-2 border-t border-slate-700/50 pt-2 font-mono text-[11px] max-h-48 overflow-y-auto">
                      {hasLogs ? (
                        sectionLogs[section.key].map((log, idx) => (
                          <div key={idx} className="text-slate-400 whitespace-pre-wrap break-words">
                            {formatLog(log)}
                          </div>
                        ))
                      ) : (
                        <div className="text-slate-500 text-xs italic py-2">
                          {isRunning ? 'Waiting for data...' : 'Bot not running'}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}


'use client'

import { useState, useEffect, useMemo } from 'react'
import { TrendingUp, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useRealtime } from '@/hooks/useRealtime'
import { useBotState } from '@/lib/context/BotStateContext'

interface CycleSummaryCardProps {
  instanceId: string
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

export function CycleSummaryCard({ instanceId }: CycleSummaryCardProps) {
  useRealtime()
  const { logs } = useBotState()
  const [sectionLogs, setSectionLogs] = useState<SectionLogs>({
    step0: [],
    step1: [],
    step1_5: [],
    step2: [],
    step3: [],
    step4: [],
    step5: [],
    step6: [],
    step7: [],
    cycleSummary: []
  })
  const [expandedSections, setExpandedSections] = useState({
    step0: false,
    step1: false,
    step1_5: false,
    step2: false,
    step3: false,
    step4: false,
    step5: false,
    step6: false,
    step7: false,
    cycleSummary: true
  })

  const instanceLogs = useMemo(() => logs[instanceId] || [], [logs, instanceId])

  // Filter logs by section markers in real-time
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



  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  const formatLog = (log: string) => {
    return log.replace(/\[STEP_\d\.?\d?_SUMMARY\]|\[CYCLE_SUMMARY\]/, '').trim()
  }

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

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-blue-400" />
          Cycle Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {/* Collapsible Sections for each step + cycle summary */}
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
                <div className="px-2 pb-2 border-t border-slate-700/50 pt-2 font-mono text-[11px] max-h-64 overflow-y-auto">
                  {hasLogs ? (
                    sectionLogs[section.key].map((log, idx) => (
                      <div key={idx} className="text-slate-400 whitespace-pre-wrap break-words">
                        {formatLog(log)}
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-500 text-xs italic py-2">
                      Waiting for data...
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}


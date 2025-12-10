'use client'

import { useState, useEffect } from 'react'
import { Camera, Eye, Shield, Zap, Coffee, Clock, CheckCircle, Circle, TrendingUp, BarChart3, Power } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState } from '@/components/shared'

interface CycleStatusCardProps {
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

export function CycleStatusCard({ instanceId }: CycleStatusCardProps) {
  const [status, setStatus] = useState<CycleStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, 2000) // Refresh every 2 seconds for near real-time
    return () => clearInterval(interval)
  }, [instanceId])

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

  if (loading) return <LoadingState text="Loading cycle status..." />
  if (error) return <div className="text-red-400 text-sm">Error: {error}</div>

  const isRunning = status?.is_running ?? false
  const currentCycle = status?.current_cycle
  const cycleStats = status?.cycle_stats

  // Bot not running - show placeholder with consistent height
  if (!isRunning) {
    return (
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="w-4 h-4 text-slate-500" />
              Trading Cycle Status
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-700/50 flex items-center justify-center mb-3">
              <Power className="w-6 h-6 text-slate-500" />
            </div>
            <div className="text-slate-400 font-medium mb-1">Bot Not Running</div>
            <div className="text-xs text-slate-500">Start the bot to see trading cycle status</div>
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
            <Clock className="w-4 h-4 text-blue-400" />
            Trading Cycle Status
          </CardTitle>
          {cycleStats && (
            <div className="text-xs text-slate-400">
              Cycle #{currentCycle?.cycle_number || 0} • {cycleStats.total_cycles} total
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress Bar */}
        {currentCycle && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-slate-400">Progress</span>
              <span className="text-white font-medium">{currentCycle.progress_percentage}%</span>
            </div>
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gradient-to-r from-blue-500 to-green-500 transition-all duration-500"
                style={{ width: `${currentCycle.progress_percentage}%` }}
              />
            </div>
          </div>
        )}

        {/* Current Step Highlight */}
        {currentCycle && (
          <div className={`p-3 rounded-lg ${stepBgColors[currentCycle.current_step]} border ${stepColors[currentCycle.current_step].replace('text', 'border')}/30`}>
            <div className="flex items-center gap-3">
              {(() => {
                const Icon = stepIcons[currentCycle.current_step]
                return <Icon className={`w-5 h-5 ${stepColors[currentCycle.current_step]} animate-pulse drop-shadow-lg`} />
              })()}
              <div>
                <div className="font-medium text-white">
                  {currentCycle.current_step.replace('_', ' ').toUpperCase()}
                </div>
                <div className="text-xs text-slate-300">
                  {currentCycle.steps.find(s => s.name.toLowerCase().includes(currentCycle.current_step.split('_')[0]))?.description || 'Processing...'}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Cycle Steps */}
        <div className="space-y-2">
          <div className="text-xs text-slate-400 mb-1">Cycle Steps</div>
          <div className="grid grid-cols-5 gap-1">
            {currentCycle?.steps.map((step, index) => {
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

        {/* Cycle Stats */}
        {cycleStats && (
          <div className="border-t border-slate-700 pt-3">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-3 h-3 text-green-400" />
                <div>
                  <div className="text-slate-400">Success Rate</div>
                  <div className="text-white font-medium">
                    {cycleStats.total_cycles > 0 
                      ? Math.round((cycleStats.successful_cycles / cycleStats.total_cycles) * 100)
                      : 0}%
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <BarChart3 className="w-3 h-3 text-blue-400" />
                <div>
                  <div className="text-slate-400">Avg Duration</div>
                  <div className="text-white font-medium">
                    {cycleStats.avg_cycle_duration_minutes}m
                  </div>
                </div>
              </div>
            </div>
            {cycleStats.last_cycle_completed && (
              <div className="text-[10px] text-slate-500 mt-2 text-center">
                Last completed: {new Date(cycleStats.last_cycle_completed).toLocaleTimeString()}
              </div>
            )}
          </div>
        )}

        {!currentCycle && (
          <div className="text-center py-4 text-slate-500 text-sm">
            No active trading cycle
          </div>
        )}
      </CardContent>
    </Card>
  )
}
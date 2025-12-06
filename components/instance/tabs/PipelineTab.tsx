'use client'

import { useState, useEffect } from 'react'
import { Camera, Brain, CheckCircle, AlertCircle, TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState, ErrorState } from '@/components/shared'
import { useSourcerStatus, useCyclesData } from '@/hooks/useBotData'

interface PipelineTabProps {
  instanceId: string
}

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

export function PipelineTab({ instanceId: _instanceId }: PipelineTabProps) {
  const { data: sourcerData, loading: sourcerLoading, refreshing: sourcerRefreshing, error: sourcerError, refetch: refetchSourcer } = useSourcerStatus(5000)
  const { data: cyclesData, loading: cyclesLoading, refreshing: cyclesRefreshing, error: cyclesError, refetch: refetchCycles } = useCyclesData(10000)
  const [countdown, setCountdown] = useState<number>(0)

  useEffect(() => {
    if (sourcerData?.next_capture?.seconds_remaining) {
      setCountdown(sourcerData.next_capture.seconds_remaining)
    }
  }, [sourcerData?.next_capture?.seconds_remaining])

  useEffect(() => {
    const timer = setInterval(() => setCountdown(prev => Math.max(0, prev - 1)), 1000)
    return () => clearInterval(timer)
  }, [])

  const loading = sourcerLoading && cyclesLoading && !sourcerData && !cyclesData
  const error = sourcerError || cyclesError

  if (loading) return <LoadingState text="Loading pipeline..." />
  if (error) return <ErrorState message={error} onRetry={() => { refetchSourcer(); refetchCycles() }} />

  const stats = sourcerData?.stats || { captured_today: 0, failed_today: 0, symbols_count: 0 }
  const analysisStats = cyclesData?.stats || { images_analyzed: 0, valid_signals: 0, actionable_pct: 0 }
  const analysisResults = cyclesData?.current_cycle_analysis || []
  const promptInfo = cyclesData?.prompt_info || { name: 'unknown', model: 'unknown', avg_confidence: 0 }

  return (
    <div className="p-6 space-y-6">
      {/* Pipeline Status Cards */}
      <div className="grid grid-cols-2 gap-4">
        {/* Capture Card */}
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Camera className="text-blue-400" size={18} />
              Chart Capture
              <Button variant="ghost" size="sm" onClick={() => refetchSourcer(true)} disabled={sourcerRefreshing} className="ml-auto h-6 w-6 p-0">
                <RefreshCw size={12} className={sourcerRefreshing ? 'animate-spin' : ''} />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-400 text-sm">Next capture:</span>
              <span className={`font-mono ${countdown < 60 ? 'text-yellow-400' : 'text-blue-400'}`}>
                {formatTime(countdown)}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-green-400 font-bold">{stats.captured_today}</div>
                <div className="text-slate-400">Captured</div>
              </div>
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-red-400 font-bold">{stats.failed_today}</div>
                <div className="text-slate-400">Failed</div>
              </div>
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-blue-400 font-bold">{stats.symbols_count}</div>
                <div className="text-slate-400">Symbols</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Analysis Card */}
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Brain className="text-purple-400" size={18} />
              AI Analysis
              <span className="text-xs text-slate-500 font-normal ml-2">{promptInfo.name}</span>
              <Button variant="ghost" size="sm" onClick={() => refetchCycles(true)} disabled={cyclesRefreshing} className="ml-auto h-6 w-6 p-0">
                <RefreshCw size={12} className={cyclesRefreshing ? 'animate-spin' : ''} />
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-blue-400 font-bold">{analysisStats.images_analyzed}</div>
                <div className="text-slate-400">Analyzed</div>
              </div>
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-green-400 font-bold">{analysisStats.valid_signals}</div>
                <div className="text-slate-400">Signals</div>
              </div>
              <div className="bg-slate-700/50 rounded p-2">
                <div className="text-purple-400 font-bold">{promptInfo.avg_confidence.toFixed(2)}</div>
                <div className="text-slate-400">Avg Conf</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Analysis Results */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Current Cycle Analysis</CardTitle>
        </CardHeader>
        <CardContent>
          {analysisResults.length === 0 ? (
            <div className="text-slate-500 text-center py-6">No analysis results for current cycle</div>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {analysisResults.slice(0, 10).map((result, i) => (
                <div key={i} className="flex items-center justify-between bg-slate-700/30 rounded px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-white">{result.symbol}</span>
                    {result.recommendation === 'LONG' ? (
                      <TrendingUp size={14} className="text-green-400" />
                    ) : result.recommendation === 'SHORT' ? (
                      <TrendingDown size={14} className="text-red-400" />
                    ) : (
                      <Minus size={14} className="text-slate-400" />
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-400">Conf: {(result.confidence * 100).toFixed(0)}%</span>
                    {result.status === 'valid' ? (
                      <CheckCircle size={14} className="text-green-400" />
                    ) : (
                      <AlertCircle size={14} className="text-red-400" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}


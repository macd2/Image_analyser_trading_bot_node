'use client'

import { useEffect, useState } from 'react'
import { AlertCircle, TrendingUp, Lightbulb, Zap } from 'lucide-react'
import { useBlink } from '@/hooks/useBlink'

interface AIInsights {
  top_performers: Array<{
    rank: number
    strategy: string
    sharpe_ratio: number
    win_rate: number
    insight: string
  }>
  risk_alerts: Array<{
    level: 'high' | 'medium' | 'low'
    title: string
    description: string
    recommendation: string
  }>
  recommendations: Array<{
    priority: 'high' | 'medium' | 'low'
    title: string
    description: string
    expectedImpact: string
  }>
  pattern_insights: Array<{
    pattern: string
    frequency: string
    profitability: string
    recommendation: string
  }>
  timestamp: string
}

export default function AIInsights() {
  const [insights, setInsights] = useState<AIInsights | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchInsights = async () => {
      try {
        const res = await fetch('/api/dashboard/ai-insights')
        if (!res.ok) throw new Error('Failed to fetch AI insights')
        const data = await res.json()
        setInsights(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }

    fetchInsights()
  }, [])

  if (loading) return <div className="text-gray-400">Loading AI insights...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (!insights) return null

  // Blink hooks for top performers
  const topPerformerBlinks = insights.top_performers.map(p => useBlink(p.sharpe_ratio))

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'high': return 'bg-red-900/30 border-red-700'
      case 'medium': return 'bg-yellow-900/30 border-yellow-700'
      case 'low': return 'bg-green-900/30 border-green-700'
      default: return 'bg-slate-700'
    }
  }

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'high': return 'bg-red-900/30 border-red-700'
      case 'medium': return 'bg-yellow-900/30 border-yellow-700'
      case 'low': return 'bg-blue-900/30 border-blue-700'
      default: return 'bg-slate-700'
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Performers */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-green-400" />
          <h3 className="text-sm font-semibold text-white">Top Performers</h3>
        </div>
        <div className="space-y-3">
          {insights.top_performers.map((performer, idx) => (
            <div key={performer.rank} className={`bg-slate-700 rounded p-4 flex items-start justify-between ${topPerformerBlinks[idx] ? 'blink' : ''}`}>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-2xl">{performer.rank === 1 ? '🥇' : performer.rank === 2 ? '🥈' : '🥉'}</span>
                  <p className="text-sm font-semibold text-white">{performer.strategy}</p>
                </div>
                <p className="text-xs text-gray-400">{performer.insight}</p>
              </div>
              <div className="text-right">
                <p className={`text-sm font-bold text-green-400 ${topPerformerBlinks[idx] ? 'text-blink' : ''}`}>{performer.sharpe_ratio.toFixed(2)} Sharpe</p>
                <p className="text-xs text-gray-400">{performer.win_rate.toFixed(1)}% Win Rate</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Risk Alerts */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <AlertCircle className="w-5 h-5 text-red-400" />
          <h3 className="text-sm font-semibold text-white">Risk Alerts</h3>
        </div>
        <div className="space-y-3">
          {insights.risk_alerts.map((alert, idx) => (
            <div key={idx} className={`rounded p-4 border ${getRiskColor(alert.level)}`}>
              <div className="flex items-start justify-between mb-2">
                <p className="text-sm font-semibold text-white">{alert.title}</p>
                <span className={`text-xs px-2 py-1 rounded ${alert.level === 'high' ? 'bg-red-700 text-red-100' : alert.level === 'medium' ? 'bg-yellow-700 text-yellow-100' : 'bg-green-700 text-green-100'}`}>
                  {alert.level.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-gray-300 mb-2">{alert.description}</p>
              <p className="text-xs text-gray-400 italic">💡 {alert.recommendation}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <Lightbulb className="w-5 h-5 text-yellow-400" />
          <h3 className="text-sm font-semibold text-white">Recommendations</h3>
        </div>
        <div className="space-y-3">
          {insights.recommendations.map((rec, idx) => (
            <div key={idx} className={`rounded p-4 border ${getPriorityColor(rec.priority)}`}>
              <div className="flex items-start justify-between mb-2">
                <p className="text-sm font-semibold text-white">{rec.title}</p>
                <span className={`text-xs px-2 py-1 rounded ${rec.priority === 'high' ? 'bg-red-700 text-red-100' : rec.priority === 'medium' ? 'bg-yellow-700 text-yellow-100' : 'bg-blue-700 text-blue-100'}`}>
                  {rec.priority.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-gray-300 mb-2">{rec.description}</p>
              <p className="text-xs text-green-400">📈 Expected Impact: {rec.expectedImpact}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pattern Insights */}
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-5 h-5 text-blue-400" />
          <h3 className="text-sm font-semibold text-white">Pattern Insights</h3>
        </div>
        <div className="space-y-3">
          {insights.pattern_insights.map((pattern, idx) => (
            <div key={idx} className="bg-slate-700 rounded p-4">
              <p className="text-sm font-semibold text-white mb-2">{pattern.pattern}</p>
              <div className="grid grid-cols-3 gap-3 mb-2">
                <div>
                  <p className="text-xs text-gray-400">Frequency</p>
                  <p className="text-sm font-bold text-blue-400">{pattern.frequency}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">Profitability</p>
                  <p className="text-sm font-bold text-green-400">{pattern.profitability}</p>
                </div>
              </div>
              <p className="text-xs text-gray-400 italic">💡 {pattern.recommendation}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Last Updated */}
      <div className="text-xs text-gray-500 text-center">
        Last updated: {new Date(insights.timestamp).toLocaleString()}
      </div>
    </div>
  )
}


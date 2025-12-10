'use client'

import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, Target, AlertTriangle, RefreshCw, Activity, Clock, Zap, BarChart3 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingState, ErrorState, StatusBadge } from '@/components/shared'
import TradeChartModal from '@/components/shared/TradeChartModal'
import type { TradeData } from '@/components/shared/TradeChart'

interface PositionsTabProps {
  instanceId: string
}

interface MonitorActivity {
  id: string
  timestamp: string
  symbol: string
  event: string
  message: string
  trade_id: string | null
  run_id: string | null
}

interface MonitorSettings {
  enable_position_tightening: boolean
  enable_sl_tightening: boolean
  enable_tp_proximity_trailing: boolean
  age_tightening_enabled: boolean
  age_cancellation_enabled: boolean
  enable_adx_tightening: boolean
}

function formatPrice(price: number | null): string {
  if (price === null) return '-'
  if (price >= 1000) return `$${price.toLocaleString()}`
  if (price >= 1) return `$${price.toFixed(2)}`
  return `$${price.toFixed(4)}`
}

export function PositionsTab({ instanceId }: PositionsTabProps) {
  // Custom positions fetch to include dry run
  const [positionsData, setPositionsData] = useState<any>(null)
  const [positionsLoading, setPositionsLoading] = useState(true)
  const [positionsRefreshing, setPositionsRefreshing] = useState(false)
  const [positionsError, setPositionsError] = useState<string | null>(null)
  
  const [monitorActivity, setMonitorActivity] = useState<MonitorActivity[]>([])
  const [activityLoading, setActivityLoading] = useState(true)
  const [monitorSettings, setMonitorSettings] = useState<MonitorSettings | null>(null)
  const [selectedTrade, setSelectedTrade] = useState<TradeData | null>(null)
  const [chartModalOpen, setChartModalOpen] = useState(false)

  // Fetch monitor activity
  useEffect(() => {
    const fetchActivity = async () => {
      try {
        const res = await fetch(`/api/bot/monitor-activity?instance_id=${instanceId}&limit=10`)
        const data = await res.json()
        setMonitorActivity(data.activities || [])
      } catch (err) {
        console.error('Failed to fetch monitor activity:', err)
      } finally {
        setActivityLoading(false)
      }
    }

    fetchActivity()
    const interval = setInterval(fetchActivity, 3000) // Refresh every 3 seconds
    return () => clearInterval(interval)
  }, [instanceId])

  // Fetch monitor settings
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch(`/api/bot/config?instance_id=${instanceId}`)
        const data = await res.json()
        const settings: MonitorSettings = {
          enable_position_tightening: data.find((c: any) => c.key === 'trading.enable_position_tightening')?.value === 'true',
          enable_sl_tightening: data.find((c: any) => c.key === 'trading.enable_sl_tightening')?.value === 'true',
          enable_tp_proximity_trailing: data.find((c: any) => c.key === 'trading.enable_tp_proximity_trailing')?.value === 'true',
          age_tightening_enabled: data.find((c: any) => c.key === 'trading.age_tightening_enabled')?.value === 'true',
          age_cancellation_enabled: data.find((c: any) => c.key === 'trading.age_cancellation_enabled')?.value === 'true',
          enable_adx_tightening: data.find((c: any) => c.key === 'trading.enable_adx_tightening')?.value === 'true',
        }
        setMonitorSettings(settings)
      } catch (err) {
        console.error('Failed to fetch monitor settings:', err)
      }
    }

    fetchSettings()
  }, [instanceId])

  // Fetch positions with dry run support
  const fetchPositions = async (isManualRefresh = false) => {
    if (isManualRefresh) setPositionsRefreshing(true)
    
    try {
      const res = await fetch(`/api/bot/positions?instance_id=${instanceId}&include_dry_run=true`)
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      const data = await res.json()
      setPositionsData(data)
      setPositionsError(null)
    } catch (err) {
      setPositionsError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      setPositionsLoading(false)
      if (isManualRefresh) setPositionsRefreshing(false)
    }
  }

  // Initial fetch
  useEffect(() => {
    fetchPositions()
  }, [instanceId])

  // Polling
  useEffect(() => {
    const interval = setInterval(fetchPositions, 5000)
    return () => clearInterval(interval)
  }, [instanceId])

  if (positionsLoading && !positionsData) return <LoadingState text="Loading positions..." />
  if (positionsError) return <ErrorState message={positionsError} onRetry={() => fetchPositions(true)} />

  const positions = positionsData?.open_positions || []
  const closedToday = positionsData?.closed_today || []
  const stats = positionsData?.stats || { 
    open_count: 0, 
    open_dry_run_count: 0,
    open_live_count: 0,
    unrealized_pnl: 0, 
    unrealized_pnl_dry_run: 0,
    unrealized_pnl_live: 0,
    closed_today_count: 0, 
    closed_today_dry_run_count: 0,
    closed_today_live_count: 0,
    win_rate_today: 0, 
    win_rate_today_dry_run: 0,
    win_rate_today_live: 0,
    total_pnl_today: 0,
    total_pnl_today_dry_run: 0,
    total_pnl_today_live: 0
  }

  // Separate live and dry run positions for display
  const livePositions = positions.filter((p: any) => !p.dry_run)
  const dryRunPositions = positions.filter((p: any) => p.dry_run)

  // Helper to convert position to TradeData format
  const positionToTradeData = (pos: any): TradeData => {
    return {
      id: pos.id || `pos-${pos.symbol}-${Date.now()}`,
      symbol: pos.symbol,
      side: pos.side === 'LONG' ? 'Buy' : 'Sell',
      entry_price: pos.entry_price,
      stop_loss: pos.stop_loss,
      take_profit: pos.take_profit,
      exit_price: null,
      status: 'open',
      submitted_at: pos.created_at || new Date().toISOString(),
      filled_at: pos.created_at || new Date().toISOString(),
      closed_at: null,
      created_at: pos.created_at || new Date().toISOString(),
      timeframe: pos.timeframe || '1h',
      dry_run: pos.dry_run,
    }
  }

  // Helper to open chart modal
  const openChart = (pos: any) => {
    setSelectedTrade(positionToTradeData(pos))
    setChartModalOpen(true)
  }

  // Helper to get monitor info for a symbol
  const getMonitorInfo = (symbol: string) => {
    return monitorActivity.filter(a => a.symbol === symbol).slice(0, 3)
  }

  // Helper to format event type
  const getEventIcon = (event: string) => {
    if (event === 'sl_tightened') return <Zap className="w-3 h-3 text-yellow-400" />
    if (event === 'position_closed') return <Target className="w-3 h-3 text-green-400" />
    if (event === 'order_cancelled_age') return <Clock className="w-3 h-3 text-orange-400" />
    return <Activity className="w-3 h-3 text-blue-400" />
  }

  const getEventColor = (event: string) => {
    if (event === 'sl_tightened') return 'text-yellow-400'
    if (event === 'position_closed') return 'text-green-400'
    if (event === 'order_cancelled_age') return 'text-orange-400'
    return 'text-blue-400'
  }

  // PositionItem component for rendering individual positions
  const PositionItem = ({ pos, isDryRun, symbolActivity, openChart }: any) => {
    const hasActivity = symbolActivity.length > 0
    
    return (
      <div className={`bg-slate-700/50 rounded-lg p-4 ${isDryRun ? 'border-l-4 border-yellow-500/50' : ''}`}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            {pos.side === 'LONG' ? (
              <TrendingUp size={20} className="text-green-400" />
            ) : (
              <TrendingDown size={20} className="text-red-400" />
            )}
            <span className="text-white font-mono text-lg">{pos.symbol}</span>
            <StatusBadge status={pos.side.toLowerCase() as 'long' | 'short'} size="sm" />
            {isDryRun && (
              <span className="px-2 py-0.5 text-xs bg-yellow-900/50 text-yellow-400 rounded">
                DRY RUN
              </span>
            )}
            {hasActivity && (
              <div className="flex items-center gap-1 text-xs text-yellow-400">
                <Activity className="w-3 h-3" />
                <span>Monitor Active</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => openChart(pos)}
              className="text-blue-400 hover:text-blue-300 hover:bg-blue-900/20"
            >
              <BarChart3 className="w-4 h-4 mr-1" />
              Chart
            </Button>
            <div className={`text-xl font-bold ${pos.pnl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%
            </div>
          </div>
        </div>

        <div className="grid grid-cols-5 gap-4 text-sm mb-3">
          <div>
            <div className="text-slate-400 text-xs">Entry</div>
            <div className="text-white">{formatPrice(pos.entry_price)}</div>
          </div>
          <div>
            <div className="text-slate-400 text-xs">Current</div>
            <div className="text-white">{pos.current_price ? formatPrice(pos.current_price) : 'Live'}</div>
          </div>
          <div>
            <div className="text-slate-400 text-xs">Size</div>
            <div className="text-white">{pos.quantity}</div>
          </div>
          <div className="flex items-center gap-1">
            <Target size={12} className="text-green-400" />
            <div>
              <div className="text-slate-400 text-xs">TP</div>
              <div className="text-green-400">{pos.take_profit ? formatPrice(pos.take_profit) : '-'}</div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <AlertTriangle size={12} className="text-red-400" />
            <div>
              <div className="text-slate-400 text-xs">SL</div>
              <div className="text-red-400">{pos.stop_loss ? formatPrice(pos.stop_loss) : '-'}</div>
            </div>
          </div>
        </div>

        {/* Monitor Activity for this position */}
        {hasActivity && (
          <div className="border-t border-slate-600 pt-2 mt-2">
            <div className="text-xs text-slate-400 mb-1 flex items-center gap-1">
              <Activity className="w-3 h-3" />
              Recent Monitor Actions:
            </div>
            <div className="space-y-1">
              {symbolActivity.map((activity: any) => (
                <div key={activity.id} className="flex items-center gap-2 text-xs bg-slate-800/50 rounded px-2 py-1">
                  {getEventIcon(activity.event)}
                  <span className={`font-medium ${getEventColor(activity.event)}`}>
                    {activity.event.replace(/_/g, ' ')}
                  </span>
                  <span className="text-slate-400 flex-1 truncate">
                    {activity.message.replace(/\[.*?\]/g, '').trim()}
                  </span>
                  <span className="text-slate-500 text-[10px]">
                    {new Date(activity.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      {/* Stats Row */}
      <div className="grid grid-cols-6 gap-3">
        {[
          { 
            label: 'Open (Total)', 
            value: stats.open_count, 
            color: 'text-blue-400',
            sublabel: `${stats.open_live_count} live, ${stats.open_dry_run_count} dry run`
          },
          { 
            label: 'Unrealized P&L', 
            value: `${stats.unrealized_pnl >= 0 ? '+' : ''}${stats.unrealized_pnl.toFixed(2)}%`, 
            color: stats.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400',
            sublabel: `Live: ${stats.unrealized_pnl_live >= 0 ? '+' : ''}${stats.unrealized_pnl_live.toFixed(2)}%, Dry: ${stats.unrealized_pnl_dry_run >= 0 ? '+' : ''}${stats.unrealized_pnl_dry_run.toFixed(2)}%`
          },
          { 
            label: 'Closed Today', 
            value: stats.closed_today_count, 
            color: 'text-purple-400',
            sublabel: `${stats.closed_today_live_count} live, ${stats.closed_today_dry_run_count} dry run`
          },
          { 
            label: 'Win Rate', 
            value: `${stats.win_rate_today}%`, 
            color: 'text-green-400',
            sublabel: `Live: ${stats.win_rate_today_live}%, Dry: ${stats.win_rate_today_dry_run}%`
          },
          { 
            label: 'Total P&L Today', 
            value: `${stats.total_pnl_today >= 0 ? '+' : ''}$${stats.total_pnl_today.toFixed(2)}`, 
            color: stats.total_pnl_today >= 0 ? 'text-green-400' : 'text-red-400',
            sublabel: `Live: ${stats.total_pnl_today_live >= 0 ? '+' : ''}$${stats.total_pnl_today_live.toFixed(2)}, Dry: ${stats.total_pnl_today_dry_run >= 0 ? '+' : ''}$${stats.total_pnl_today_dry_run.toFixed(2)}`
          },
        ].map((stat, i) => (
          <div key={i} className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-center">
            <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
            <div className="text-xs text-slate-400">{stat.label}</div>
            <div className="text-[10px] text-slate-500 mt-1">{stat.sublabel}</div>
          </div>
        ))}
      </div>

      {/* Monitor Status & Activity */}
      <div className="grid grid-cols-3 gap-4">
        {/* Monitor Status Panel */}
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" />
              <CardTitle className="text-base">Monitor Status</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {monitorSettings ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Master Switch</span>
                  <div className={`flex items-center gap-1 ${monitorSettings.enable_position_tightening ? 'text-green-400' : 'text-red-400'}`}>
                    <div className={`w-2 h-2 rounded-full ${monitorSettings.enable_position_tightening ? 'bg-green-400' : 'bg-red-400'}`} />
                    {monitorSettings.enable_position_tightening ? 'ON' : 'OFF'}
                  </div>
                </div>
                {monitorSettings.enable_position_tightening && (
                  <>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">RR Tightening</span>
                      <div className={`flex items-center gap-1 ${monitorSettings.enable_sl_tightening ? 'text-green-400' : 'text-slate-500'}`}>
                        <div className={`w-2 h-2 rounded-full ${monitorSettings.enable_sl_tightening ? 'bg-green-400' : 'bg-slate-600'}`} />
                        {monitorSettings.enable_sl_tightening ? 'Active' : 'Inactive'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">TP Proximity</span>
                      <div className={`flex items-center gap-1 ${monitorSettings.enable_tp_proximity_trailing ? 'text-green-400' : 'text-slate-500'}`}>
                        <div className={`w-2 h-2 rounded-full ${monitorSettings.enable_tp_proximity_trailing ? 'bg-green-400' : 'bg-slate-600'}`} />
                        {monitorSettings.enable_tp_proximity_trailing ? 'Active' : 'Inactive'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">Age Tightening</span>
                      <div className={`flex items-center gap-1 ${monitorSettings.age_tightening_enabled ? 'text-green-400' : 'text-slate-500'}`}>
                        <div className={`w-2 h-2 rounded-full ${monitorSettings.age_tightening_enabled ? 'bg-green-400' : 'bg-slate-600'}`} />
                        {monitorSettings.age_tightening_enabled ? 'Active' : 'Inactive'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">Age Cancellation</span>
                      <div className={`flex items-center gap-1 ${monitorSettings.age_cancellation_enabled ? 'text-green-400' : 'text-slate-500'}`}>
                        <div className={`w-2 h-2 rounded-full ${monitorSettings.age_cancellation_enabled ? 'bg-green-400' : 'bg-slate-600'}`} />
                        {monitorSettings.age_cancellation_enabled ? 'Active' : 'Inactive'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400">ADX Tightening</span>
                      <div className="flex items-center gap-1 text-slate-500">
                        <div className="w-2 h-2 rounded-full bg-slate-600" />
                        Not Implemented
                      </div>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="text-slate-500 text-center py-4 text-sm">Loading...</div>
            )}
          </CardContent>
        </Card>

        {/* Activity Feed */}
        <Card className="bg-slate-800 border-slate-700 col-span-2">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" />
              <CardTitle className="text-base">Recent Activity</CardTitle>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              Live
            </div>
          </CardHeader>
          <CardContent>
            {activityLoading ? (
              <div className="text-slate-500 text-center py-4 text-sm">Loading activity...</div>
            ) : monitorActivity.length === 0 ? (
              <div className="text-slate-500 text-center py-4 text-sm">No monitor activity yet</div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {monitorActivity.slice(0, 8).map((activity) => (
                  <div key={activity.id} className="flex items-start gap-2 bg-slate-700/30 rounded px-3 py-2 text-xs">
                    <div className="mt-0.5">{getEventIcon(activity.event)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-white">{activity.symbol}</span>
                        <span className={`font-medium ${getEventColor(activity.event)}`}>
                          {activity.event.replace(/_/g, ' ')}
                        </span>
                      </div>
                      <div className="text-slate-400 truncate">{activity.message.replace(/\[.*?\]/g, '').trim()}</div>
                      <div className="text-slate-500 text-[10px] mt-0.5">
                        {new Date(activity.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Open Positions */}
      <Card className="bg-slate-800 border-slate-700">
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-base">Open Positions</CardTitle>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-xs">
              <div className="w-2 h-2 bg-green-500 rounded-full"></div>
              <span className="text-slate-400">Live: {livePositions.length}</span>
            </div>
            <div className="flex items-center gap-1 text-xs">
              <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
              <span className="text-slate-400">Dry Run: {dryRunPositions.length}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={() => fetchPositions(true)} disabled={positionsRefreshing}>
              <RefreshCw size={14} className={positionsRefreshing ? 'animate-spin' : ''} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {positions.length === 0 ? (
            <div className="text-slate-500 text-center py-8">No open positions</div>
          ) : (
            <div className="space-y-3">
              {/* Live Positions */}
              {livePositions.length > 0 && (
                <div className="mb-4">
                  <div className="text-sm font-medium text-green-400 mb-2 flex items-center gap-2">
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                    Live Positions
                  </div>
                  <div className="space-y-3">
                    {livePositions.map((pos: any, i: number) => (
                      <PositionItem 
                        key={i} 
                        pos={pos} 
                        isDryRun={false}
                        symbolActivity={getMonitorInfo(pos.symbol)}
                        openChart={openChart}
                      />
                    ))}
                  </div>
                </div>
              )}
              
              {/* Dry Run Positions */}
              {dryRunPositions.length > 0 && (
                <div>
                  <div className="text-sm font-medium text-yellow-400 mb-2 flex items-center gap-2">
                    <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
                    Dry Run (Paper Trading) Positions
                  </div>
                  <div className="space-y-3">
                    {dryRunPositions.map((pos: any, i: number) => (
                      <PositionItem 
                        key={`dry-${i}`} 
                        pos={pos} 
                        isDryRun={true}
                        symbolActivity={getMonitorInfo(pos.symbol)}
                        openChart={openChart}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Closed Today */}
      {closedToday.length > 0 && (
        <Card className="bg-slate-800 border-slate-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Closed Today</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {closedToday.slice(0, 10).map((pos: any, i: number) => (
                <div key={i} className="flex items-center justify-between bg-slate-700/30 rounded px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-white">{pos.symbol}</span>
                    <StatusBadge status={pos.side.toLowerCase() as 'long' | 'short'} size="sm" />
                    {pos.dry_run && (
                      <span className="px-1.5 py-0.5 text-[10px] bg-yellow-900/50 text-yellow-400 rounded">
                        DRY
                      </span>
                    )}
                  </div>
                  <div className={`font-bold ${pos.pnl_percent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {pos.pnl_percent >= 0 ? '+' : ''}{pos.pnl_percent.toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Live Chart Modal */}
      <TradeChartModal
        isOpen={chartModalOpen}
        onClose={() => setChartModalOpen(false)}
        trade={selectedTrade}
        mode="live"
      />
    </div>
  )
}


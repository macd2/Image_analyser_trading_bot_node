'use client'

import { createContext, useContext, useState, useCallback, ReactNode, useRef, useEffect } from 'react'

interface BotStatus {
  running: boolean
  mode: string
  network: string
  uptime_seconds: number | null
  wallet: { balance_usdt: number; available_usdt: number; equity_usdt: number }
  open_positions: number
  pending_orders: number
}

interface BotState {
  // Bot status
  status: BotStatus | null
  isLoading: boolean
  
  // Persistent logs per instance (survives route changes)
  logs: Record<string, string[]>  // instanceId -> logs array
  stderrLogs: Record<string, string[]>
  
  // Actions
  addLog: (log: string, instanceId?: string) => void
  addStderrLog: (log: string, instanceId?: string) => void
  setLogs: (logs: string[], instanceId?: string) => void
  setStderrLogs: (logs: string[], instanceId?: string) => void
  clearLogs: (instanceId?: string) => void
  setStatus: (status: BotStatus | null) => void
  setLoading: (loading: boolean) => void
}

const BotStateContext = createContext<BotState | null>(null)

export function BotStateProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [isLoading, setLoading] = useState(false)
  const [logs, setLogsState] = useState<Record<string, string[]>>({})
  const [stderrLogs, setStderrLogsState] = useState<Record<string, string[]>>({})
  
  // Use refs to avoid stale closures in callbacks
  const logsRef = useRef(logs)
  const stderrRef = useRef(stderrLogs)
  
  useEffect(() => { logsRef.current = logs }, [logs])
  useEffect(() => { stderrRef.current = stderrLogs }, [stderrLogs])

  const addLog = useCallback((log: string, instanceId?: string) => {
    const key = instanceId || 'global'
    console.log('[BotStateContext] addLog', { key, log: log.substring(0, 100) })
    setLogsState(prev => {
      const instanceLogs = prev[key] || []
      const newLogs = [...instanceLogs, log]
      // Keep last 1000 logs per instance to prevent memory issues
      const updated = { ...prev, [key]: newLogs.slice(-1000) }
      return updated
    })
  }, [])

  const addStderrLog = useCallback((log: string, instanceId?: string) => {
    const key = instanceId || 'global'
    setStderrLogsState(prev => {
      const instanceLogs = prev[key] || []
      const newLogs = [...instanceLogs, log]
      return { ...prev, [key]: newLogs.slice(-1000) }
    })
  }, [])

  const setLogs = useCallback((newLogs: string[], instanceId?: string) => {
    const key = instanceId || 'global'
    // Only update if logs actually changed (avoid re-renders)
    setLogsState(prev => {
      const sliced = newLogs.slice(-1000)
      const instanceLogs = prev[key] || []
      // Fast check: if same length and last entry is same, skip update
      if (instanceLogs.length === sliced.length && instanceLogs[instanceLogs.length - 1] === sliced[sliced.length - 1]) {
        return prev
      }
      return { ...prev, [key]: sliced }
    })
  }, [])

  const setStderrLogs = useCallback((newLogs: string[], instanceId?: string) => {
    const key = instanceId || 'global'
    setStderrLogsState(prev => ({
      ...prev,
      [key]: newLogs.slice(-1000)
    }))
  }, [])

  const clearLogs = useCallback((instanceId?: string) => {
    if (instanceId) {
      setLogsState(prev => ({ ...prev, [instanceId]: [] }))
      setStderrLogsState(prev => ({ ...prev, [instanceId]: [] }))
    } else {
      setLogsState({})
      setStderrLogsState({})
    }
  }, [])

  return (
    <BotStateContext.Provider value={{
      status,
      isLoading,
      logs,
      stderrLogs,
      addLog,
      addStderrLog,
      setLogs,
      setStderrLogs,
      clearLogs,
      setStatus,
      setLoading,
    }}>
      {children}
    </BotStateContext.Provider>
  )
}

export function useBotState() {
  const context = useContext(BotStateContext)
  if (!context) {
    throw new Error('useBotState must be used within BotStateProvider')
  }
  return context
}


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
  
  // Persistent logs (survives route changes)
  logs: string[]
  stderrLogs: string[]
  
  // Actions
  addLog: (log: string) => void
  addStderrLog: (log: string) => void
  setLogs: (logs: string[]) => void
  setStderrLogs: (logs: string[]) => void
  clearLogs: () => void
  setStatus: (status: BotStatus | null) => void
  setLoading: (loading: boolean) => void
}

const BotStateContext = createContext<BotState | null>(null)

export function BotStateProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [isLoading, setLoading] = useState(false)
  const [logs, setLogsState] = useState<string[]>([])
  const [stderrLogs, setStderrLogsState] = useState<string[]>([])
  
  // Use refs to avoid stale closures in callbacks
  const logsRef = useRef(logs)
  const stderrRef = useRef(stderrLogs)
  
  useEffect(() => { logsRef.current = logs }, [logs])
  useEffect(() => { stderrRef.current = stderrLogs }, [stderrLogs])

  const addLog = useCallback((log: string) => {
    setLogsState(prev => {
      const newLogs = [...prev, log]
      // Keep last 1000 logs to prevent memory issues
      return newLogs.slice(-1000)
    })
  }, [])

  const addStderrLog = useCallback((log: string) => {
    setStderrLogsState(prev => {
      const newLogs = [...prev, log]
      return newLogs.slice(-1000)
    })
  }, [])

  const setLogs = useCallback((newLogs: string[]) => {
    setLogsState(newLogs.slice(-1000))
  }, [])

  const setStderrLogs = useCallback((newLogs: string[]) => {
    setStderrLogsState(newLogs.slice(-1000))
  }, [])

  const clearLogs = useCallback(() => {
    setLogsState([])
    setStderrLogsState([])
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


'use client'

import { createContext, useContext, useState, ReactNode } from 'react'

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

  // Actions
  setStatus: (status: BotStatus | null) => void
  setLoading: (loading: boolean) => void
}

const BotStateContext = createContext<BotState | null>(null)

export function BotStateProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<BotStatus | null>(null)
  const [isLoading, setLoading] = useState(false)



  return (
    <BotStateContext.Provider value={{
      status,
      isLoading,
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


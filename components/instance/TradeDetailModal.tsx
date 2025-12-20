'use client'

import { useState } from 'react'
import TradeChartModal from '@/components/shared/TradeChartModal'
import { TradeReplayModal } from '@/components/trades/TradeReplayModal'
import type { TradeData } from '@/components/shared/TradeChart'

interface TradeRow {
  id: string
  symbol: string
  side: string
  entry_price: number
  stop_loss: number
  take_profit: number
  fill_price: number | null
  exit_price: number | null
  pnl: number | null
  pnl_percent: number | null
  confidence: number | null
  rr_ratio: number | null
  created_at: string
  filled_at: string | null
  closed_at: string | null
  submitted_at: string | null
  status: string
  timeframe: string | null
  dry_run: number
  rejection_reason: string | null
  // Strategy information
  strategy_type?: string | null
  strategy_name?: string | null
  strategy_metadata?: any
}

interface TradeDetailModalProps {
  isOpen: boolean
  onClose: () => void
  trade: TradeRow | null
}



export function TradeDetailModal({ isOpen, onClose, trade }: TradeDetailModalProps) {
  const [replayModalOpen, setReplayModalOpen] = useState(false)

  // Use TradeChartModal for all trades (it handles both price-based and spread-based internally)
  if (trade) {
    const tradeData: TradeData = {
      id: trade.id,
      symbol: trade.symbol,
      side: trade.side === 'LONG' ? 'Buy' : 'Sell',
      entry_price: trade.entry_price,
      stop_loss: trade.stop_loss,
      take_profit: trade.take_profit,
      exit_price: trade.exit_price,
      status: trade.status,
      created_at: trade.created_at,
      filled_at: trade.filled_at,
      closed_at: trade.closed_at,
      submitted_at: trade.submitted_at,
      timeframe: trade.timeframe,
      dry_run: trade.dry_run,
      rejection_reason: trade.rejection_reason,
      strategy_type: trade.strategy_type,
      strategy_name: trade.strategy_name,
      strategy_metadata: trade.strategy_metadata,
    }
    return (
      <>
        <TradeChartModal isOpen={isOpen} onClose={onClose} trade={tradeData} mode="historical" />
        <TradeReplayModal tradeId={trade.id} isOpen={replayModalOpen} onClose={() => setReplayModalOpen(false)} />
      </>
    )
  }



  return null
}


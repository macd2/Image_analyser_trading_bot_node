'use client'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type StatusType = 
  | 'running' | 'stopped' | 'error' | 'pending'
  | 'long' | 'short' | 'hold'
  | 'filled' | 'cancelled' | 'rejected'
  | 'success' | 'warning' | 'info'
  | 'live' | 'paper'

interface StatusBadgeProps {
  status: StatusType
  className?: string
  size?: 'sm' | 'md'
}

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  // Bot states
  running: { label: 'Running', className: 'bg-green-500/20 text-green-400 border-green-500/50' },
  stopped: { label: 'Stopped', className: 'bg-slate-500/20 text-slate-400 border-slate-500/50' },
  error: { label: 'Error', className: 'bg-red-500/20 text-red-400 border-red-500/50' },
  pending: { label: 'Pending', className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' },
  
  // Trade directions
  long: { label: 'LONG', className: 'bg-green-900 text-green-200 border-green-700' },
  short: { label: 'SHORT', className: 'bg-red-900 text-red-200 border-red-700' },
  hold: { label: 'HOLD', className: 'bg-gray-900 text-gray-200 border-gray-700' },
  
  // Order states
  filled: { label: 'Filled', className: 'bg-green-500/20 text-green-400 border-green-500/50' },
  cancelled: { label: 'Cancelled', className: 'bg-slate-500/20 text-slate-400 border-slate-500/50' },
  rejected: { label: 'Rejected', className: 'bg-red-500/20 text-red-400 border-red-500/50' },
  
  // General states
  success: { label: 'Success', className: 'bg-green-500/20 text-green-400 border-green-500/50' },
  warning: { label: 'Warning', className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' },
  info: { label: 'Info', className: 'bg-blue-500/20 text-blue-400 border-blue-500/50' },
  
  // Trading modes
  live: { label: 'LIVE', className: 'bg-green-500/20 text-green-400 border-green-500/50' },
  paper: { label: 'PAPER', className: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50' },
}

export function StatusBadge({ status, className, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.info
  
  return (
    <Badge 
      variant="outline" 
      className={cn(
        config.className,
        size === 'sm' && 'text-[10px] px-1.5 py-0',
        className
      )}
    >
      {config.label}
    </Badge>
  )
}


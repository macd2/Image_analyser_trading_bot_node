'use client'

import { useState } from 'react'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ErrorStateProps {
  message: string
  onRetry?: () => void | Promise<void>
  className?: string
}

export function ErrorState({ message, onRetry, className }: ErrorStateProps) {
  const [isRetrying, setIsRetrying] = useState(false)

  const handleRetry = async () => {
    if (!onRetry) return
    setIsRetrying(true)
    try {
      await Promise.resolve(onRetry())
    } finally {
      setIsRetrying(false)
    }
  }

  return (
    <div className={cn('p-6', className)}>
      <div className="bg-red-900/30 border border-red-500 rounded-lg p-4 flex items-center justify-between">
        <div className="flex items-center gap-3 text-red-300">
          <AlertCircle size={20} />
          <span>{message}</span>
        </div>
        {onRetry && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleRetry}
            disabled={isRetrying}
            className="text-blue-400 hover:text-blue-300 disabled:opacity-50"
          >
            <RefreshCw size={14} className={cn("mr-1", isRetrying && "animate-spin")} />
            {isRetrying ? 'Retrying...' : 'Retry'}
          </Button>
        )}
      </div>
    </div>
  )
}


'use client'

import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ErrorStateProps {
  message: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({ message, onRetry, className }: ErrorStateProps) {
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
            onClick={onRetry}
            className="text-blue-400 hover:text-blue-300"
          >
            <RefreshCw size={14} className="mr-1" />
            Retry
          </Button>
        )}
      </div>
    </div>
  )
}


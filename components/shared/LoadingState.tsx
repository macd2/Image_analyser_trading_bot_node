'use client'

import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface LoadingStateProps {
  size?: 'sm' | 'md' | 'lg'
  color?: 'blue' | 'purple' | 'green' | 'yellow' | 'slate'
  text?: string
  className?: string
}

const sizeMap = {
  sm: 16,
  md: 32,
  lg: 48,
}

const colorMap = {
  blue: 'text-blue-400',
  purple: 'text-purple-400',
  green: 'text-green-400',
  yellow: 'text-yellow-400',
  slate: 'text-slate-400',
}

export function LoadingState({ 
  size = 'md', 
  color = 'blue', 
  text,
  className 
}: LoadingStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center h-64 gap-3', className)}>
      <Loader2 
        className={cn('animate-spin', colorMap[color])} 
        size={sizeMap[size]} 
      />
      {text && <p className="text-slate-400 text-sm">{text}</p>}
    </div>
  )
}


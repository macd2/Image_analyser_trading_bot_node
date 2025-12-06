'use client'

import { LucideIcon } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface DataCardProps {
  title: string
  value: string | number
  icon?: LucideIcon
  trend?: string
  positive?: boolean
  subtitle?: string
  variant?: 'default' | 'compact' | 'highlight'
  className?: string
}

export function DataCard({
  title,
  value,
  icon: Icon,
  trend,
  positive,
  subtitle,
  variant = 'default',
  className,
}: DataCardProps) {
  const isCompact = variant === 'compact'
  const isHighlight = variant === 'highlight'
  
  return (
    <Card className={cn(
      'bg-slate-800 border-slate-700',
      isHighlight && 'border-blue-500/50 bg-blue-950/20',
      className
    )}>
      <CardContent className={cn('p-4', isCompact && 'p-3')}>
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <p className={cn(
              'text-slate-400',
              isCompact ? 'text-xs' : 'text-sm'
            )}>
              {title}
            </p>
            <p className={cn(
              'font-bold text-white',
              isCompact ? 'text-lg mt-1' : 'text-2xl mt-2'
            )}>
              {value}
            </p>
            {(trend || subtitle) && (
              <p className={cn(
                'text-xs mt-1',
                positive === undefined ? 'text-slate-400' :
                positive ? 'text-green-400' : 'text-red-400'
              )}>
                {trend || subtitle}
              </p>
            )}
          </div>
          {Icon && (
            <div className={cn(
              'rounded-lg',
              isCompact ? 'p-2' : 'p-3',
              positive === undefined ? 'bg-slate-700/50' :
              positive ? 'bg-green-900/30' : 'bg-red-900/30'
            )}>
              <Icon 
                size={isCompact ? 18 : 24} 
                className={cn(
                  positive === undefined ? 'text-slate-400' :
                  positive ? 'text-green-400' : 'text-red-400'
                )}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}


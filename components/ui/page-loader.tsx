'use client';

import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PageLoaderProps {
  /** Loading message to display */
  message?: string;
  /** Additional CSS classes */
  className?: string;
  /** Size of the spinner: 'sm' | 'md' | 'lg' */
  size?: 'sm' | 'md' | 'lg';
  /** Whether to show as full page overlay or inline */
  fullPage?: boolean;
}

const sizeMap = {
  sm: { spinner: 16, text: 'text-xs' },
  md: { spinner: 24, text: 'text-sm' },
  lg: { spinner: 32, text: 'text-base' },
};

/**
 * Reusable loading spinner component for dashboard pages.
 * Can be used as a full-page loader or inline loader.
 */
export function PageLoader({
  message = 'Loading...',
  className,
  size = 'md',
  fullPage = true,
}: PageLoaderProps) {
  const { spinner, text } = sizeMap[size];

  const content = (
    <div className={cn('flex flex-col items-center justify-center gap-3', className)}>
      <Loader2 
        size={spinner} 
        className="animate-spin text-yellow-400" 
      />
      {message && (
        <p className={cn('text-slate-400', text)}>
          {message}
        </p>
      )}
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        {content}
      </div>
    );
  }

  return content;
}

/**
 * Skeleton loader for cards - can be used while data is loading
 */
export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('bg-slate-800/50 border border-slate-700 rounded-lg p-4 animate-pulse', className)}>
      <div className="h-4 bg-slate-700 rounded w-1/3 mb-3" />
      <div className="space-y-2">
        <div className="h-3 bg-slate-700 rounded w-full" />
        <div className="h-3 bg-slate-700 rounded w-2/3" />
      </div>
    </div>
  );
}

/**
 * Inline loader for buttons or small areas
 */
export function InlineLoader({ 
  message, 
  className 
}: { 
  message?: string; 
  className?: string;
}) {
  return (
    <div className={cn('flex items-center gap-2 text-slate-400', className)}>
      <Loader2 size={14} className="animate-spin" />
      {message && <span className="text-xs">{message}</span>}
    </div>
  );
}


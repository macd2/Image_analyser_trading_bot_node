'use client'

import { usePathname } from 'next/navigation'
import Sidebar from '@/components/Sidebar'
import { BotStateProvider } from '@/lib/context/BotStateContext'
import { GlobalLogListener } from '@/components/GlobalLogListener'
import { OpenAIRateLimitBanner } from '@/components/OpenAIRateLimitBanner'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const pathname = usePathname()

  // Extract instance ID from URL if viewing instance detail page
  const instanceIdMatch = pathname.match(/\/instances\/([^/?]+)/)
  const instanceId = instanceIdMatch ? instanceIdMatch[1] : null

  return (
    <BotStateProvider>
      {/* Global listener for Socket.IO bot logs - populates BotStateContext */}
      <GlobalLogListener />

      {/* Show OpenAI rate limit banner if viewing an instance */}
      {instanceId && <OpenAIRateLimitBanner instanceId={instanceId} />}

      <div className="flex h-screen bg-slate-950">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </BotStateProvider>
  )
}


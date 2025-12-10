'use client'

import Sidebar from '@/components/Sidebar'
import { BotStateProvider } from '@/lib/context/BotStateContext'
import { GlobalLogListener } from '@/components/GlobalLogListener'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <BotStateProvider>
      {/* Global listener for Socket.IO bot logs - populates BotStateContext */}
      <GlobalLogListener />
      <div className="flex h-screen bg-slate-950">
        <Sidebar />
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </BotStateProvider>
  )
}


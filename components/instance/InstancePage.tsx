'use client'

import { useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { InstanceHeader } from './InstanceHeader'
import { OverviewTab } from './tabs/OverviewTab'
import { BrowserTab } from './tabs/BrowserTab'
import { PipelineTab } from './tabs/PipelineTab'
import { TradesTab } from './tabs/TradesTab'
import { PositionsTab } from './tabs/PositionsTab'
import { LogsTab } from './tabs/LogsTab'
import { SettingsModal } from './modals/SettingsModal'
import { LoadingState } from '@/components/shared'

interface InstancePageProps {
  instanceId: string
}

function InstancePageContent({ instanceId }: InstancePageProps) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [showSettings, setShowSettings] = useState(false)
  
  const currentTab = searchParams.get('tab') || 'overview'

  const handleTabChange = (value: string) => {
    router.push(`/instances/${instanceId}?tab=${value}`, { scroll: false })
  }

  return (
    <div className="flex flex-col h-full">
      <InstanceHeader 
        instanceId={instanceId} 
        onSettingsClick={() => setShowSettings(true)}
      />
      
      <Tabs value={currentTab} onValueChange={handleTabChange} className="flex-1 flex flex-col">
        <div className="bg-slate-900 border-b border-slate-700">
          <TabsList className="bg-transparent h-auto p-0 gap-0">
            <TabsTrigger 
              value="overview" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              📊 Overview
            </TabsTrigger>
            <TabsTrigger 
              value="browser" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              🖥️ Browser
            </TabsTrigger>
            <TabsTrigger 
              value="pipeline" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              🔄 Pipeline
            </TabsTrigger>
            <TabsTrigger 
              value="trades" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              💹 Trades
            </TabsTrigger>
            <TabsTrigger 
              value="positions" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              📈 Positions
            </TabsTrigger>
            <TabsTrigger 
              value="logs" 
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-blue-500 data-[state=active]:bg-transparent px-4 py-3"
            >
              📋 Logs
            </TabsTrigger>
          </TabsList>
        </div>
        
        <div className="flex-1 overflow-auto">
          <TabsContent value="overview" className="m-0 h-full">
            <OverviewTab instanceId={instanceId} />
          </TabsContent>
          <TabsContent value="browser" className="m-0 h-full">
            <BrowserTab instanceId={instanceId} />
          </TabsContent>
          <TabsContent value="pipeline" className="m-0 h-full">
            <PipelineTab instanceId={instanceId} />
          </TabsContent>
          <TabsContent value="trades" className="m-0 h-full">
            <TradesTab instanceId={instanceId} />
          </TabsContent>
          <TabsContent value="positions" className="m-0 h-full">
            <PositionsTab instanceId={instanceId} />
          </TabsContent>
          <TabsContent value="logs" className="m-0 h-full">
            <LogsTab instanceId={instanceId} />
          </TabsContent>
        </div>
      </Tabs>

      <SettingsModal 
        instanceId={instanceId}
        open={showSettings}
        onOpenChange={setShowSettings}
      />
    </div>
  )
}

export function InstancePage({ instanceId }: InstancePageProps) {
  return (
    <Suspense fallback={<LoadingState text="Loading instance..." />}>
      <InstancePageContent instanceId={instanceId} />
    </Suspense>
  )
}


'use client'

import { useState, useEffect } from 'react'
import { RefreshCw, HelpCircle } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { LoadingState } from '@/components/shared'

interface SettingsModalProps {
  instanceId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface ConfigItem {
  key: string
  value: string
  hasValue: boolean
  type: 'string' | 'number' | 'boolean' | 'json'
  category: string
  group?: string | null
  order?: number
  description: string | null
  tooltip?: string | null
}

export function SettingsModal({ instanceId, open, onOpenChange }: SettingsModalProps) {
  const [config, setConfig] = useState<ConfigItem[]>([])
  const [loading, setLoading] = useState(true)
  const [pendingChanges, setPendingChanges] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [activeCategory, setActiveCategory] = useState('trading')
  const [prompts, setPrompts] = useState<Array<{ name: string; description: string }>>([])
  const [instancePrompt, setInstancePrompt] = useState<string>('')

  useEffect(() => {
    if (open) {
      fetchConfig()
      fetchPrompts()
    }
  }, [open, instanceId])

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await fetch(`/api/bot/config?instance_id=${instanceId}`)
      const data = await res.json()
      if (data.config) setConfig(data.config)
    } catch (err) {
      console.error('Failed to fetch config:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchPrompts = async () => {
    try {
      const [promptsRes, instanceRes] = await Promise.all([
        fetch('/api/bot/prompts'),
        fetch(`/api/bot/instances?id=${instanceId}`)
      ])
      const promptsData = await promptsRes.json()
      const instanceData = await instanceRes.json()
      if (promptsData.prompts) setPrompts(promptsData.prompts)
      if (instanceData.instance?.prompt_name) setInstancePrompt(instanceData.instance.prompt_name)
    } catch (err) {
      console.error('Failed to fetch prompts:', err)
    }
  }

  const handleChange = (key: string, value: string) => {
    setPendingChanges(prev => ({ ...prev, [key]: value }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      // Convert pendingChanges object to array format expected by API
      const updates = Object.entries(pendingChanges).map(([key, value]) => ({ key, value }))

      await fetch('/api/bot/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates, instance_id: instanceId })
      })
      setPendingChanges({})
      await fetchConfig()
    } catch (err) {
      console.error('Failed to save config:', err)
    } finally {
      setSaving(false)
    }
  }

  const handlePromptChange = async (promptName: string) => {
    try {
      await fetch('/api/bot/instances', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: instanceId, prompt_name: promptName })
      })
      setInstancePrompt(promptName)
    } catch (err) {
      console.error('Failed to update prompt:', err)
    }
  }

  const categories = [...new Set(config.map(c => c.category))].sort()
  const filteredConfig = config.filter(c => c.category === activeCategory)
  const hasPendingChanges = Object.keys(pendingChanges).length > 0

  // Group settings by their group property
  const groupedConfig = filteredConfig.reduce((acc, item) => {
    const group = item.group || 'General'
    if (!acc[group]) acc[group] = []
    acc[group].push(item)
    return acc
  }, {} as Record<string, ConfigItem[]>)

  // Get ordered group names (sorted by the prefix number if present, then alphabetically)
  const groupOrder = Object.keys(groupedConfig).sort((a, b) => {
    // "General" always first
    if (a === 'General') return -1
    if (b === 'General') return 1
    // Otherwise sort naturally (the "1.", "2.", etc prefixes will sort correctly)
    return a.localeCompare(b)
  })

  // Helper to get display name and indentation level from group name
  const getGroupDisplay = (groupName: string) => {
    // Check for hierarchy indicators like "2. ├─" or "2. └─"
    const isChild = groupName.includes('├─') || groupName.includes('└─')
    // Remove the prefix numbers and tree characters for display
    const displayName = groupName.replace(/^\d+\.\s*(├─|└─)?\s*/, '')
    return { displayName, isChild }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl bg-slate-900 border-slate-700 text-white">
        <DialogHeader>
          <DialogTitle>Instance Settings</DialogTitle>
        </DialogHeader>

        {loading ? (
          <LoadingState size="sm" />
        ) : (
          <TooltipProvider>
            <Tabs value={activeCategory} onValueChange={setActiveCategory}>
              <TabsList className="bg-slate-800 mb-4">
                {categories.map(cat => (
                  <TabsTrigger key={cat} value={cat} className="capitalize">
                    {cat}
                  </TabsTrigger>
                ))}
              </TabsList>

              <ScrollArea className="h-[400px] pr-4">
                {activeCategory === 'ai' && (
                  <div className="mb-4 p-3 bg-blue-900/20 border border-blue-600/50 rounded-lg">
                    <label className="text-xs text-slate-300 font-medium block mb-2">Instance Prompt</label>
                    <Select value={instancePrompt} onValueChange={handlePromptChange}>
                      <SelectTrigger className="bg-slate-800 border-slate-600">
                        <SelectValue placeholder="Select a prompt..." />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-800 border-slate-600">
                        {prompts.map(p => (
                          <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}

                <div className="space-y-4">
                  {groupOrder.map(groupName => {
                    const { displayName, isChild } = getGroupDisplay(groupName)

                    return (
                      <div key={groupName} className={`space-y-2 ${isChild ? 'ml-4 pl-3 border-l-2 border-slate-700' : ''}`}>
                        {/* Group Header */}
                        <h3 className={`text-xs font-semibold uppercase tracking-wider border-b pb-1 ${
                          isChild
                            ? 'text-slate-500 border-slate-700/50'
                            : 'text-slate-400 border-slate-700'
                        }`}>
                          {displayName}
                        </h3>

                        {/* Group Items */}
                        <div className="space-y-2">
                          {groupedConfig[groupName].map(item => {
                            const shortKey = item.key.split('.').pop() || item.key
                            const currentValue = pendingChanges[item.key] ?? item.value
                            const isChanged = pendingChanges[item.key] !== undefined
                            const isBoolean = item.type === 'boolean'
                            const hasNoValue = !item.hasValue && !isChanged

                            return (
                              <div key={item.key} className={`p-2.5 rounded-lg border ${
                                isChanged
                                  ? 'bg-amber-900/20 border-amber-600/50'
                                  : hasNoValue
                                    ? 'bg-slate-900/30 border-slate-700/30 opacity-60'
                                    : 'bg-slate-800/50 border-slate-700/50'
                              }`}>
                                <div className="flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-2 flex-1 min-w-0">
                                    <label className="text-sm text-slate-300 font-medium truncate">
                                      {shortKey.replace(/_/g, ' ')}
                                    </label>
                                    {hasNoValue && <span className="text-xs text-slate-500">(not set)</span>}
                                    {item.tooltip && (
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <HelpCircle className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300 cursor-help flex-shrink-0" />
                                        </TooltipTrigger>
                                        <TooltipContent className="max-w-xs bg-slate-800 border-slate-600 text-slate-200">
                                          <p className="text-xs">{item.tooltip}</p>
                                        </TooltipContent>
                                      </Tooltip>
                                    )}
                                  </div>
                                  {isBoolean ? (
                                    <Switch
                                      checked={currentValue === 'true'}
                                      onCheckedChange={(checked) => handleChange(item.key, checked ? 'true' : 'false')}
                                    />
                                  ) : (
                                    <input
                                      type="text"
                                      value={currentValue}
                                      placeholder={hasNoValue ? 'Enter value...' : ''}
                                      onChange={(e) => handleChange(item.key, e.target.value)}
                                      className="w-40 bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm text-white text-right placeholder:text-slate-600"
                                    />
                                  )}
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </ScrollArea>

              {hasPendingChanges && (
                <div className="mt-4 pt-4 border-t border-slate-700 flex items-center justify-between">
                  <span className="text-sm text-amber-400">{Object.keys(pendingChanges).length} change(s)</span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setPendingChanges({})}>Cancel</Button>
                    <Button size="sm" onClick={handleSave} disabled={saving}>
                      {saving ? <><RefreshCw className="w-3 h-3 animate-spin mr-1" />Saving...</> : 'Save Changes'}
                    </Button>
                  </div>
                </div>
              )}
            </Tabs>
          </TooltipProvider>
        )}
      </DialogContent>
    </Dialog>
  )
}


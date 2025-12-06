'use client'

import { useState, useEffect, useCallback } from 'react'
import { Monitor, RefreshCw, Maximize2, Minimize2, Play, Square, Camera } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { LoadingState, StatusBadge } from '@/components/shared'

interface BrowserTabProps {
  instanceId: string
}

export function BrowserTab({ instanceId: _instanceId }: BrowserTabProps) {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<string | null>(null)
  const [screenshotName, setScreenshotName] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [screenshotAvailable, setScreenshotAvailable] = useState<boolean | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [interactiveBrowserRunning, setInteractiveBrowserRunning] = useState(false)
  const [browserLoading, setBrowserLoading] = useState(false)

  // Check if screenshots are available before trying to load
  const checkScreenshotAvailability = async () => {
    try {
      const res = await fetch('/api/bot/browser-view?check=true')
      const data = await res.json()
      setScreenshotAvailable(data.available === true)
      return data.available === true
    } catch {
      setScreenshotAvailable(false)
      return false
    }
  }

  const fetchScreenshot = useCallback(async () => {
    if (interactiveBrowserRunning) return

    setIsLoading(true)
    try {
      const timestamp = Date.now()
      const response = await fetch(`/api/bot/browser-view?t=${timestamp}`)

      if (response.ok) {
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)
        if (imageUrl) URL.revokeObjectURL(imageUrl)
        setImageUrl(url)
        setLastUpdate(response.headers.get('X-Screenshot-Time') || new Date().toISOString())
        setScreenshotName(response.headers.get('X-Screenshot-Path') || null)
        setScreenshotAvailable(true)
      } else {
        setScreenshotAvailable(false)
      }
    } catch {
      setScreenshotAvailable(false)
    } finally {
      setIsLoading(false)
    }
  }, [imageUrl, interactiveBrowserRunning])

  const checkBrowserStatus = async () => {
    try {
      const res = await fetch('/api/bot/vnc')
      if (res.ok) {
        const data = await res.json()
        setInteractiveBrowserRunning(data.running)
      }
    } catch {
      // Ignore
    }
  }

  const toggleInteractiveBrowser = async () => {
    setBrowserLoading(true)
    try {
      const action = interactiveBrowserRunning ? 'stop' : 'start'
      await fetch(`/api/bot/vnc?action=${action}`, { method: 'POST' })
      await checkBrowserStatus()
    } catch {
      // Ignore
    } finally {
      setBrowserLoading(false)
    }
  }

  useEffect(() => {
    checkBrowserStatus()
    // Check availability first, then fetch if available
    checkScreenshotAvailability().then(available => {
      if (available) fetchScreenshot()
    })
  }, [])

  useEffect(() => {
    if (autoRefresh && !interactiveBrowserRunning && screenshotAvailable) {
      const interval = setInterval(fetchScreenshot, 5000)
      return () => clearInterval(interval)
    }
    return undefined
  }, [autoRefresh, interactiveBrowserRunning, fetchScreenshot, screenshotAvailable])

  return (
    <div className="p-6 space-y-4">
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Monitor className="text-blue-400" size={20} />
          <h2 className="text-lg font-semibold text-white">Browser View</h2>
          {interactiveBrowserRunning && <StatusBadge status="running" size="sm" />}
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
            disabled={interactiveBrowserRunning}
          >
            <RefreshCw size={14} className={autoRefresh ? 'animate-spin' : ''} />
            {autoRefresh ? 'Auto' : 'Manual'}
          </Button>
          
          <Button variant="outline" size="sm" onClick={fetchScreenshot} disabled={isLoading}>
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </Button>
          
          <Button variant="outline" size="sm" onClick={() => setIsFullscreen(!isFullscreen)}>
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </Button>
          
          <Button
            variant={interactiveBrowserRunning ? 'destructive' : 'default'}
            size="sm"
            onClick={toggleInteractiveBrowser}
            disabled={browserLoading}
          >
            {browserLoading ? '...' : interactiveBrowserRunning ? (
              <><Square size={14} className="mr-1" />Stop VNC</>
            ) : (
              <><Play size={14} className="mr-1" />Start VNC</>
            )}
          </Button>
        </div>
      </div>

      {/* Screenshot Display */}
      <div className={`bg-slate-800 border border-slate-700 rounded-lg overflow-hidden ${isFullscreen ? 'fixed inset-4 z-50' : ''}`}>
        {isFullscreen && (
          <div className="absolute top-2 right-2 z-10">
            <Button variant="outline" size="sm" onClick={() => setIsFullscreen(false)}>
              <Minimize2 size={14} />
            </Button>
          </div>
        )}

        {interactiveBrowserRunning ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <div className="text-6xl">🖥️</div>
            <div className="text-white text-lg font-semibold">Interactive Browser Active</div>
            <div className="text-slate-400 text-sm">Check your desktop for the browser window</div>
            <div className="text-slate-500 text-xs">Screenshot capture is paused during interactive mode</div>
          </div>
        ) : screenshotAvailable === false ? (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Camera className="w-16 h-16 text-slate-600" />
            <div className="text-white text-lg font-semibold">No Screenshots Available</div>
            <div className="text-slate-400 text-sm text-center max-w-md">
              Screenshots are captured during trading cycles when the bot analyzes charts.
              Start the bot to begin capturing.
            </div>
            <Button variant="outline" size="sm" onClick={fetchScreenshot} className="mt-2">
              <RefreshCw size={14} className="mr-2" /> Check Again
            </Button>
          </div>
        ) : imageUrl ? (
          <>
            <img src={imageUrl} alt="Browser View" className="w-full h-auto" />
            {(lastUpdate || screenshotName) && (
              <div className="bg-slate-900 px-3 py-2 text-xs text-slate-400 flex justify-between">
                <span>{screenshotName || 'screenshot.png'}</span>
                {lastUpdate && <span>Updated: {new Date(lastUpdate).toLocaleTimeString()}</span>}
              </div>
            )}
          </>
        ) : isLoading ? (
          <LoadingState text="Loading screenshot..." />
        ) : (
          <div className="flex flex-col items-center justify-center py-20 gap-4">
            <Camera className="w-16 h-16 text-slate-600" />
            <div className="text-slate-400">Checking for screenshots...</div>
          </div>
        )}
      </div>
    </div>
  )
}


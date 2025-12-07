'use client'

import { useState, useEffect } from 'react'
import { X, CheckCircle, RefreshCw, Info, Power, Monitor } from 'lucide-react'

interface VncLoginModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  loginState: {
    state: 'idle' | 'waiting_for_login' | 'login_confirmed' | 'browser_opened'
    message: string | null
    browser_opened: boolean
  }
}

export default function VncLoginModal({ isOpen, onClose, onConfirm }: VncLoginModalProps) {
  const [confirming, setConfirming] = useState(false)
  const [startingVnc, setStartingVnc] = useState(false)
  const [startingBrowser, setStartingBrowser] = useState(false)
  const [killingVnc, setKillingVnc] = useState(false)
  const [vncEnabled, setVncEnabled] = useState<boolean | null>(null)
  const [vncRunning, setVncRunning] = useState<boolean>(false)

  // Check VNC status when modal opens
  useEffect(() => {
    if (isOpen) {
      checkVncStatus()
      // Poll VNC status every 3 seconds while modal is open
      const interval = setInterval(checkVncStatus, 3000)
      return () => clearInterval(interval)
    }
    return () => {} // Return empty cleanup function for non-open case
  }, [isOpen])

  const checkVncStatus = async () => {
    try {
      const response = await fetch('/api/vnc/status')
      const data = await response.json()
      setVncEnabled(data.enableVnc || false)
      setVncRunning(data.running || false)
      console.log('VNC status:', { enabled: data.enableVnc, running: data.running })
    } catch (error) {
      console.error('Failed to check VNC status:', error)
      setVncEnabled(false)
      setVncRunning(false)
    }
  }

  const handleStartVnc = async () => {
    setStartingVnc(true)
    try {
      console.log('[VNC Modal] Starting VNC services...')
      const response = await fetch('/api/vnc/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'start' })
      })
      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to start VNC services')
      }

      console.log('[VNC Modal] ✅ VNC services started')
      // Status will update via polling
    } catch (error) {
      console.error('[VNC Modal] Error starting VNC:', error)
      alert(`Failed to start VNC services: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setStartingVnc(false)
    }
  }

  const handleStartBrowser = async () => {
    setStartingBrowser(true)
    try {
      console.log('[VNC Modal] Signaling Python to open browser...')
      const response = await fetch('/api/vnc/browser-ready', {
        method: 'POST'
      })
      const data = await response.json()

      if (!data.success) {
        throw new Error(data.error || 'Failed to signal browser open')
      }

      console.log('[VNC Modal] ✅ Browser open signal sent')
      // Don't set browserStarted - allow multiple clicks if browser crashes
    } catch (error) {
      console.error('[VNC Modal] Error starting browser:', error)
      alert(`Failed to start browser: ${error instanceof Error ? error.message : 'Unknown error'}`)
    } finally {
      setStartingBrowser(false)
    }
  }

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await onConfirm()
    } finally {
      setConfirming(false)
    }
  }

  const handleKillVnc = async () => {
    setKillingVnc(true)
    try {
      const response = await fetch('/api/vnc/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stop' })
      })
      const data = await response.json()

      if (data.success) {
        alert('VNC services stopped successfully. Browser session closed.')
      } else {
        alert(`Failed to stop VNC: ${data.error || 'Unknown error'}`)
      }
    } catch (error) {
      console.error('Failed to kill VNC:', error)
      alert('Failed to stop VNC services. Check console for details.')
    } finally {
      setKillingVnc(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="bg-slate-800 border border-slate-600 rounded-lg shadow-2xl w-full max-w-6xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-600">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-600/20 flex items-center justify-center">
              🔐
            </div>
            <div>
              <h2 className="text-xl font-bold text-white flex items-center gap-3">
                TradingView Login
                {/* VNC Status Indicator */}
                {vncEnabled !== null && (
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    vncEnabled
                      ? (vncRunning ? 'bg-green-600/20 text-green-400 border border-green-600/50' : 'bg-blue-600/20 text-blue-400 border border-blue-600/50')
                      : 'bg-slate-600/20 text-slate-400 border border-slate-600/50'
                  }`}>
                    {vncEnabled ? (vncRunning ? '● VNC Running' : '○ VNC Enabled') : 'Local Mode'}
                  </span>
                )}
              </h2>
              <p className="text-sm text-slate-400">Log in to TradingView to continue</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-700 rounded-lg transition"
          >
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        {/* Content - Step-by-step instructions */}
        <div className="flex-1 overflow-auto p-4">
          <div className="h-full flex flex-col gap-4">
            {/* VNC Connection Info */}
            {vncEnabled && (
              <div className="bg-slate-900/50 border border-slate-600 rounded-lg p-4">
                <p className="font-mono text-xs text-slate-400 mb-1">VNC Server Address:</p>
                <p className="font-mono text-base text-white">
                  Check Railway TCP Proxy settings for connection details
                </p>
                <p className="font-mono text-xs text-slate-400 mt-1">
                  Default port: 5900 (x11vnc)
                </p>
              </div>
            )}

            {/* Step-by-step Instructions */}
            <div className="bg-blue-900/30 border border-blue-600 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <Info className="w-6 h-6 text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-blue-100 w-full">
                  <strong className="text-base block mb-3">📋 Step-by-Step Instructions</strong>

                  <div className="space-y-3">
                    {/* Step 1 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">1</span>
                      <div className="flex-1">
                        <p className="font-semibold">Press "Start VNC" button below</p>
                        <p className="text-xs text-blue-200 mt-1">This starts the VNC server (Xvfb + x11vnc)</p>
                      </div>
                    </div>

                    {/* Step 2 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">2</span>
                      <div className="flex-1">
                        <p className="font-semibold">Connect to VNC using a VNC client</p>
                        <p className="text-xs text-blue-200 mt-1">
                          Use the address above. Recommended clients:
                          <a href="https://www.realvnc.com/en/connect/download/viewer/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline ml-1">RealVNC Viewer</a> or
                          <a href="https://tigervnc.org/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline ml-1">TigerVNC</a>
                        </p>
                      </div>
                    </div>

                    {/* Step 3 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">3</span>
                      <div className="flex-1">
                        <p className="font-semibold">Press "Start Browser" button below</p>
                        <p className="text-xs text-blue-200 mt-1">This opens TradingView in the VNC session</p>
                      </div>
                    </div>

                    {/* Step 4 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center font-bold">4</span>
                      <div className="flex-1">
                        <p className="font-semibold">Login to TradingView in the VNC window</p>
                        <p className="text-xs text-blue-200 mt-1">Complete the login process in your VNC client</p>
                      </div>
                    </div>

                    {/* Step 5 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-green-600 text-white text-xs flex items-center justify-center font-bold">5</span>
                      <div className="flex-1">
                        <p className="font-semibold">Press "Confirm Login" button below</p>
                        <p className="text-xs text-green-200 mt-1">This saves your session and resumes the bot</p>
                      </div>
                    </div>

                    {/* Step 6 */}
                    <div className="flex items-start gap-2">
                      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-red-600 text-white text-xs flex items-center justify-center font-bold">6</span>
                      <div className="flex-1">
                        <p className="font-semibold">Press "Kill VNC" button to cleanup</p>
                        <p className="text-xs text-red-200 mt-1">Stops VNC services to free resources</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer - 4 Action Buttons (ALWAYS ACTIVE AND FUNCTIONAL) */}
        <div className="p-4 border-t border-slate-600">
          <div className="grid grid-cols-2 gap-3 mb-3">
            {/* Button 1: Start VNC - ALWAYS ACTIVE */}
            <button
              onClick={handleStartVnc}
              disabled={startingVnc}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
              title="Start VNC services (Xvfb + x11vnc)"
            >
              {startingVnc ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Power className="w-4 h-4" />
                  1. Start VNC
                </>
              )}
            </button>

            {/* Button 2: Start Browser - ALWAYS ACTIVE */}
            <button
              onClick={handleStartBrowser}
              disabled={startingBrowser}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
              title="Open browser in VNC session"
            >
              {startingBrowser ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Monitor className="w-4 h-4" />
                  2. Start Browser
                </>
              )}
            </button>

            {/* Button 3: Confirm Login - ALWAYS ACTIVE */}
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
              title="Confirm login completed"
            >
              {confirming ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Confirming...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  3. Confirm Login
                </>
              )}
            </button>

            {/* Button 4: Kill VNC - ALWAYS ACTIVE */}
            <button
              onClick={handleKillVnc}
              disabled={killingVnc}
              className="flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
              title="Stop VNC services and cleanup"
            >
              {killingVnc ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Stopping...
                </>
              ) : (
                <>
                  <Power className="w-4 h-4" />
                  4. Kill VNC
                </>
              )}
            </button>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition text-white"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}


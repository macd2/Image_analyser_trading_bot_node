'use client'

import { useState } from 'react'
import { X, CheckCircle, RefreshCw, Info, Power } from 'lucide-react'

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
  const [killingVnc, setKillingVnc] = useState(false)

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
              <h2 className="text-xl font-bold text-white">TradingView Login</h2>
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

        {/* Content - Static Instructions */}
        <div className="flex-1 overflow-auto p-4">
          <div className="h-full flex flex-col gap-4">
            {/* Connection Instructions */}
            <div className="bg-blue-900/30 border border-blue-600 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <Info className="w-6 h-6 text-blue-400 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-blue-100">
                  <strong className="text-base block mb-2">Connect with VNC Client</strong>
                  <p className="mb-3">
                    Use a desktop VNC client to connect to the browser for manual TradingView login.
                  </p>

                  <div className="bg-slate-900/50 rounded-lg p-3 mb-3">
                    <p className="font-mono text-xs text-green-400 mb-1">VNC Server Address:</p>
                    <p className="font-mono text-base text-white">
                      Check Railway TCP Proxy settings for connection details
                    </p>
                    <p className="font-mono text-xs text-slate-400 mt-1">
                      Default port: 5900 (x11vnc)
                    </p>
                  </div>

                  <div className="space-y-2 mb-3">
                    <p className="font-semibold">Steps:</p>
                    <ol className="list-decimal list-inside space-y-1 ml-2">
                      <li>Download a VNC client:
                        <ul className="list-disc list-inside ml-4 text-xs mt-1">
                          <li><a href="https://www.realvnc.com/en/connect/download/viewer/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">RealVNC Viewer</a> (Windows/Mac/Linux)</li>
                          <li><a href="https://tigervnc.org/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">TigerVNC</a> (Open Source)</li>
                        </ul>
                      </li>
                      <li>Connect to the Railway TCP Proxy address (port 5900)</li>
                      <li>No password required</li>
                      <li>Log in to TradingView in the VNC window</li>
                      <li>Return here and click &quot;Confirm Login&quot; below</li>
                      <li>Click &quot;Kill VNC&quot; to stop services when done</li>
                    </ol>
                  </div>

                  <div className="bg-amber-900/30 border border-amber-600 rounded-lg p-3">
                    <p className="font-semibold text-amber-200 mb-1">⚠️ Important:</p>
                    <ul className="list-disc list-inside space-y-1 text-xs text-amber-100">
                      <li>Browser may take 10-15 seconds to appear in VNC</li>
                      <li>If browser crashes, click &quot;Kill VNC&quot; and try again</li>
                      <li>Always click &quot;Kill VNC&quot; when done to free resources</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer - Always visible buttons */}
        <div className="flex items-center justify-between p-4 border-t border-slate-600">
          {/* Left side - Kill VNC button (always visible) */}
          <button
            onClick={handleKillVnc}
            disabled={killingVnc || confirming}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
            title="Stop VNC services and close browser session"
          >
            {killingVnc ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Stopping...
              </>
            ) : (
              <>
                <Power className="w-4 h-4" />
                Kill VNC
              </>
            )}
          </button>

          {/* Right side - Cancel and Confirm buttons (always visible) */}
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={confirming}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium"
            >
              {confirming ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  Confirming...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Confirm Login
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}


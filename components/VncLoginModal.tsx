'use client'

import { useState, useEffect } from 'react'
import { X, CheckCircle, RefreshCw, AlertTriangle, Info } from 'lucide-react'

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

export default function VncLoginModal({ isOpen, onClose, onConfirm, loginState }: VncLoginModalProps) {
  const [vncAvailable, setVncAvailable] = useState(false)
  const [vncUrl, setVncUrl] = useState('')
  const [loading, setLoading] = useState(true)
  const [confirming, setConfirming] = useState(false)

  // Check VNC availability when modal opens
  useEffect(() => {
    if (isOpen) {
      checkVncStatus()
    }
  }, [isOpen])

  const checkVncStatus = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/vnc/status')
      const data = await response.json()
      
      setVncAvailable(data.available)
      setVncUrl(data.vncUrl || '')
    } catch (error) {
      console.error('Failed to check VNC status:', error)
      setVncAvailable(false)
    } finally {
      setLoading(false)
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

        {/* Content */}
        <div className="flex-1 overflow-hidden p-4">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <RefreshCw className="w-12 h-12 text-blue-400 animate-spin mx-auto mb-4" />
                <p className="text-slate-300">Connecting to VNC server...</p>
              </div>
            </div>
          ) : !vncAvailable ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <AlertTriangle className="w-16 h-16 text-amber-400 mx-auto mb-4" />
                <h3 className="text-xl font-bold text-white mb-2">VNC Not Available</h3>
                <p className="text-slate-300 mb-4">
                  VNC server is not available. This feature only works on Railway deployments.
                </p>
                <p className="text-sm text-slate-400">
                  For local development, use the manual login flow or upload a session.
                </p>
              </div>
            </div>
          ) : (
            <div className="h-full flex flex-col gap-4">
              {/* Connection Instructions */}
              <div className="bg-blue-900/30 border border-blue-600 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <Info className="w-6 h-6 text-blue-400 mt-0.5 flex-shrink-0" />
                  <div className="text-sm text-blue-100">
                    <strong className="text-base block mb-2">Connect with VNC Client</strong>
                    <p className="mb-3">
                      Use a VNC client (RealVNC, TigerVNC, TightVNC, or noVNC web client) to connect to the browser.
                    </p>

                    <div className="bg-slate-900/50 rounded-lg p-3 mb-3">
                      <p className="font-mono text-xs text-green-400 mb-1">VNC Server Address:</p>
                      <p className="font-mono text-base text-white break-all">
                        {vncUrl || 'Loading...'}
                      </p>
                    </div>

                    <div className="space-y-2 mb-3">
                      <p className="font-semibold">Option 1: Desktop VNC Client (Recommended)</p>
                      <ol className="list-decimal list-inside space-y-1 ml-2">
                        <li>Download a VNC client:
                          <ul className="list-disc list-inside ml-4 text-xs mt-1">
                            <li><a href="https://www.realvnc.com/en/connect/download/viewer/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">RealVNC Viewer</a> (Windows/Mac/Linux)</li>
                            <li><a href="https://tigervnc.org/" target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">TigerVNC</a> (Open Source)</li>
                          </ul>
                        </li>
                        <li>Connect to the address above</li>
                        <li>No password required</li>
                        <li>Log in to TradingView in the VNC window</li>
                        <li>Return here and click &quot;Confirm Login&quot;</li>
                      </ol>
                    </div>

                    <div className="space-y-2">
                      <p className="font-semibold">Option 2: Web Browser (noVNC)</p>
                      <ol className="list-decimal list-inside space-y-1 ml-2">
                        <li>Open the VNC web client:
                          {vncUrl && (
                            <a
                              href={vncUrl.replace(/:\d+$/, '') + '/vnc.html?host=' + vncUrl.split(':')[0] + '&port=' + vncUrl.split(':')[1] + '&autoconnect=true'}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-400 hover:underline ml-2"
                            >
                              Open noVNC
                            </a>
                          )}
                        </li>
                        <li>Log in to TradingView</li>
                        <li>Return here and click &quot;Confirm Login&quot;</li>
                      </ol>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-slate-600">
          <div className="text-sm text-slate-400">
            {loginState.browser_opened && (
              <span className="flex items-center gap-2 text-green-400">
                <CheckCircle className="w-4 h-4" />
                Browser opened - complete login above
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleConfirm}
              disabled={!loginState.browser_opened || confirming}
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


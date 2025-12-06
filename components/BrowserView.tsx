'use client';

import { useState, useEffect, useCallback } from 'react';
import { Monitor, RefreshCw, Maximize2, Minimize2, Play, Square, Info, Bot } from 'lucide-react';

export default function BrowserView() {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false); // Manual by default
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [interactiveBrowserRunning, setInteractiveBrowserRunning] = useState(false);
  const [browserLoading, setBrowserLoading] = useState(false);
  const [botRunning, setBotRunning] = useState(false); // Track if trading bot is running

  // Only fetch screenshots when bot is running (not interactive browser)
  const fetchScreenshot = useCallback(async () => {
    // Don't fetch if interactive browser is running - user sees desktop
    if (interactiveBrowserRunning) {
      return;
    }

    setIsLoading(true);
    try {
      const timestamp = Date.now();
      const response = await fetch(`/api/bot/browser-view?t=${timestamp}`);

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        if (imageUrl) URL.revokeObjectURL(imageUrl);
        setImageUrl(url);
        setLastUpdate(response.headers.get('X-Screenshot-Time') || new Date().toISOString());
        setError(null);
      } else {
        const data = await response.json();
        setError(data.error || 'No screenshot available');
      }
    } catch {
      setError('Failed to fetch browser view');
    } finally {
      setIsLoading(false);
    }
  }, [imageUrl, interactiveBrowserRunning]);

  // Check interactive browser status
  const checkInteractiveBrowserStatus = async () => {
    try {
      const res = await fetch('/api/bot/vnc');
      const data = await res.json();
      setInteractiveBrowserRunning(data.running);
    } catch { setInteractiveBrowserRunning(false); }
  };

  // Check if trading bot is running
  const checkBotStatus = async () => {
    try {
      const res = await fetch('/api/bot/status');
      const data = await res.json();
      setBotRunning(data.running === true);
    } catch { setBotRunning(false); }
  };

  const toggleInteractiveBrowser = async () => {
    setBrowserLoading(true);
    try {
      const res = await fetch('/api/bot/vnc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: interactiveBrowserRunning ? 'stop' : 'start' }),
      });
      const data = await res.json();
      if (data.success) {
        setInteractiveBrowserRunning(!interactiveBrowserRunning);
        // Clear screenshot when interactive browser starts
        if (!interactiveBrowserRunning) {
          setImageUrl(null);
          setError('Interactive browser open on your desktop - login manually');
        }
      }
    } catch (err) {
      console.error('Browser toggle failed:', err);
    } finally {
      setBrowserLoading(false);
    }
  };

  useEffect(() => {
    checkInteractiveBrowserStatus();
    checkBotStatus();

    const statusInterval = setInterval(() => {
      checkInteractiveBrowserStatus();
      checkBotStatus();
    }, 5000);

    // Only auto-refresh screenshots when bot is running AND auto mode is on AND interactive is off
    if (autoRefresh && botRunning && !interactiveBrowserRunning) {
      fetchScreenshot(); // Initial fetch
      const screenshotInterval = setInterval(fetchScreenshot, 1000);
      return () => {
        clearInterval(statusInterval);
        clearInterval(screenshotInterval);
      };
    }

    return () => clearInterval(statusInterval);
  }, [autoRefresh, botRunning, interactiveBrowserRunning, fetchScreenshot]);

  useEffect(() => {
    return () => { if (imageUrl) URL.revokeObjectURL(imageUrl); };
  }, [imageUrl]);

  return (
    <div className={`space-y-4 ${isFullscreen ? 'fixed inset-4 z-50 bg-slate-900 p-4 rounded-xl' : ''}`}>
      {/* Header */}
      <div className="bg-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Monitor className="w-6 h-6 text-blue-400" />
            <h2 className="text-xl font-bold text-white">Browser View</h2>
            {/* Status badges */}
            {interactiveBrowserRunning && (
              <span className="px-2 py-1 bg-yellow-600 text-white text-xs rounded-full">🖥️ Interactive Mode</span>
            )}
            {botRunning && !interactiveBrowserRunning && (
              <span className="px-2 py-1 bg-green-600 text-white text-xs rounded-full">🤖 Bot Running</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleInteractiveBrowser}
              disabled={browserLoading || botRunning}
              title={botRunning ? 'Stop the bot first to open interactive browser' : ''}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition ${
                interactiveBrowserRunning
                  ? 'bg-red-600 hover:bg-red-700 text-white'
                  : 'bg-blue-600 hover:bg-blue-700 text-white'
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {browserLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : interactiveBrowserRunning ? (
                <Square className="w-4 h-4" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              {interactiveBrowserRunning ? 'Stop & Save Session' : 'Open Interactive Browser'}
            </button>
            {/* Only show auto refresh when bot is running */}
            {botRunning && !interactiveBrowserRunning && (
              <button
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg transition ${
                  autoRefresh ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
                {autoRefresh ? 'Live' : 'Manual'}
              </button>
            )}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              className="p-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition"
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Interactive browser alert */}
        {interactiveBrowserRunning && (
          <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-600 rounded-lg flex items-start gap-3">
            <Info className="w-5 h-5 text-yellow-400 mt-0.5" />
            <div className="text-sm text-yellow-200">
              <strong>Interactive browser is open on your desktop!</strong><br/>
              Log in to TradingView manually. When done, click &quot;Stop &amp; Save Session&quot; to capture your login cookies.
              <br/><span className="text-yellow-400">No screenshots are shown here - look at your desktop.</span>
            </div>
          </div>
        )}

        {/* Bot running alert */}
        {botRunning && !interactiveBrowserRunning && (
          <div className="mb-4 p-3 bg-green-900/30 border border-green-600 rounded-lg flex items-start gap-3">
            <Bot className="w-5 h-5 text-green-400 mt-0.5" />
            <div className="text-sm text-green-200">
              <strong>Trading bot is running!</strong> Live browser screenshots from chart captures are shown below.
              <br/><span className="text-green-400">Toggle &quot;Live&quot; mode to auto-refresh every second.</span>
            </div>
          </div>
        )}

        {/* Status bar - only when not in interactive mode */}
        {!interactiveBrowserRunning && (
          <div className="flex items-center gap-4 mb-4">
            {lastUpdate && (
              <span className="text-xs text-slate-400 bg-slate-700 px-2 py-1 rounded">
                Updated: {new Date(lastUpdate).toLocaleTimeString()}
              </span>
            )}
            <button
              onClick={fetchScreenshot}
              disabled={isLoading || !botRunning}
              title={!botRunning ? 'Start the bot to see screenshots' : 'Refresh screenshot'}
              className="p-2 bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        )}

        {/* Screenshot display */}
        <div className={`relative bg-slate-900 rounded-lg overflow-hidden border border-slate-700 ${isFullscreen ? 'h-[calc(100vh-14rem)]' : 'h-[600px]'}`}>
          {interactiveBrowserRunning ? (
            // Interactive mode - no screenshot, just message
            <div className="flex items-center justify-center h-full text-slate-400">
              <div className="text-center">
                <Monitor className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p className="text-lg text-yellow-400">🖥️ Interactive Browser Active</p>
                <p className="text-sm mt-2 text-slate-400">
                  Look at your desktop - browser window is open there.
                </p>
                <p className="text-sm mt-1 text-slate-500">
                  Log in to TradingView, then click &quot;Stop &amp; Save Session&quot;
                </p>
              </div>
            </div>
          ) : !botRunning ? (
            // Bot not running - show instructions
            <div className="flex items-center justify-center h-full text-slate-400">
              <div className="text-center">
                <Monitor className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p className="text-lg">No Browser Activity</p>
                <p className="text-sm mt-2 text-slate-500">
                  Start the trading bot to see live chart captures, or use &quot;Open Interactive Browser&quot; for manual login.
                </p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full text-slate-400">
              <div className="text-center">
                <Monitor className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p className="text-lg">{error}</p>
                <p className="text-sm mt-2 text-slate-500">
                  Waiting for bot to capture charts...
                </p>
              </div>
            </div>
          ) : imageUrl ? (
            <img src={imageUrl} alt="Browser View" className="w-full h-full object-contain" />
          ) : (
            <div className="flex items-center justify-center h-full text-slate-400">
              <RefreshCw className="w-10 h-10 animate-spin" />
            </div>
          )}
        </div>

        {/* Help text */}
        <div className="mt-3 p-3 bg-slate-700/50 rounded-lg">
          <p className="text-xs text-slate-400">
            <strong>💡 How it works:</strong>
          </p>
          <ul className="text-xs text-slate-500 mt-1 space-y-1">
            <li>• <strong>Interactive Browser:</strong> Opens a real browser on your desktop for manual TradingView login. Session is saved when you close it.</li>
            <li>• <strong>Bot Running:</strong> Shows live screenshots from the bot&apos;s automated chart captures.</li>
            <li>• Sessions are encrypted and stored in the database for reuse.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}


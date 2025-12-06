'use client'

import { RefreshCw } from 'lucide-react'

interface ConnectionStatusProps {
  connected: boolean;
  lastUpdate: Date | null;
  onReconnect: () => void;
}

export default function ConnectionStatus({ connected, lastUpdate, onReconnect }: ConnectionStatusProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 text-sm">
        <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
        <span className={connected ? 'text-green-400' : 'text-red-400'}>
          {connected ? 'Live' : 'Disconnected'}
        </span>
      </div>
      {lastUpdate && (
        <span className="text-xs text-slate-500">
          {lastUpdate.toLocaleTimeString()}
        </span>
      )}
      <button
        onClick={onReconnect}
        className="p-1.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 transition"
        title="Reconnect"
      >
        <RefreshCw className="w-3 h-3" />
      </button>
    </div>
  );
}


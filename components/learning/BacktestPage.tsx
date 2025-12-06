'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Play, Square, RefreshCw, CheckCircle, XCircle, Clock, Loader2, AlertCircle, Settings2 } from 'lucide-react';

interface BacktestRun {
  runId: string;
  status: 'starting' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  result?: unknown;
  config?: BacktestConfig;
  startedAt: string;
  logs: string[];
}

interface BacktestConfig {
  prompts: string[];
  symbols: string[];
  numImages: number;
  timeframes: string[];
}

const AVAILABLE_TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

export default function BacktestPage() {
  const [prompts, setPrompts] = useState<string[]>([]);
  const [availableSymbols, setAvailableSymbols] = useState<string[]>([]);
  const [selectedPrompts, setSelectedPrompts] = useState<string[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>(['1h']);
  const [numImages, setNumImages] = useState(10);
  const [currentRun, setCurrentRun] = useState<BacktestRun | null>(null);
  const [runHistory, setRunHistory] = useState<BacktestRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Fetch available prompts and symbols
  useEffect(() => {
    fetch('/api/learning/prompts')
      .then(res => res.json())
      .then(data => { if (data.prompts) setPrompts(data.prompts); })
      .catch(console.error);

    fetch('/api/backtest/symbols')
      .then(res => res.json())
      .then(data => {
        if (data.symbols) {
          setAvailableSymbols(data.symbols);
          // Auto-select first 2 symbols
          setSelectedSymbols(data.symbols.slice(0, 2));
        }
      })
      .catch(console.error);
  }, []);

  const toggleItem = (item: string, list: string[], setList: (l: string[]) => void) => {
    setList(list.includes(item) ? list.filter(i => i !== item) : [...list, item]);
  };

  // Poll for status updates
  const pollStatus = useCallback(async (runId: string) => {
    try {
      const res = await fetch(`/api/backtest?runId=${runId}`);
      const data = await res.json();
      
      setCurrentRun(prev => prev ? {
        ...prev,
        status: data.status,
        progress: data.progress || 0,
        result: data.result,
        logs: (data.logs as string[]) || prev.logs,
      } : null);

      if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
        if (pollRef.current) clearInterval(pollRef.current);
        // Move to history
        setRunHistory(prev => [{ ...data, runId, startedAt: new Date().toISOString(), logs: [] }, ...prev.slice(0, 9)]);
      }
    } catch (e) {
      console.error('Poll error:', e);
    }
  }, []);

  const startBacktest = async () => {
    if (selectedPrompts.length === 0) { setError('Select at least one prompt'); return; }
    if (selectedSymbols.length === 0) { setError('Select at least one symbol'); return; }
    setError(null);

    const config: BacktestConfig = {
      prompts: selectedPrompts,
      symbols: selectedSymbols,
      numImages,
      timeframes: selectedTimeframes,
    };

    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      const data = await res.json();
      
      if (!data.success) throw new Error(data.error);

      const newRun: BacktestRun = {
        runId: data.runId,
        status: 'starting',
        progress: 0,
        config,
        startedAt: new Date().toISOString(),
        logs: [],
      };
      setCurrentRun(newRun);

      // Start polling (faster for better real-time feel)
      pollRef.current = setInterval(() => pollStatus(data.runId), 500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start backtest');
    }
  };

  const cancelBacktest = async () => {
    if (!currentRun) return;
    try {
      await fetch(`/api/backtest?runId=${currentRun.runId}`, { method: 'DELETE' });
      if (pollRef.current) clearInterval(pollRef.current);
      setCurrentRun(prev => prev ? { ...prev, status: 'cancelled' } : null);
    } catch (e) {
      console.error('Cancel error:', e);
    }
  };

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (currentRun?.logs.length) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentRun?.logs]);

  const isRunning = currentRun && ['starting', 'running'].includes(currentRun.status);
  const estimatedTime = Math.ceil((selectedPrompts.length * selectedSymbols.length * numImages * 3) / 60);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <Settings2 className="text-blue-400" /> Run Backtest
          </h2>
          <p className="text-slate-400 text-sm mt-1">Test prompts against historical chart images</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Configuration */}
        <div className="lg:col-span-2 space-y-4">
          <ConfigCard title="Prompts" count={selectedPrompts.length}>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              {prompts.length === 0 ? (
                <p className="text-slate-500 text-sm">Loading prompts...</p>
              ) : prompts.map(p => (
                <ToggleButton key={p} label={p.replace('get_analyzer_prompt_', '').slice(0, 20)}
                  active={selectedPrompts.includes(p)} onClick={() => toggleItem(p, selectedPrompts, setSelectedPrompts)}
                  color="blue" disabled={!!isRunning} />
              ))}
            </div>
          </ConfigCard>

          <ConfigCard title="Symbols" count={selectedSymbols.length}>
            <div className="flex flex-wrap gap-2">
              {availableSymbols.length === 0 ? (
                <div className="text-slate-500 text-sm">Loading symbols...</div>
              ) : (
                availableSymbols.map(s => (
                  <ToggleButton key={s} label={s.replace('USDT', '')}
                    active={selectedSymbols.includes(s)} onClick={() => toggleItem(s, selectedSymbols, setSelectedSymbols)}
                    color="green" disabled={!!isRunning} />
                ))
              )}
            </div>
          </ConfigCard>
        </div>
        {/* Right: Run Panel */}
        <div className="space-y-4">
          {/* Timeframes & Images */}
          <ConfigCard title="Timeframes" count={selectedTimeframes.length}>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_TIMEFRAMES.map(t => (
                <ToggleButton key={t} label={t}
                  active={selectedTimeframes.includes(t)} onClick={() => toggleItem(t, selectedTimeframes, setSelectedTimeframes)}
                  color="purple" disabled={!!isRunning} />
              ))}
            </div>
          </ConfigCard>

          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-white font-medium">Images per Symbol</h3>
              <span className="text-blue-400 font-mono">{numImages}</span>
            </div>
            <input type="range" min={1} max={50} value={numImages} onChange={e => setNumImages(Number(e.target.value))}
              disabled={!!isRunning} className="w-full accent-blue-500" />
            <div className="flex justify-between text-xs text-slate-500 mt-1"><span>1</span><span>50</span></div>
          </div>

          {/* Estimate */}
          <div className="bg-slate-700/50 rounded-lg p-3 text-sm">
            <div className="flex items-center gap-2 text-slate-300">
              <Clock size={14} />
              <span>Est. time: <b className="text-white">{estimatedTime} min</b></span>
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {selectedPrompts.length} prompts × {selectedSymbols.length} symbols × {numImages} images
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-900/30 border border-red-500 rounded-lg p-3 flex items-start gap-2">
              <AlertCircle size={16} className="text-red-400 mt-0.5" />
              <span className="text-red-400 text-sm">{error}</span>
            </div>
          )}

          {/* Run Button */}
          <button onClick={isRunning ? cancelBacktest : startBacktest}
            disabled={!isRunning && (selectedPrompts.length === 0 || selectedSymbols.length === 0)}
            className={`w-full flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition ${
              isRunning ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
            }`}>
            {isRunning ? <><Square size={18} /> Stop Backtest</> : <><Play size={18} /> Start Backtest</>}
          </button>
        </div>
      </div>

      {/* Progress Panel */}
      {currentRun && (
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <StatusBadge status={currentRun.status} />
              <span className="text-slate-400 text-sm font-mono">{currentRun.runId}</span>
            </div>
            <span className="text-white font-bold text-xl">{currentRun.progress}%</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-4 overflow-hidden mb-4">
            <div className={`h-full transition-all duration-300 ${
              currentRun.status === 'failed' ? 'bg-red-500'
                : currentRun.status === 'completed' ? 'bg-green-500' : 'bg-blue-500'
            }`} style={{ width: `${currentRun.progress}%` }} />
          </div>
          {currentRun.config && (
            <div className="mb-3 text-xs text-slate-500">
              Testing: {currentRun.config.prompts.join(', ')} on {currentRun.config.symbols.join(', ')}
            </div>
          )}

          {/* Real-time Logs */}
          <LogsPanel logs={currentRun.logs} status={currentRun.status} logsEndRef={logsEndRef} />

          {currentRun.result !== undefined && currentRun.status === 'completed' ? (
            <div className="mt-3 p-3 bg-green-900/20 border border-green-700 rounded text-sm text-green-400">
              ✓ Backtest completed! Results saved to database.
            </div>
          ) : null}
          {currentRun.result !== undefined && currentRun.status === 'failed' ? (
            <div className="mt-3 p-3 bg-red-900/20 border border-red-700 rounded text-sm text-red-400">
              ✗ {typeof currentRun.result === 'object' && currentRun.result !== null && 'error' in currentRun.result
                  ? String((currentRun.result as {error: string}).error) : 'Unknown error'}
            </div>
          ) : null}
        </div>
      )}

      {/* History */}
      {runHistory.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <h3 className="text-white font-medium mb-3">Recent Runs</h3>
          <div className="space-y-2">
            {runHistory.map(run => (
              <div key={run.runId} className="flex items-center justify-between p-2 bg-slate-700/50 rounded text-sm">
                <div className="flex items-center gap-2">
                  <StatusBadge status={run.status} />
                  <span className="text-slate-300 font-mono">{run.runId}</span>
                </div>
                <span className="text-slate-500">{new Date(run.startedAt).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const ConfigCard = ({ title, count, children }: { title: string; count: number; children: React.ReactNode }) => (
  <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
    <div className="flex justify-between items-center mb-3">
      <h3 className="text-white font-medium">{title}</h3>
      <span className="text-xs text-slate-400 bg-slate-700 px-2 py-1 rounded">{count} selected</span>
    </div>
    {children}
  </div>
);

const ToggleButton = ({ label, active, onClick, color, disabled }:
  { label: string; active: boolean; onClick: () => void; color: string; disabled: boolean }) => (
  <button onClick={onClick} disabled={disabled}
    className={`text-xs px-3 py-1.5 rounded transition ${
      active ? (color === 'blue' ? 'bg-blue-600 text-white' : color === 'green' ? 'bg-green-600 text-white' : 'bg-purple-600 text-white')
        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
    } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
    {label}
  </button>
);

const StatusBadge = ({ status }: { status: string }) => {
  const config: Record<string, { icon: typeof CheckCircle; color: string; label: string }> = {
    starting: { icon: Loader2, color: 'text-yellow-400', label: 'Starting' },
    running: { icon: RefreshCw, color: 'text-blue-400', label: 'Running' },
    completed: { icon: CheckCircle, color: 'text-green-400', label: 'Completed' },
    failed: { icon: XCircle, color: 'text-red-400', label: 'Failed' },
    cancelled: { icon: Square, color: 'text-slate-400', label: 'Cancelled' },
  };
  const { icon: Icon, color, label } = config[status] || config.running;
  return (
    <span className={`flex items-center gap-1 ${color}`}>
      <Icon size={14} className={status === 'running' || status === 'starting' ? 'animate-spin' : ''} />
      <span className="text-xs">{label}</span>
    </span>
  );
};

const LogsPanel = ({ logs, status, logsEndRef }: { logs: string[]; status: string; logsEndRef: React.RefObject<HTMLDivElement> }) => {
  if (!logs || logs.length === 0) return null;
  return (
    <div className="mt-3 bg-slate-900/50 rounded border border-slate-700 p-3 max-h-64 overflow-y-auto">
      <div className="flex items-center gap-2 mb-2 text-xs text-slate-400 sticky top-0 bg-slate-900/90 pb-1">
        <Loader2 size={12} className={status === 'running' ? 'animate-spin' : ''} />
        <span>Live Output ({logs.length} lines)</span>
      </div>
      <div className="font-mono text-xs space-y-0.5">
        {logs.slice(-20).map((log, i) => (
          <div key={i} className={`${
            log.includes('Error') || log.includes('Failed') ? 'text-red-400' :
            log.includes('Completed') || log.includes('Success') ? 'text-green-400' :
            log.startsWith('[') ? 'text-blue-400' : 'text-slate-400'
          }`}>
            {log}
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
};


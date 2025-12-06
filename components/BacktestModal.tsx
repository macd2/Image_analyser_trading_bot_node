'use client';

import { useState } from 'react';
import { X, Play, Loader2 } from 'lucide-react';

interface BacktestModalProps {
  isOpen: boolean;
  onClose: () => void;
  prompts: string[];
  onRunBacktest: (config: BacktestConfig) => Promise<void>;
}

export interface BacktestConfig {
  prompts: string[];
  symbols: string[];
  numImages: number;
  timeframes: string[];
}

const AVAILABLE_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
  'AVAXUSDT', 'ADAUSDT', 'LINKUSDT', 'DOTUSDT', 'MATICUSDT'
];

const AVAILABLE_TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

export default function BacktestModal({ isOpen, onClose, prompts, onRunBacktest }: BacktestModalProps) {
  const [selectedPrompts, setSelectedPrompts] = useState<string[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['BTCUSDT', 'ETHUSDT']);
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>(['1h']);
  const [numImages, setNumImages] = useState(10);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const toggleItem = (item: string, list: string[], setList: (l: string[]) => void) => {
    setList(list.includes(item) ? list.filter(i => i !== item) : [...list, item]);
  };

  const handleRun = async () => {
    if (selectedPrompts.length === 0) {
      setError('Select at least one prompt');
      return;
    }
    if (selectedSymbols.length === 0) {
      setError('Select at least one symbol');
      return;
    }
    setError(null);
    setIsRunning(true);
    try {
      await onRunBacktest({
        prompts: selectedPrompts,
        symbols: selectedSymbols,
        numImages,
        timeframes: selectedTimeframes,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backtest failed');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b border-slate-700">
          <h2 className="text-xl font-bold text-white">Run Backtest</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Prompts Selection */}
          <div>
            <label className="text-sm text-slate-400 mb-2 block">Prompts to Test</label>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto bg-slate-900 p-2 rounded">
              {prompts.map(p => (
                <button
                  key={p}
                  onClick={() => toggleItem(p, selectedPrompts, setSelectedPrompts)}
                  className={`text-xs px-2 py-1 rounded ${
                    selectedPrompts.includes(p)
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {p.replace('get_analyzer_prompt_', '').slice(0, 25)}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-500 mt-1">{selectedPrompts.length} selected</p>
          </div>

          {/* Symbols */}
          <div>
            <label className="text-sm text-slate-400 mb-2 block">Symbols</label>
            <div className="flex flex-wrap gap-2">
              {AVAILABLE_SYMBOLS.map(s => (
                <button
                  key={s}
                  onClick={() => toggleItem(s, selectedSymbols, setSelectedSymbols)}
                  className={`text-xs px-2 py-1 rounded ${
                    selectedSymbols.includes(s)
                      ? 'bg-green-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {s.replace('USDT', '')}
                </button>
              ))}
            </div>
          </div>

          {/* Timeframes */}
          <div>
            <label className="text-sm text-slate-400 mb-2 block">Timeframes</label>
            <div className="flex gap-2">
              {AVAILABLE_TIMEFRAMES.map(t => (
                <button
                  key={t}
                  onClick={() => toggleItem(t, selectedTimeframes, setSelectedTimeframes)}
                  className={`text-xs px-3 py-1 rounded ${
                    selectedTimeframes.includes(t)
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Number of Images */}
          <div>
            <label className="text-sm text-slate-400 mb-2 block">Images per Symbol: {numImages}</label>
            <input
              type="range"
              min={1}
              max={50}
              value={numImages}
              onChange={e => setNumImages(Number(e.target.value))}
              className="w-full accent-blue-500"
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}
        </div>

        <div className="flex justify-end gap-3 p-4 border-t border-slate-700">
          <button onClick={onClose} className="px-4 py-2 bg-slate-700 text-white rounded hover:bg-slate-600">
            Cancel
          </button>
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {isRunning ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
            {isRunning ? 'Running...' : 'Start Backtest'}
          </button>
        </div>
      </div>
    </div>
  );
}


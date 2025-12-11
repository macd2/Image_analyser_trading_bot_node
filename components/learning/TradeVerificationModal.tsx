'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { X, TrendingUp, TrendingDown, Search, Filter, CheckCircle, XCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, Time, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts';

// Types
interface TradeMetadata {
  summary?: string;
  key_levels?: { support?: number; resistance?: number };
  risk_factors?: string[];
  market_condition?: string;
  market_direction?: string;
  evidence?: string;
  entry_explanation?: string;
  take_profit_explanation?: string;
  stop_loss_explanation?: string;
  risk_reward_ratio?: number;
  rationale?: string;
}

interface Trade {
  prompt: string;
  image: string;
  symbol: string;
  direction: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  outcome: string;
  pnl: number;
  exit_price?: number;
  exit_reason?: string;
  confidence?: number;  // AI's confidence score (0-1 or percentage)
  metadata?: TradeMetadata;  // Extended model output
}

// Calculate R-value (outcome in R units: -1R = hit SL, +RR = hit TP)
function calculateR(trade: Trade): number | null {
  const { entry_price, stop_loss, exit_price, direction } = trade;
  if (!entry_price || !stop_loss || !exit_price) return null;

  const isLong = direction?.toUpperCase() === 'LONG' || direction?.toUpperCase() === 'BUY';
  const risk = isLong ? (entry_price - stop_loss) : (stop_loss - entry_price);
  if (risk <= 0) return null;

  const actualMove = isLong ? (exit_price - entry_price) : (entry_price - exit_price);
  return actualMove / risk;
}

// Calculate Risk-Reward ratio from trade setup
function calculateRR(trade: Trade): number | null {
  const { entry_price, stop_loss, take_profit, direction } = trade;
  if (!entry_price || !stop_loss || !take_profit) return null;

  const isLong = direction?.toUpperCase() === 'LONG' || direction?.toUpperCase() === 'BUY';
  const risk = isLong ? (entry_price - stop_loss) : (stop_loss - entry_price);
  const reward = isLong ? (take_profit - entry_price) : (entry_price - take_profit);
  if (risk <= 0) return null;

  return reward / risk;
}

// Calculate Pearson correlation coefficient
function calculateCorrelation(pairs: Array<{ x: number; y: number }>): number | null {
  if (pairs.length < 3) return null;

  const n = pairs.length;
  const sumX = pairs.reduce((a, p) => a + p.x, 0);
  const sumY = pairs.reduce((a, p) => a + p.y, 0);
  const sumXY = pairs.reduce((a, p) => a + p.x * p.y, 0);
  const sumX2 = pairs.reduce((a, p) => a + p.x * p.x, 0);
  const sumY2 = pairs.reduce((a, p) => a + p.y * p.y, 0);

  const num = n * sumXY - sumX * sumY;
  const denom = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  if (denom === 0) return null;

  return num / denom;
}

interface PhaseData {
  trades: Trade[];
  prompts_tested: string[];
  images_count: number;
  survivors?: string[];
  eliminated?: string[];
}

interface TournamentData {
  id: string;
  phase_details: Record<string, PhaseData>;
}

interface TradeVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  tournament: TournamentData | null;
}

interface TradeWithPhase extends Trade {
  phase: string;
  phaseNum: number;
  timestamp: number;
  promptSurvived: boolean;
}

interface Candle {
  time: Time;
  open: number;
  high: number;
  low: number;
  close: number;
}

// Utility to parse timestamp from image filename
function parseTimestampFromImage(filename: string): number | null {
  // Format: SYMBOL_TIMEFRAME_YYYYMMDD_HHMMSS.png
  const match = filename.match(/(\d{8})_(\d{6})\.png$/);
  if (!match) return null;
  const dateStr = match[1];
  const timeStr = match[2];
  const year = parseInt(dateStr.slice(0, 4));
  const month = parseInt(dateStr.slice(4, 6)) - 1;
  const day = parseInt(dateStr.slice(6, 8));
  const hour = parseInt(timeStr.slice(0, 2));
  const min = parseInt(timeStr.slice(2, 4));
  const sec = parseInt(timeStr.slice(4, 6));
  return new Date(year, month, day, hour, min, sec).getTime();
}

// Utility to parse timeframe from image filename
function parseTimeframeFromImage(filename: string): string {
  const parts = filename.replace('.png', '').split('_');
  return parts.length >= 2 ? parts[1] : '1h';
}

export default function TradeVerificationModal({ isOpen, onClose, tournament }: TradeVerificationModalProps) {
  const [selectedTrade, setSelectedTrade] = useState<TradeWithPhase | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ phase: 'all', prompt: 'all', symbol: 'all', outcome: 'all' });
  const [chartReady, setChartReady] = useState(false);
  const [barCounts, setBarCounts] = useState<{ signalToFill: number | null; fillToExit: number | null }>({ signalToFill: null, fillToExit: null });
  const [collapsedPhases, setCollapsedPhases] = useState<Set<number>>(new Set());
  const [collapsedPrompts, setCollapsedPrompts] = useState<Set<string>>(new Set());
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);

  const togglePhase = (phaseNum: number) => {
    setCollapsedPhases(prev => {
      const next = new Set(prev);
      if (next.has(phaseNum)) next.delete(phaseNum);
      else next.add(phaseNum);
      return next;
    });
  };

  const togglePrompt = (key: string) => {
    setCollapsedPrompts(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Build survivor map - which prompts survived each phase
  const survivorMap = React.useMemo(() => {
    const map: Record<string, Set<string>> = {};
    if (!tournament?.phase_details) return map;

    // For each phase, check if prompt appears in next phase
    const phases = Object.keys(tournament.phase_details).sort();
    phases.forEach((phase, idx) => {
      const nextPhase = phases[idx + 1];
      const nextPhaseData = nextPhase ? tournament.phase_details[nextPhase] : null;
      const survivedPrompts = nextPhaseData?.prompts_tested || [];
      map[phase] = new Set(survivedPrompts);
    });
    // Last phase prompts all survived (made it to the end)
    const lastPhase = phases[phases.length - 1];
    if (lastPhase && tournament.phase_details[lastPhase]) {
      map[lastPhase] = new Set(tournament.phase_details[lastPhase].prompts_tested || []);
    }
    return map;
  }, [tournament]);

  // Collect all trades from all phases with metadata
  const allTrades = React.useMemo(() => {
    if (!tournament?.phase_details) return [];
    const trades: TradeWithPhase[] = [];
    Object.entries(tournament.phase_details).forEach(([phase, data]) => {
      const phaseData = data as PhaseData;
      const phaseNum = parseInt(phase.replace('phase_', '')) || 0;
      if (Array.isArray(phaseData?.trades)) {
        phaseData.trades.forEach(t => {
          const timestamp = parseTimestampFromImage(t.image) || 0;
          const promptSurvived = survivorMap[phase]?.has(t.prompt) || false;
          trades.push({ ...t, phase, phaseNum, timestamp, promptSurvived });
        });
      }
    });
    // Sort by phase, then by timestamp (newest first within each phase)
    return trades.sort((a, b) => {
      if (a.phaseNum !== b.phaseNum) return a.phaseNum - b.phaseNum;
      return b.timestamp - a.timestamp;
    });
  }, [tournament, survivorMap]);

  // Get all phase numbers (1, 2, 3) regardless of whether they have trades
  const allPhaseNumbers = React.useMemo(() => {
    if (!tournament?.phase_details) return [];
    return Object.keys(tournament.phase_details)
      .map(p => parseInt(p.replace('phase_', '')))
      .filter(n => !isNaN(n))
      .sort((a, b) => a - b);
  }, [tournament]);

  const uniquePrompts = [...new Set(allTrades.map(t => t.prompt))];
  const uniqueSymbols = [...new Set(allTrades.map(t => t.symbol))];

  // Filter trades
  const filteredTrades = allTrades.filter(t => {
    if (filters.phase !== 'all' && t.phaseNum !== parseInt(filters.phase)) return false;
    if (filters.prompt !== 'all' && t.prompt !== filters.prompt) return false;
    if (filters.symbol !== 'all' && t.symbol !== filters.symbol) return false;
    if (filters.outcome !== 'all' && t.outcome?.toUpperCase() !== filters.outcome) return false;
    return true;
  });

  // Group trades by phase for rendering
  const tradesByPhase = React.useMemo(() => {
    const grouped: Record<number, TradeWithPhase[]> = {};
    filteredTrades.forEach(t => {
      if (!grouped[t.phaseNum]) grouped[t.phaseNum] = [];
      grouped[t.phaseNum].push(t);
    });
    return grouped;
  }, [filteredTrades]);

  // Calculate confidence-R correlation across filtered trades
  const confidenceRCorrelation = React.useMemo(() => {
    const pairs: Array<{ x: number; y: number }> = [];
    filteredTrades.forEach(t => {
      const conf = t.confidence;
      const rValue = calculateR(t);
      if (conf != null && rValue != null) {
        // Normalize confidence to 0-1 if it's percentage
        const normalizedConf = conf > 1 ? conf / 100 : conf;
        pairs.push({ x: normalizedConf, y: rValue });
      }
    });
    return {
      correlation: calculateCorrelation(pairs),
      count: pairs.length,
      avgR: pairs.length > 0 ? pairs.reduce((a, p) => a + p.y, 0) / pairs.length : null
    };
  }, [filteredTrades]);

  // Fetch candles when trade is selected
  const fetchCandles = useCallback(async (trade: Trade) => {
    const timestamp = parseTimestampFromImage(trade.image);
    const timeframe = parseTimeframeFromImage(trade.image);
    if (!timestamp) {
      setError('Could not parse timestamp from image filename');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/tournament/candles?symbol=${trade.symbol}&timeframe=${timeframe}&timestamp=${timestamp}`);
      const data = await res.json();
      if (data.error) {
        setError(data.error);
        setCandles([]);
      } else if (data.candles && data.candles.length > 0) {
        setCandles(data.candles);
      } else {
        setError('No candles found for this trade');
        setCandles([]);
      }
    } catch (err) {
      console.error('Failed to fetch candles:', err);
      setError('Failed to fetch candles');
      setCandles([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTrade) fetchCandles(selectedTrade);
  }, [selectedTrade, fetchCandles]);

  // Initialize chart - runs once when modal opens and a trade is selected
  useEffect(() => {
    if (!chartContainerRef.current || !isOpen || !selectedTrade) return;

    // Skip if chart already exists
    if (chartRef.current) return;

    // Delay chart creation to ensure container has dimensions
    const timer = setTimeout(() => {
      if (!chartContainerRef.current || chartRef.current) return;

      const containerWidth = chartContainerRef.current.clientWidth || 600;
      const containerHeight = chartContainerRef.current.clientHeight || 400;

      console.log('[Chart] Creating chart with dimensions:', containerWidth, 'x', containerHeight);

      const chart = createChart(chartContainerRef.current, {
        layout: { background: { color: '#1e293b' }, textColor: '#94a3b8' },
        grid: { vertLines: { color: '#334155' }, horzLines: { color: '#334155' } },
        width: containerWidth,
        height: containerHeight,
        crosshair: { mode: 1 },
        timeScale: { timeVisible: true, secondsVisible: false },
      });
      chartRef.current = chart;
      candleSeriesRef.current = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });

      setChartReady(true);

      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: chartContainerRef.current.clientWidth,
            height: chartContainerRef.current.clientHeight
          });
        }
      };
      window.addEventListener('resize', handleResize);

      // Store cleanup function
      (chartRef.current as unknown as { _resizeHandler: () => void })._resizeHandler = handleResize;
    }, 150);

    return () => {
      clearTimeout(timer);
    };
  }, [isOpen, selectedTrade]);

  // Cleanup chart when modal closes
  useEffect(() => {
    if (!isOpen && chartRef.current) {
      const handler = (chartRef.current as unknown as { _resizeHandler?: () => void })._resizeHandler;
      if (handler) window.removeEventListener('resize', handler);
      chartRef.current.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      setChartReady(false);
    }
  }, [isOpen]);

  // Update chart data and markers when candles change OR chart becomes ready
  useEffect(() => {
    if (!chartReady || !chartRef.current) {
      console.log('[Chart] Waiting for chart... ready:', chartReady, 'ref:', !!chartRef.current);
      return;
    }
    if (candles.length === 0) {
      console.log('[Chart] No candles to display');
      return;
    }

    console.log('[Chart] Updating chart with', candles.length, 'candles');

    // Remove old series and create new one to clear price lines
    if (candleSeriesRef.current) {
      chartRef.current.removeSeries(candleSeriesRef.current);
    }

    // Create new series
    candleSeriesRef.current = chartRef.current.addSeries(CandlestickSeries, {
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    });

    // Set candle data
    candleSeriesRef.current.setData(candles as CandlestickData<Time>[]);

    if (selectedTrade) {
      const timestamp = parseTimestampFromImage(selectedTrade.image);
      if (timestamp) {
        const entryTimeNum = Math.floor(timestamp / 1000);
        const entryTime = entryTimeNum as Time;
        const isLong = selectedTrade.direction?.toUpperCase() === 'LONG' || selectedTrade.direction?.toUpperCase() === 'BUY';
        const entryPrice = selectedTrade.entry_price;

        // Find the fill candle - first candle after signal where price touches entry_price
        let fillTime: Time | null = null;
        let fillIndex = -1;
        let signalIndex = -1;
        if (entryPrice) {
          for (let i = 0; i < candles.length; i++) {
            const candle = candles[i];
            const candleTimeNum = Number(candle.time);
            // Track signal candle index
            if (signalIndex === -1 && candleTimeNum >= entryTimeNum) {
              signalIndex = i;
            }
            // Only check candles AT or AFTER the signal time
            if (candleTimeNum >= entryTimeNum) {
              // Fill occurs when the entry price is within the candle's range (low to high)
              // This works for both LONG and SHORT - price touched the entry level
              const filled = candle.low <= entryPrice && candle.high >= entryPrice;
              if (filled) {
                fillTime = candle.time as Time;
                fillIndex = i;
                break;
              }
            }
          }
        }

        // Calculate bar counts for signal-to-fill and fill-to-exit
        let signalToFillBars: number | null = null;
        let fillToExitBars: number | null = null;

        if (signalIndex >= 0 && fillIndex >= 0) {
          signalToFillBars = fillIndex - signalIndex;

          // Find exit candle if we have exit price
          if (selectedTrade.exit_price) {
            const exitPrice = selectedTrade.exit_price;
            for (let i = fillIndex; i < candles.length; i++) {
              const candle = candles[i];
              // Exit when price touches exit level
              if (candle.low <= exitPrice && candle.high >= exitPrice) {
                fillToExitBars = i - fillIndex;
                break;
              }
            }
          }
        }
        setBarCounts({ signalToFill: signalToFillBars, fillToExit: fillToExitBars });

        // Add markers for signal and fill using v5 API
        const markers: Array<{ time: Time; position: 'belowBar' | 'aboveBar'; color: string; shape: 'circle' | 'square' | 'arrowUp' | 'arrowDown'; text: string }> = [
          { time: entryTime, position: isLong ? 'belowBar' : 'aboveBar', color: '#3b82f6', shape: 'circle', text: 'Signal' },
        ];

        if (fillTime) {
          const fillDate = new Date(Number(fillTime) * 1000);
          const fillTimeStr = fillDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          markers.push({
            time: fillTime,
            position: isLong ? 'belowBar' : 'aboveBar',
            color: '#f59e0b',
            shape: isLong ? 'arrowUp' : 'arrowDown',
            text: `Fill ${fillTimeStr}`
          });
        }

        // Sort markers by time (required by lightweight-charts)
        markers.sort((a, b) => Number(a.time) - Number(b.time));
        createSeriesMarkers(candleSeriesRef.current, markers);

        const series = candleSeriesRef.current;

        // Add price lines for Entry, SL, TP, Exit
        if (selectedTrade.entry_price) {
          series.createPriceLine({ price: selectedTrade.entry_price, color: '#3b82f6', lineWidth: 2, lineStyle: 2, title: 'Entry' });
        }
        if (selectedTrade.stop_loss) {
          series.createPriceLine({ price: selectedTrade.stop_loss, color: '#ef4444', lineWidth: 1, lineStyle: 1, title: 'SL' });
        }
        if (selectedTrade.take_profit) {
          series.createPriceLine({ price: selectedTrade.take_profit, color: '#22c55e', lineWidth: 1, lineStyle: 1, title: 'TP' });
        }
        if (selectedTrade.exit_price) {
          const exitColor = selectedTrade.outcome?.toUpperCase() === 'WIN' ? '#22c55e' : '#ef4444';
          series.createPriceLine({ price: selectedTrade.exit_price, color: exitColor, lineWidth: 2, lineStyle: 0, title: 'Exit' });
        }
      }
      chartRef.current.timeScale().fitContent();
    }
  }, [candles, chartReady, selectedTrade]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 rounded-xl w-full max-w-7xl h-[90vh] flex flex-col border border-slate-700">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Search size={18} /> Trade Verification - {tournament?.id || 'Unknown'}
          </h2>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-400">{filteredTrades.length} trades</span>
            <button onClick={onClose} className="text-slate-400 hover:text-white p-1"><X size={20} /></button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 p-3 border-b border-slate-800 bg-slate-800/50">
          <Filter size={14} className="text-slate-400" />
          <select value={filters.phase} onChange={e => setFilters(f => ({ ...f, phase: e.target.value }))}
            className="bg-slate-700 text-white text-xs rounded px-2 py-1 border border-slate-600">
            <option value="all">All Phases</option>
            {allPhaseNumbers.map(p => <option key={p} value={String(p)}>Phase {p}</option>)}
          </select>
          <select value={filters.prompt} onChange={e => setFilters(f => ({ ...f, prompt: e.target.value }))}
            className="bg-slate-700 text-white text-xs rounded px-2 py-1 border border-slate-600 max-w-[150px]">
            <option value="all">All Prompts</option>
            {uniquePrompts.map(p => <option key={p} value={p}>{p.replace('get_analyzer_prompt_', '')}</option>)}
          </select>
          <select value={filters.symbol} onChange={e => setFilters(f => ({ ...f, symbol: e.target.value }))}
            className="bg-slate-700 text-white text-xs rounded px-2 py-1 border border-slate-600">
            <option value="all">All Symbols</option>
            {uniqueSymbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filters.outcome} onChange={e => setFilters(f => ({ ...f, outcome: e.target.value }))}
            className="bg-slate-700 text-white text-xs rounded px-2 py-1 border border-slate-600">
            <option value="all">All Outcomes</option>
            <option value="WIN">Wins</option>
            <option value="LOSS">Losses</option>
          </select>
        </div>

        {/* Split View */}
        <div className="flex-1 flex overflow-hidden">
          {/* Trade List - Left */}
          <div className="w-96 border-r border-slate-700 overflow-y-auto">
            {/* Show all phases, even empty ones */}
            {allPhaseNumbers.map(phaseNum => {
              const phaseTrades = tradesByPhase[phaseNum] || [];
              // Skip phases when phase filter is active and doesn't match
              if (filters.phase !== 'all' && parseInt(filters.phase) !== phaseNum) return null;

              // Group trades by prompt within this phase
              const tradesByPrompt: Record<string, typeof phaseTrades> = {};
              phaseTrades.forEach(t => {
                const p = t.prompt || 'Unknown';
                if (!tradesByPrompt[p]) tradesByPrompt[p] = [];
                tradesByPrompt[p].push(t);
              });
              const promptNames = Object.keys(tradesByPrompt).sort();
              const phaseCollapsed = collapsedPhases.has(phaseNum);

              return (
                <div key={phaseNum}>
                  {/* Phase Header - Clickable */}
                  <div
                    onClick={() => togglePhase(phaseNum)}
                    className="sticky top-0 bg-slate-800 px-3 py-2 border-b border-slate-700 flex items-center justify-between z-10 cursor-pointer hover:bg-slate-700/50 transition"
                  >
                    <div className="flex items-center gap-2">
                      {phaseCollapsed ? <ChevronRight size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                      <span className="text-sm font-semibold text-blue-400">Phase {phaseNum}</span>
                    </div>
                    <span className="text-xs text-slate-400">
                      {phaseTrades.length === 0 ? 'No trades (all HOLDs)' : `${phaseTrades.length} trades, ${promptNames.length} prompts`}
                    </span>
                  </div>
                  {/* Trades in this phase grouped by prompt - collapsible */}
                  {!phaseCollapsed && (
                    phaseTrades.length === 0 ? (
                      <div className="p-3 text-xs text-slate-500 italic">
                        All prompts recommended HOLD in this phase - no trades to display
                      </div>
                    ) : (
                      promptNames.map(promptName => {
                        const promptTrades = tradesByPrompt[promptName];
                        // Apply prompt filter
                        if (filters.prompt !== 'all' && promptName !== filters.prompt) return null;
                        const wins = promptTrades.filter(t => t.outcome?.toUpperCase() === 'WIN').length;
                        const totalPnl = promptTrades.reduce((sum, t) => sum + (Number(t.pnl) || 0), 0);
                        const survived = promptTrades[0]?.promptSurvived;
                        const promptKey = `${phaseNum}-${promptName}`;
                        const promptCollapsed = collapsedPrompts.has(promptKey);

                        return (
                          <div key={promptKey}>
                            {/* Prompt Sub-Header - Clickable with matching style */}
                            <div
                              onClick={() => togglePrompt(promptKey)}
                              className="px-3 py-1.5 bg-slate-750 border-b border-slate-700 flex items-center justify-between cursor-pointer hover:bg-slate-700/50 transition"
                              style={{ backgroundColor: 'rgb(41, 48, 61)' }}
                            >
                              <div className="flex items-center gap-1.5">
                                {promptCollapsed ? <ChevronRight size={12} className="text-slate-400" /> : <ChevronDown size={12} className="text-slate-400" />}
                                <span title={survived ? "Survived" : "Eliminated"}>
                                  {survived
                                    ? <CheckCircle size={11} className="text-green-400" />
                                    : <XCircle size={11} className="text-red-400" />}
                                </span>
                                <span className="text-xs text-slate-300 font-medium truncate max-w-[160px]" title={promptName}>
                                  {promptName.replace('get_analyzer_prompt_', '')}
                                </span>
                              </div>
                              <div className="flex items-center gap-2 text-xs">
                                <span className="text-slate-400">{wins}/{promptTrades.length} W</span>
                                <span className={totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                                  {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}%
                                </span>
                              </div>
                            </div>
                            {/* Trades for this prompt - collapsible */}
                            {!promptCollapsed && promptTrades.map((trade, idx) => {
                              const dateTime = trade.timestamp ? new Date(trade.timestamp).toLocaleString() : 'Unknown';
                              return (
                                <div key={`${promptKey}-${idx}`} onClick={() => setSelectedTrade(trade)}
                                  className={`p-3 border-b border-slate-800 cursor-pointer hover:bg-slate-800/50 transition
                                    ${selectedTrade === trade ? 'bg-slate-800 border-l-2 border-l-blue-500' : ''}`}>
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      {trade.outcome?.toUpperCase() === 'WIN'
                                        ? <TrendingUp size={14} className="text-green-400" />
                                        : <TrendingDown size={14} className="text-red-400" />}
                                      <span className="text-white font-medium text-sm">{trade.symbol}</span>
                                      <span className={`text-xs px-1.5 py-0.5 rounded ${trade.direction?.toUpperCase() === 'LONG' || trade.direction?.toUpperCase() === 'BUY' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}`}>
                                        {trade.direction?.toUpperCase()}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className={`text-sm font-mono ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                        {trade.pnl >= 0 ? '+' : ''}{Number(trade.pnl).toFixed(2)}%
                                      </span>
                                    </div>
                                  </div>
                                  {/* Date/Time and Image */}
                                  <div className="mt-1 text-xs text-slate-500">
                                    <span>{dateTime}</span>
                                  </div>
                                  <div className="text-xs text-slate-600 truncate" title={trade.image}>{trade.image}</div>
                                </div>
                              );
                            })}
                          </div>
                        );
                      })
                    )
                  )}
                </div>
              );
            })}
            {/* Show message if no phases at all */}
            {allPhaseNumbers.length === 0 && (
              <div className="p-4 text-slate-500 text-sm">No phase data found</div>
            )}
          </div>

          {/* Chart - Right */}
          <div className="flex-1 flex flex-col p-4 overflow-hidden">
            {selectedTrade ? (
              <>
                {/* Chart container - use explicit height instead of flex-1 with absolute */}
                <div className="relative w-full h-[400px] bg-slate-800/30 rounded-lg overflow-hidden">
                  <div ref={chartContainerRef} className="w-full h-full" />
                  {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10">
                      <div className="text-white flex items-center gap-2">
                        <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
                        Loading candles...
                      </div>
                    </div>
                  )}
                  {error && !loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10">
                      <div className="text-red-400 text-center p-4">
                        <div className="text-lg mb-2">⚠️ Chart Error</div>
                        <div className="text-sm">{error}</div>
                      </div>
                    </div>
                  )}
                </div>
                {/* Trade Info Panel - 4 columns */}
                <div className="mt-4 grid grid-cols-4 gap-3 bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  {/* Row 1: Direction and Confidence */}
                  <div><div className="text-xs text-slate-400">Direction</div><div className={`font-medium ${selectedTrade.direction?.toUpperCase() === 'LONG' ? 'text-green-400' : 'text-red-400'}`}>{selectedTrade.direction?.toUpperCase()}</div></div>
                  <div>
                    <div className="text-xs text-slate-400">Confidence</div>
                    {selectedTrade.confidence != null ? (
                      <div className="text-yellow-400 font-mono">{(selectedTrade.confidence > 1 ? selectedTrade.confidence : selectedTrade.confidence * 100).toFixed(0)}%</div>
                    ) : <div className="text-slate-500">-</div>}
                  </div>
                  <div></div>
                  <div></div>

                  {/* Row 2: Entry, SL, TP, Exit */}
                  <div><div className="text-xs text-slate-400">Entry</div><div className="text-white font-mono text-sm">{selectedTrade.entry_price}</div></div>
                  <div><div className="text-xs text-slate-400">Stop Loss</div><div className="text-red-400 font-mono text-sm">{selectedTrade.stop_loss}</div></div>
                  <div><div className="text-xs text-slate-400">Take Profit</div><div className="text-green-400 font-mono text-sm">{selectedTrade.take_profit}</div></div>
                  <div><div className="text-xs text-slate-400">Exit</div><div className="text-white font-mono text-sm">{selectedTrade.exit_price || '-'}</div></div>

                  {/* Row 3: Exit Reason, Outcome, PnL */}
                  <div><div className="text-xs text-slate-400">Exit Reason</div><div className="text-slate-300 text-sm">{selectedTrade.exit_reason || '-'}</div></div>
                  <div><div className="text-xs text-slate-400">Outcome</div><div className={selectedTrade.outcome?.toUpperCase() === 'WIN' ? 'text-green-400' : 'text-red-400'}>{selectedTrade.outcome}</div></div>
                  <div><div className="text-xs text-slate-400">PnL</div><div className={`font-mono font-bold ${selectedTrade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{selectedTrade.pnl >= 0 ? '+' : ''}{Number(selectedTrade.pnl).toFixed(2)}%</div></div>
                  <div></div>

                  {/* Row 4: Signal→Fill, Trade Duration, R-Value, Setup RR */}
                  <div><div className="text-xs text-slate-400">Signal → Fill</div><div className="text-amber-400 font-mono">{barCounts.signalToFill !== null ? `${barCounts.signalToFill} bars` : '-'}</div></div>
                  <div><div className="text-xs text-slate-400">Trade Duration</div><div className="text-cyan-400 font-mono">{barCounts.fillToExit !== null ? `${barCounts.fillToExit} bars` : '-'}</div></div>
                  <div>
                    <div className="text-xs text-slate-400">R-Value</div>
                    {(() => {
                      const rVal = calculateR(selectedTrade);
                      if (rVal === null) return <div className="text-slate-500">-</div>;
                      const color = rVal >= 0 ? 'text-green-400' : 'text-red-400';
                      return <div className={`font-mono font-bold ${color}`}>{rVal >= 0 ? '+' : ''}{rVal.toFixed(2)}R</div>;
                    })()}
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Setup RR</div>
                    {(() => {
                      const rr = calculateRR(selectedTrade);
                      if (rr === null) return <div className="text-slate-500">-</div>;
                      return <div className="text-purple-400 font-mono font-medium">1:{rr.toFixed(2)}</div>;
                    })()}
                  </div>
                </div>

                {/* Confidence-R Correlation Summary */}
                {confidenceRCorrelation.count >= 3 && (
                  <div className="mt-3 bg-slate-800/30 rounded-lg px-4 py-2 border border-slate-700/50 flex items-center gap-6 text-sm">
                    <span className="text-slate-400">Confidence ↔ R Correlation:</span>
                    {confidenceRCorrelation.correlation !== null ? (
                      <>
                        <span className={`font-mono font-bold ${
                          confidenceRCorrelation.correlation > 0.3 ? 'text-green-400' :
                          confidenceRCorrelation.correlation < -0.3 ? 'text-red-400' : 'text-slate-400'
                        }`}>
                          r = {confidenceRCorrelation.correlation.toFixed(3)}
                        </span>
                        <span className="text-slate-500">
                          ({confidenceRCorrelation.count} trades with confidence data)
                        </span>
                        <span className="text-slate-500">
                          Avg R: <span className={confidenceRCorrelation.avgR! >= 0 ? 'text-green-400' : 'text-red-400'}>
                            {confidenceRCorrelation.avgR! >= 0 ? '+' : ''}{confidenceRCorrelation.avgR!.toFixed(2)}R
                          </span>
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-500">Insufficient variance</span>
                    )}
                  </div>
                )}
                {/* Full values on hover */}
                <div className="mt-2 text-xs text-slate-500 flex items-center gap-2 flex-wrap">
                  <span className="bg-slate-800 px-2 py-1 rounded" title={selectedTrade.prompt}>
                    Prompt: {selectedTrade.prompt?.replace('get_analyzer_prompt_', '')}
                  </span>
                  <span className="bg-slate-800 px-2 py-1 rounded" title={selectedTrade.image}>
                    Image: {selectedTrade.image}
                  </span>
                  <span className="bg-slate-800 px-2 py-1 rounded">
                    Phase: {selectedTrade.phaseNum}
                  </span>
                  <span className={`px-2 py-1 rounded flex items-center gap-1 ${selectedTrade.promptSurvived ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                    {selectedTrade.promptSurvived ? <CheckCircle size={12} /> : <XCircle size={12} />}
                    {selectedTrade.promptSurvived ? 'Survived' : 'Eliminated'}
                  </span>
                </div>

                {/* AI Analysis Metadata (collapsible) */}
                {selectedTrade.metadata && Object.values(selectedTrade.metadata).some(v => v != null) && (
                  <details className="mt-3 bg-slate-800/30 rounded-lg border border-slate-700/50">
                    <summary className="px-4 py-2 cursor-pointer text-sm text-slate-400 hover:text-slate-300 flex items-center gap-2">
                      <ChevronRight size={14} className="details-open-rotate" />
                      AI Analysis Details
                    </summary>
                    <div className="px-4 pb-3 pt-1 text-sm space-y-2">
                      {selectedTrade.metadata.summary && (
                        <div><span className="text-slate-500">Summary:</span> <span className="text-slate-300">{selectedTrade.metadata.summary}</span></div>
                      )}
                      {selectedTrade.metadata.rationale && (
                        <div><span className="text-slate-500">Rationale:</span> <span className="text-slate-300">{selectedTrade.metadata.rationale}</span></div>
                      )}
                      {selectedTrade.metadata.evidence && (
                        <div><span className="text-slate-500">Evidence:</span> <span className="text-slate-300">{selectedTrade.metadata.evidence}</span></div>
                      )}
                      {selectedTrade.metadata.market_condition && (
                        <div><span className="text-slate-500">Market:</span> <span className="text-amber-400">{selectedTrade.metadata.market_condition}</span> <span className="text-slate-400">{selectedTrade.metadata.market_direction}</span></div>
                      )}
                      {selectedTrade.metadata.key_levels && (
                        <div><span className="text-slate-500">Key Levels:</span> <span className="text-green-400">S: {selectedTrade.metadata.key_levels.support}</span> <span className="text-red-400">R: {selectedTrade.metadata.key_levels.resistance}</span></div>
                      )}
                      {selectedTrade.metadata.entry_explanation && (
                        <div><span className="text-slate-500">Entry:</span> <span className="text-slate-300">{selectedTrade.metadata.entry_explanation}</span></div>
                      )}
                      {selectedTrade.metadata.stop_loss_explanation && (
                        <div><span className="text-slate-500">Stop Loss:</span> <span className="text-slate-300">{selectedTrade.metadata.stop_loss_explanation}</span></div>
                      )}
                      {selectedTrade.metadata.take_profit_explanation && (
                        <div><span className="text-slate-500">Take Profit:</span> <span className="text-slate-300">{selectedTrade.metadata.take_profit_explanation}</span></div>
                      )}
                      {selectedTrade.metadata.risk_factors && selectedTrade.metadata.risk_factors.length > 0 && (
                        <div><span className="text-slate-500">Risk Factors:</span> <span className="text-orange-400">{selectedTrade.metadata.risk_factors.join(', ')}</span></div>
                      )}
                      {selectedTrade.metadata.risk_reward_ratio != null && (
                        <div><span className="text-slate-500">Model RR:</span> <span className="text-purple-400">{selectedTrade.metadata.risk_reward_ratio}</span></div>
                      )}
                    </div>
                  </details>
                )}
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500">
                Select a trade from the list to view chart
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


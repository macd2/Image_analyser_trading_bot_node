'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Trophy, Square, Settings, Loader2, Crown, Medal, Award, TrendingUp, Zap, X, Clock, Target, BarChart3, ChevronRight, Copy, Check, Eye } from 'lucide-react';
import TradeVerificationModal from './TradeVerificationModal';
import { PageLoader } from '@/components/ui/page-loader';

interface TournamentConfig {
  prompts: string[];
  symbols: string[];
  timeframes: string[];
  model: string;
  eliminationPct: number;
  imagesPhase1: number;
  imagesPhase2: number;
  imagesPhase3: number;
  imageOffset: number;
  selectionStrategy: 'random' | 'sequential';
  rankingStrategy: 'wilson' | 'win_rate' | 'pnl';
  randomSymbols: boolean;
  randomTimeframes: boolean;
  minTradesForSurvival: number;
  holdPenalty: number;
}

interface RankingEntry {
  prompt: string;
  win_rate: number;
  avg_pnl: number;
  wilson_lower?: number;
  rank_score?: number;
}

interface TournamentResult {
  winner: string;
  win_rate: number;
  avg_pnl: number;
  wilson_lower: number;
  rank_score: number;
  ranking_strategy: string;
  rankings: Array<{ rank: number; prompt: string; win_rate: number; avg_pnl: number; trades: number; wilson_lower: number; rank_score: number }>;
  total_api_calls: number;
  duration_sec: number;
  error?: string;
}

interface TournamentState {
  tournamentId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress: number;
  rankings: RankingEntry[];
  logs: string[];
  result: TournamentResult | null;
}

const MODELS = ['gpt-4o', 'gpt-4o-mini', 'claude-3-5-sonnet-20241022'];
const SETTINGS_INSTANCE_ID = 'tournament';

interface TournamentSettings {
  excludedPrompts?: string[];  // Blacklist - prompts to exclude
  selectedSymbols?: string[];
  selectedTimeframes?: string[];
  model?: string;
  eliminationPct?: number;
  imagesPhase1?: number;
  imagesPhase2?: number;
  imagesPhase3?: number;
  imageOffset?: number;
  selectionStrategy?: 'random' | 'sequential';
  randomSymbols?: boolean;     // When random: randomize symbols?
  randomTimeframes?: boolean;  // When random: randomize timeframes?
  rankingStrategy?: 'wilson' | 'win_rate' | 'pnl';
  minTradesForSurvival?: number;
  holdPenalty?: number;
}

export default function FindBestPromptPage() {
  // Config state
  const [prompts, setPrompts] = useState<string[]>([]);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [availableTimeframes, setAvailableTimeframes] = useState<string[]>(['1h']); // From backup folder
  const [excludedPrompts, setExcludedPrompts] = useState<string[]>([]);  // Blacklist
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>(['1h']);
  const [model, setModel] = useState('gpt-4o');
  const [eliminationPct, setEliminationPct] = useState(50);
  const [imagesPhase1, setImagesPhase1] = useState(10);
  const [imagesPhase2, setImagesPhase2] = useState(25);
  const [imagesPhase3, setImagesPhase3] = useState(50);
  const [imageOffset, setImageOffset] = useState(100);
  const [selectionStrategy, setSelectionStrategy] = useState<'random' | 'sequential'>('random');
  const [randomSymbols, setRandomSymbols] = useState(true);
  const [randomTimeframes, setRandomTimeframes] = useState(false);
  const [rankingStrategy, setRankingStrategy] = useState<'wilson' | 'win_rate' | 'pnl'>('wilson');
  const [minTradesForSurvival, setMinTradesForSurvival] = useState(1);  // Require at least 1 trade to survive
  const [holdPenalty, setHoldPenalty] = useState(-0.1);  // Penalty per HOLD (opportunity cost)
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');

  // Tournament state
  const [tournament, setTournament] = useState<TournamentState | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [recentRuns, setRecentRuns] = useState<Array<{
    id: number; tournament_id: string; started_at: string; finished_at: string;
    status: string; winner: string; win_rate: number; avg_pnl: number;
    config: { symbols?: string[]; timeframes?: string[]; model?: string; prompts?: string[] };
    total_api_calls: number; duration_sec: number; random_seed: number;
  }>>([]);
  const [selectedRun, setSelectedRun] = useState<{
    id: number; tournament_id: string; started_at: string; finished_at: string;
    status: string; winner: string; win_rate: number; avg_pnl: number; random_seed: number;
    config: Record<string, unknown>; phase_details: Record<string, unknown>; result: Record<string, unknown>;
    total_api_calls: number; duration_sec: number;
  } | null>(null);
  const [loadingRunDetails, setLoadingRunDetails] = useState(false);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Computed: active prompts (all except excluded)
  const activePrompts = prompts.filter(p => !excludedPrompts.includes(p));

  // Load prompts, symbols, and saved settings
  useEffect(() => {
    Promise.all([
      fetch('/api/learning/prompts').then(r => r.json()),
      fetch('/api/backtest/symbols').then(r => r.json()),
      fetch(`/api/settings?instanceId=${SETTINGS_INSTANCE_ID}`).then(r => r.json())
    ]).then(([promptsData, symbolsData, settingsData]) => {
      const availablePrompts = promptsData.prompts || [];
      const availableSymbols = symbolsData.symbols || [];
      const availableTfs = symbolsData.timeframes || ['1h']; // Get timeframes from backup folder
      setPrompts(availablePrompts);
      setSymbols(availableSymbols);
      setAvailableTimeframes(availableTfs);

      const s = settingsData.settings as TournamentSettings;
      if (s) {
        // Apply saved blacklist (only valid prompts)
        const savedExcluded = s.excludedPrompts?.filter((p: string) => availablePrompts.includes(p)) || [];
        setExcludedPrompts(savedExcluded);
        // Apply saved symbols (filter to only available)
        const savedSymbols = s.selectedSymbols?.filter((sym: string) => availableSymbols.includes(sym)) || [];
        setSelectedSymbols(savedSymbols.length ? savedSymbols : availableSymbols.slice(0, 3));
        // Apply saved timeframes (filter to only available)
        const savedTimeframes = s.selectedTimeframes?.filter((tf: string) => availableTfs.includes(tf)) || [];
        setSelectedTimeframes(savedTimeframes.length ? savedTimeframes : availableTfs.slice(0, 1));
        // Apply other settings
        if (s.model) setModel(s.model);
        if (s.eliminationPct) setEliminationPct(s.eliminationPct);
        if (s.imagesPhase1) setImagesPhase1(s.imagesPhase1);
        if (s.imagesPhase2) setImagesPhase2(s.imagesPhase2);
        if (s.imagesPhase3) setImagesPhase3(s.imagesPhase3);
        if (s.imageOffset !== undefined) setImageOffset(s.imageOffset);
        if (s.selectionStrategy) setSelectionStrategy(s.selectionStrategy);
        if (s.randomSymbols !== undefined) setRandomSymbols(s.randomSymbols);
        if (s.randomTimeframes !== undefined) setRandomTimeframes(s.randomTimeframes);
        if (s.rankingStrategy) setRankingStrategy(s.rankingStrategy);
        if (s.minTradesForSurvival !== undefined) setMinTradesForSurvival(s.minTradesForSurvival);
        if (s.holdPenalty !== undefined) setHoldPenalty(s.holdPenalty);
      } else {
        // Default: select first 3 symbols and first timeframe
        setSelectedSymbols(availableSymbols.slice(0, 3));
        setSelectedTimeframes(availableTfs.slice(0, 1));
      }
      setSettingsLoaded(true);
      // Also load recent runs
      fetch('/api/tournament/history?limit=10').then(r => r.json())
        .then(data => setRecentRuns(data.runs || []))
        .catch(() => {});
    }).catch(() => setSettingsLoaded(true));
  }, []);

  // Reload history after tournament completes
  const reloadHistory = useCallback(() => {
    fetch('/api/tournament/history?limit=10').then(r => r.json())
      .then(data => setRecentRuns(data.runs || []))
      .catch(() => {});
  }, []);

  // Load full details for a tournament run
  const loadRunDetails = useCallback(async (tournamentId: string) => {
    setLoadingRunDetails(true);
    try {
      const res = await fetch(`/api/tournament/history?id=${tournamentId}`);
      const data = await res.json();
      if (data && !data.error) {
        setSelectedRun(data);
      }
    } catch { /* ignore */ }
    setLoadingRunDetails(false);
  }, []);

  // Copy to clipboard helper
  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  };

  // Save settings when they change (debounced with visual feedback)
  useEffect(() => {
    if (!settingsLoaded) return;
    setSaveStatus('saving');
    const timeout = setTimeout(() => {
      const settings: TournamentSettings = {
        excludedPrompts, selectedSymbols, selectedTimeframes, model,
        eliminationPct, imagesPhase1, imagesPhase2, imagesPhase3,
        imageOffset, selectionStrategy, randomSymbols, randomTimeframes, rankingStrategy,
        minTradesForSurvival, holdPenalty
      };
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instanceId: SETTINGS_INSTANCE_ID, settings })
      }).then(() => {
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 1500);
      }).catch(console.error);
    }, 500);
    return () => clearTimeout(timeout);
  }, [settingsLoaded, excludedPrompts, selectedSymbols, selectedTimeframes, model,
      eliminationPct, imagesPhase1, imagesPhase2, imagesPhase3, imageOffset,
      selectionStrategy, randomSymbols, randomTimeframes, rankingStrategy,
      minTradesForSurvival, holdPenalty]);

  // Auto-scroll logs
  useEffect(() => {
    if (tournament?.logs.length) logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [tournament?.logs]);

  // Cleanup
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const toggleItem = (item: string, list: string[], setList: (l: string[]) => void) => {
    setList(list.includes(item) ? list.filter(i => i !== item) : [...list, item]);
  };

  const pollStatus = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/tournament?tournamentId=${id}`);
      const data = await res.json();
      setTournament(prev => prev ? { ...prev, ...data } : null);
      if (['completed', 'failed', 'cancelled'].includes(data.status)) {
        if (pollRef.current) clearInterval(pollRef.current);
        reloadHistory();  // Refresh history when tournament ends
      }
    } catch (e) { console.error('Poll error:', e); }
  }, [reloadHistory]);

  const startTournament = async () => {
    if (activePrompts.length < 2) return alert('Need at least 2 prompts (exclude fewer)');
    if (!selectionStrategy.startsWith('random') && selectedSymbols.length === 0) return alert('Select at least 1 symbol');
    if (!selectionStrategy.startsWith('random') && selectedTimeframes.length === 0) return alert('Select at least 1 timeframe');

    const config: TournamentConfig = {
      prompts: activePrompts,  // All prompts minus excluded
      symbols: randomSymbols && selectionStrategy === 'random' ? symbols : selectedSymbols,
      timeframes: randomTimeframes && selectionStrategy === 'random' ? availableTimeframes : selectedTimeframes,
      model, eliminationPct, imagesPhase1, imagesPhase2, imagesPhase3, imageOffset, selectionStrategy, rankingStrategy,
      randomSymbols: randomSymbols && selectionStrategy === 'random',
      randomTimeframes: randomTimeframes && selectionStrategy === 'random',
      minTradesForSurvival, holdPenalty,
    };

    try {
      const res = await fetch('/api/tournament', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      setTournament({
        tournamentId: data.tournamentId, status: 'running', progress: 0,
        rankings: [], logs: [], result: null
      });
      pollRef.current = setInterval(() => pollStatus(data.tournamentId), 500);
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Failed to start');
    }
  };

  const cancelTournament = async () => {
    if (!tournament) return;
    await fetch(`/api/tournament?tournamentId=${tournament.tournamentId}`, { method: 'DELETE' });
    if (pollRef.current) clearInterval(pollRef.current);
    setTournament(prev => prev ? { ...prev, status: 'cancelled' } : null);
  };

  const isRunning = tournament && ['pending', 'running'].includes(tournament.status);
  const isRandomSymbols = selectionStrategy === 'random' && randomSymbols;
  const isRandomTimeframes = selectionStrategy === 'random' && randomTimeframes;
  const estimatedCalls = activePrompts.length * (imagesPhase1 +
    Math.ceil(activePrompts.length * (100-eliminationPct)/100) * imagesPhase2 +
    Math.min(3, Math.ceil(activePrompts.length * ((100-eliminationPct)/100)**2)) * imagesPhase3);

  // Show loading state while initial data is being fetched
  if (!settingsLoaded) {
    return <PageLoader message="Loading tournament configuration..." />;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header with save indicator */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Trophy className="text-yellow-400" size={28} />
          <div>
            <h2 className="text-2xl font-bold text-white">Find Best Prompt</h2>
            <p className="text-slate-400 text-sm">Tournament-style elimination to find the winning prompt</p>
          </div>
        </div>
        {/* Autosave indicator */}
        <div className={`text-xs px-2 py-1 rounded transition-opacity duration-300 ${
          saveStatus === 'idle' ? 'opacity-0' : 'opacity-100'
        } ${saveStatus === 'saving' ? 'bg-yellow-900/50 text-yellow-400' : 'bg-green-900/50 text-green-400'}`}>
          {saveStatus === 'saving' ? '⏳ Saving...' : '✓ Saved'}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Config Panel */}
        <div className="lg:col-span-2 space-y-4">
          {/* Prompts - Blacklist mode */}
          <ConfigCard
            title="Prompts to Exclude"
            subtitle={`${activePrompts.length} active / ${excludedPrompts.length} excluded`}>
            <div className="text-xs text-slate-500 mb-2">Click to exclude prompts from testing (all others will be tested)</div>
            <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
              {prompts.map(p => (
                <ToggleChip key={p} label={p.replace('get_analyzer_prompt_', '').slice(0, 18)}
                  active={excludedPrompts.includes(p)}
                  onClick={() => toggleItem(p, excludedPrompts, setExcludedPrompts)}
                  disabled={!!isRunning} color="red" invertColors />
              ))}
            </div>
          </ConfigCard>

          {/* Symbols & Timeframes */}
          <div className="grid grid-cols-2 gap-4">
            <ConfigCard
              title="Symbols"
              subtitle={isRandomSymbols ? '🎲 Random' : `${selectedSymbols.length} selected`}
              dimmed={isRandomSymbols}>
              {isRandomSymbols && (
                <div className="text-xs text-yellow-500 mb-2 flex items-center gap-1">
                  ⚠️ Ignored - using random symbols
                </div>
              )}
              <div className={`flex flex-wrap gap-2 ${isRandomSymbols ? 'opacity-40 pointer-events-none' : ''}`}>
                {symbols.map(s => (
                  <ToggleChip key={s} label={s.replace('USDT', '')} color="green"
                    active={selectedSymbols.includes(s)} onClick={() => toggleItem(s, selectedSymbols, setSelectedSymbols)}
                    disabled={!!isRunning || isRandomSymbols} />
                ))}
              </div>
            </ConfigCard>
            <ConfigCard
              title="Timeframes"
              subtitle={isRandomTimeframes ? '🎲 Random' : `${selectedTimeframes.length} selected`}
              dimmed={isRandomTimeframes}>
              {isRandomTimeframes && (
                <div className="text-xs text-yellow-500 mb-2 flex items-center gap-1">
                  ⚠️ Ignored - using random timeframes
                </div>
              )}
              <div className={`flex flex-wrap gap-2 ${isRandomTimeframes ? 'opacity-40 pointer-events-none' : ''}`}>
                {availableTimeframes.map(t => (
                  <ToggleChip key={t} label={t} color="purple"
                    active={selectedTimeframes.includes(t)} onClick={() => toggleItem(t, selectedTimeframes, setSelectedTimeframes)}
                    disabled={!!isRunning || isRandomTimeframes} />
                ))}
              </div>
            </ConfigCard>
          </div>

          {/* Advanced Settings */}
          <button onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-slate-400 hover:text-white text-sm">
            <Settings size={14} /> {showAdvanced ? 'Hide' : 'Show'} Advanced Settings
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-slate-800/30 p-4 rounded-lg">
              <div className="relative group">
                <label className="text-xs text-slate-400 flex items-center gap-1">
                  Model
                  <span className="text-amber-400 cursor-help" title="Currently uses OpenAI Assistant API. Actual model is determined by the Assistant configuration on OpenAI platform.">ⓘ</span>
                </label>
                <select value={model} onChange={e => setModel(e.target.value)} disabled={!!isRunning}
                  className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm">
                  {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <div className="absolute z-10 left-0 top-full mt-1 w-64 p-2 bg-slate-900 border border-slate-600 rounded text-xs text-slate-300 hidden group-hover:block shadow-lg">
                  <p className="text-amber-400 font-medium mb-1">⚠️ Assistant API Mode</p>
                  <p>Currently using OpenAI Assistants API. The actual model is determined by the Assistant configuration on the OpenAI platform, not this dropdown.</p>
                  <p className="mt-1 text-slate-400">Future: Direct API calls will use selected model.</p>
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-400">Elimination %</label>
                <input type="number" min={20} max={80} value={eliminationPct} onChange={e => setEliminationPct(Number(e.target.value))}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-400">Image Offset</label>
                <input type="number" min={0} max={500} value={imageOffset} onChange={e => setImageOffset(Number(e.target.value))}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-400">Image Selection</label>
                <select value={selectionStrategy} onChange={e => setSelectionStrategy(e.target.value as 'random' | 'sequential')}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm">
                  <option value="random">Random</option>
                  <option value="sequential">Sequential</option>
                </select>
              </div>
              {/* Random options - only show when random is selected */}
              {selectionStrategy === 'random' && (
                <div className="col-span-2 md:col-span-4 flex gap-4 bg-slate-900/50 p-3 rounded border border-yellow-900/50">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={randomSymbols} onChange={e => setRandomSymbols(e.target.checked)}
                      disabled={!!isRunning} className="rounded bg-slate-700 border-slate-600" />
                    <span className="text-slate-300">🎲 Random Symbols</span>
                    <span className="text-xs text-slate-500">(ignore symbol selection)</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={randomTimeframes} onChange={e => setRandomTimeframes(e.target.checked)}
                      disabled={!!isRunning} className="rounded bg-slate-700 border-slate-600" />
                    <span className="text-slate-600">🎲 Random Timeframes</span>
                    <span className="text-xs text-slate-500">(ignore timeframe selection)</span>
                  </label>
                </div>
              )}
              <div>
                <label className="text-xs text-slate-400">Phase 1 Images</label>
                <input type="number" min={5} max={50} value={imagesPhase1} onChange={e => setImagesPhase1(Number(e.target.value))}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-400">Phase 2 Images</label>
                <input type="number" min={10} max={100} value={imagesPhase2} onChange={e => setImagesPhase2(Number(e.target.value))}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
              </div>
              <div>
                <label className="text-xs text-slate-400">Phase 3 Images</label>
                <input type="number" min={20} max={200} value={imagesPhase3} onChange={e => setImagesPhase3(Number(e.target.value))}
                  disabled={!!isRunning} className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
              </div>
              <div className="col-span-2 md:col-span-4 pt-2 border-t border-slate-700">
                <label className="text-xs text-slate-400 block mb-2">Ranking Strategy</label>
                <div className="flex gap-3">
                  {[
                    { id: 'wilson', label: 'Wilson Lower Bound', desc: 'Conservative, sample-size aware (recommended)' },
                    { id: 'win_rate', label: 'Win Rate', desc: 'Simple win rate ranking' },
                    { id: 'pnl', label: 'Avg PnL', desc: 'Focus on profitability' },
                  ].map(s => (
                    <button key={s.id} onClick={() => setRankingStrategy(s.id as typeof rankingStrategy)}
                      disabled={!!isRunning}
                      className={`flex-1 p-2 rounded border text-left ${
                        rankingStrategy === s.id
                          ? 'border-yellow-500 bg-yellow-900/20'
                          : 'border-slate-600 bg-slate-800/50 hover:border-slate-500'
                      } ${isRunning ? 'opacity-50 cursor-not-allowed' : ''}`}>
                      <div className="text-white text-sm font-medium">{s.label}</div>
                      <div className="text-slate-400 text-xs">{s.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* HOLD Penalty Settings */}
              <div className="col-span-2 md:col-span-4 pt-2 border-t border-slate-700">
                <label className="text-xs text-slate-400 block mb-2">HOLD Penalty (Opportunity Cost)</label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-slate-500">Min Trades to Survive</label>
                    <input type="number" min={0} max={10} value={minTradesForSurvival}
                      onChange={e => setMinTradesForSurvival(Number(e.target.value))}
                      disabled={!!isRunning}
                      className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
                    <span className="text-xs text-slate-500">0 = disabled, 1+ = require trades</span>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500">Hold Penalty (%)</label>
                    <input type="number" step={0.05} min={-1} max={0} value={holdPenalty}
                      onChange={e => setHoldPenalty(Number(e.target.value))}
                      disabled={!!isRunning}
                      className="w-full mt-1 bg-slate-700 text-white rounded px-2 py-1.5 text-sm" />
                    <span className="text-xs text-slate-500">Penalty per HOLD (e.g., -0.1%)</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Panel - Actions */}
        <div className="space-y-4">
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <h3 className="text-white font-medium mb-3 flex items-center gap-2">
              <Zap className="text-yellow-400" size={16} /> Tournament Summary
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">Prompts:</span><span className="text-white">{activePrompts.length}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Symbols:</span><span className="text-white">{isRandomSymbols ? 'Random' : selectedSymbols.length}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Timeframes:</span><span className="text-white">{isRandomTimeframes ? 'Random' : selectedTimeframes.length}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Phases:</span><span className="text-white">3</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Est. API Calls:</span><span className="text-yellow-400">~{estimatedCalls}</span></div>
            </div>
          </div>

          <button onClick={isRunning ? cancelTournament : startTournament}
            disabled={!isRunning && (activePrompts.length < 2 || (!isRandomSymbols && selectedSymbols.length === 0))}
            className={`w-full flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition ${
              isRunning ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-yellow-600 hover:bg-yellow-700 text-white disabled:opacity-50 disabled:cursor-not-allowed'
            }`}>
            {isRunning ? <><Square size={18} /> Cancel</> : <><Trophy size={18} /> Start Tournament</>}
          </button>
        </div>
      </div>

      {/* Tournament Progress */}
      {tournament && (
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <StatusBadge status={tournament.status} />
              <span className="text-slate-400 text-sm font-mono">{tournament.tournamentId}</span>
            </div>
            <span className="text-white font-bold text-2xl">{tournament.progress}%</span>
          </div>

          <div className="w-full bg-slate-700 rounded-full h-4 overflow-hidden mb-4">
            <div className={`h-full transition-all duration-300 ${
              tournament.status === 'failed' ? 'bg-red-500' : tournament.status === 'completed' ? 'bg-green-500' : 'bg-yellow-500'
            }`} style={{ width: `${tournament.progress}%` }} />
          </div>

          {/* Live Rankings */}
          {tournament.rankings.length > 0 && (
            <div className="mb-4">
              <h4 className="text-white text-sm font-medium mb-2">Live Rankings ({rankingStrategy === 'wilson' ? 'Wilson' : rankingStrategy === 'pnl' ? 'PnL' : 'Win Rate'})</h4>
              <div className="space-y-1">
                {tournament.rankings.slice(0, 5).map((r, i) => (
                  <div key={r.prompt} className="flex items-center gap-2 text-sm">
                    {i === 0 ? <Crown className="text-yellow-400" size={14} /> :
                     i === 1 ? <Medal className="text-slate-300" size={14} /> :
                     i === 2 ? <Award className="text-amber-600" size={14} /> :
                     <span className="w-3.5 text-center text-slate-500">{i+1}</span>}
                    <span className="text-white flex-1 truncate">{r.prompt.replace('get_analyzer_prompt_', '')}</span>
                    {rankingStrategy === 'wilson' && r.wilson_lower !== undefined && (
                      <span className="text-purple-400 text-xs" title="Wilson Lower Bound">W:{r.wilson_lower.toFixed(1)}%</span>
                    )}
                    <span className="text-green-400">{r.win_rate.toFixed(1)}%</span>
                    <span className={r.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>{r.avg_pnl.toFixed(2)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Logs */}
          {tournament.logs.length > 0 && (
            <div className="bg-slate-900/50 rounded border border-slate-700 p-3 max-h-64 overflow-y-auto">
              <div className="text-xs text-slate-500 mb-1">Live Output</div>
              <div className="font-mono text-xs space-y-0.5">
                {tournament.logs.slice(-25).map((log, i) => (
                  <div key={i} className={
                    log.includes('❌') || log.includes('ERROR') || log.includes('Traceback') ? 'text-red-400 font-medium' :
                    log.includes('⚠️') || log.includes('WARNING') ? 'text-yellow-400' :
                    log.includes('Eliminated') ? 'text-orange-400' :
                    log.includes('INFO:') ? 'text-blue-400' :
                    'text-slate-400'
                  }>{log}</div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </div>
          )}

          {/* Error Display */}
          {tournament.result?.error && (
            <div className="mt-4 p-4 bg-red-900/30 border border-red-600 rounded-lg">
              <div className="flex items-center gap-2 text-red-400 mb-2">
                <span className="text-lg">❌</span>
                <span className="font-medium">Tournament Failed</span>
              </div>
              <pre className="text-xs text-red-300 bg-red-950/50 p-3 rounded overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                {tournament.result.error}
              </pre>
            </div>
          )}

          {/* Winner Display */}
          {tournament.result && !tournament.result.error && tournament.status === 'completed' && (
            <div className="mt-4 p-4 bg-gradient-to-r from-yellow-900/30 to-amber-900/30 border border-yellow-600 rounded-lg">
              <div className="flex items-center gap-3 mb-3">
                <Trophy className="text-yellow-400" size={24} />
                <div>
                  <div className="text-yellow-400 text-sm">Tournament Winner ({tournament.result.ranking_strategy || 'wilson'})</div>
                  <div className="text-white text-xl font-bold">{tournament.result.winner?.replace('get_analyzer_prompt_', '')}</div>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-3 text-center">
                {tournament.result.wilson_lower !== undefined && (
                  <div><div className="text-2xl font-bold text-purple-400">{tournament.result.wilson_lower.toFixed(1)}%</div><div className="text-xs text-slate-400">Wilson LB</div></div>
                )}
                <div><div className="text-2xl font-bold text-green-400">{tournament.result.win_rate.toFixed(1)}%</div><div className="text-xs text-slate-400">Win Rate</div></div>
                <div><div className={`text-2xl font-bold ${tournament.result.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{tournament.result.avg_pnl.toFixed(2)}%</div><div className="text-xs text-slate-400">Avg PnL</div></div>
                <div><div className="text-2xl font-bold text-blue-400">{tournament.result.total_api_calls}</div><div className="text-xs text-slate-400">API Calls</div></div>
                <div><div className="text-2xl font-bold text-slate-300">{(tournament.result.duration_sec / 60).toFixed(1)}m</div><div className="text-xs text-slate-400">Duration</div></div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent Runs */}
      {recentRuns.length > 0 && (
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <h3 className="text-white font-medium mb-3 flex items-center gap-2">
            <TrendingUp size={18} className="text-blue-400" /> Recent Tournament Runs
          </h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {recentRuns.map(run => (
              <div key={run.id} onClick={() => loadRunDetails(run.tournament_id)}
                className="bg-slate-900/50 rounded p-3 text-sm cursor-pointer hover:bg-slate-800/70 transition group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${run.status === 'completed' ? 'bg-green-500' : run.status === 'running' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                    <span className="text-slate-300 font-mono text-xs">{run.tournament_id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-500 text-xs">{new Date(run.started_at).toLocaleString()}</span>
                    <ChevronRight size={14} className="text-slate-500 group-hover:text-blue-400 transition" />
                  </div>
                </div>
                {run.winner && (
                  <div className="flex items-center gap-4 text-xs">
                    <span className="text-yellow-400 flex items-center gap-1"><Trophy size={12} />{run.winner.replace('get_analyzer_prompt_', '')}</span>
                    <span className="text-green-400">{run.win_rate?.toFixed(1)}% WR</span>
                    <span className={run.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>{run.avg_pnl?.toFixed(2)}% PnL</span>
                    <span className="text-slate-500">{run.config?.model}</span>
                    <span className="text-slate-500">seed: {run.random_seed}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tournament Details Modal */}
      {selectedRun && (
        <TournamentDetailModal run={selectedRun} onClose={() => setSelectedRun(null)} loading={loadingRunDetails}
          copiedField={copiedField} copyToClipboard={copyToClipboard} onVerifyTrades={() => setVerifyModalOpen(true)} />
      )}

      {/* Trade Verification Modal */}
      {verifyModalOpen && selectedRun && (
        <TradeVerificationModal
          isOpen={verifyModalOpen}
          onClose={() => setVerifyModalOpen(false)}
          tournament={{ id: selectedRun.tournament_id, phase_details: selectedRun.phase_details as Record<string, { trades: Array<{ prompt: string; image: string; symbol: string; direction: string; entry_price: number; stop_loss: number; take_profit: number; outcome: string; pnl: number; exit_price?: number; exit_reason?: string }>; prompts_tested: string[]; images_count: number }> }}
        />
      )}
    </div>
  );
}

// Helper Components
const ConfigCard = ({ title, subtitle, children, dimmed }: { title: string; subtitle?: string; children: React.ReactNode; dimmed?: boolean }) => (
  <div className={`bg-slate-800/50 rounded-lg p-4 border ${dimmed ? 'border-yellow-900/50' : 'border-slate-700'}`}>
    <div className="flex justify-between items-center mb-3">
      <h3 className={`font-medium ${dimmed ? 'text-slate-400' : 'text-white'}`}>{title}</h3>
      {subtitle && <span className={`text-xs ${subtitle.includes('🎲') ? 'text-yellow-400' : 'text-slate-400'}`}>{subtitle}</span>}
    </div>
    {children}
  </div>
);

const ToggleChip = ({ label, active, onClick, disabled, color = 'blue', invertColors = false }:
  { label: string; active: boolean; onClick: () => void; disabled: boolean; color?: string; invertColors?: boolean }) => {
  // invertColors: when true, active = excluded (red/strikethrough), inactive = included
  const isExcluded = invertColors ? active : false;
  const isActive = invertColors ? !active : active;

  const colorMap: Record<string, string> = {
    blue: 'bg-blue-600',
    green: 'bg-green-600',
    purple: 'bg-purple-600',
    red: 'bg-red-600'
  };

  return (
    <button onClick={onClick} disabled={disabled}
      className={`text-xs px-3 py-1.5 rounded transition ${
        isExcluded
          ? 'bg-red-900/50 text-red-400 line-through border border-red-800'
          : isActive
            ? `${colorMap[color] || colorMap.blue} text-white`
            : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
      {label}
    </button>
  );
};

const StatusBadge = ({ status }: { status: string }) => {
  const config: Record<string, { color: string; label: string }> = {
    pending: { color: 'text-yellow-400', label: 'Pending' },
    running: { color: 'text-blue-400', label: 'Running' },
    completed: { color: 'text-green-400', label: 'Completed' },
    failed: { color: 'text-red-400', label: 'Failed' },
    cancelled: { color: 'text-slate-400', label: 'Cancelled' },
  };
  const { color, label } = config[status] || config.running;
  return (
    <span className={`flex items-center gap-1 ${color}`}>
      {status === 'running' && <Loader2 size={14} className="animate-spin" />}
      <span className="text-xs font-medium">{label}</span>
    </span>
  );
};

// Tournament Details Modal Component
interface TournamentDetailModalProps {
  run: {
    tournament_id: string; started_at: string; finished_at: string; status: string;
    winner: string; win_rate: number; avg_pnl: number; random_seed: number;
    config: Record<string, unknown>; phase_details: Record<string, unknown>; result: Record<string, unknown>;
    total_api_calls: number; duration_sec: number;
  };
  onClose: () => void;
  loading: boolean;
  copiedField: string | null;
  copyToClipboard: (text: string, field: string) => void;
  onVerifyTrades: () => void;
}

const TournamentDetailModal = ({ run, onClose, loading, copiedField, copyToClipboard, onVerifyTrades }: TournamentDetailModalProps) => {
  const config = (run.config || {}) as { symbols?: string[]; timeframes?: string[]; model?: string; prompts?: string[];
    images_phase_1?: number; images_phase_2?: number; images_phase_3?: number; elimination_pct?: number;
    ranking_strategy?: string; selection_strategy?: string; image_offset?: number };
  const result = (run.result || {}) as { rankings?: Array<{ rank: number; prompt: string; win_rate: number; avg_pnl: number; trades: number; wilson_lower?: number }> };
  const phaseDetails = (run.phase_details || {}) as Record<string, { prompts?: string[]; images?: number; eliminated?: string[] }>;

  const formatDuration = (sec: number) => {
    if (sec < 60) return `${sec.toFixed(0)}s`;
    if (sec < 3600) return `${(sec / 60).toFixed(1)}m`;
    return `${(sec / 3600).toFixed(1)}h`;
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-slate-900 rounded-xl border border-slate-700 max-w-4xl w-full max-h-[90vh] overflow-hidden shadow-2xl"
        onClick={e => e.stopPropagation()}>
        {loading ? (
          <div className="flex items-center justify-center py-20"><Loader2 size={32} className="animate-spin text-blue-400" /></div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-700 bg-slate-800/50">
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-lg font-semibold text-white">Tournament Details</h2>
                  <StatusBadge status={run.status} />
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                  <span className="font-mono">{run.tournament_id}</span>
                  <button onClick={() => copyToClipboard(run.tournament_id, 'id')}
                    className="hover:text-blue-400 transition">
                    {copiedField === 'id' ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={onVerifyTrades}
                  className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
                  <Eye size={16} /> Verify Trades
                </button>
                <button onClick={onClose} className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-700 transition">
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-4 overflow-y-auto max-h-[calc(90vh-80px)] space-y-4">
              {/* Winner Banner */}
              {run.winner && (
                <div className="bg-gradient-to-r from-yellow-900/30 to-amber-900/30 border border-yellow-800/50 rounded-lg p-4">
                  <div className="flex items-center gap-3">
                    <Trophy size={28} className="text-yellow-400" />
                    <div>
                      <div className="text-xs text-yellow-400/80 uppercase tracking-wide">Winner</div>
                      <div className="text-lg font-semibold text-yellow-300">{String(run.winner).replace('get_analyzer_prompt_', '')}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-4 gap-4 mt-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-green-400">{(Number(run.win_rate) || 0).toFixed(1)}%</div>
                      <div className="text-xs text-slate-400">Win Rate</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold ${(Number(run.avg_pnl) || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{(Number(run.avg_pnl) || 0).toFixed(2)}%</div>
                      <div className="text-xs text-slate-400">Avg PnL</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-400">{Number(run.total_api_calls) || 0}</div>
                      <div className="text-xs text-slate-400">API Calls</div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-slate-300">{formatDuration(Number(run.duration_sec) || 0)}</div>
                      <div className="text-xs text-slate-400">Duration</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Config & Timing Grid */}
              <div className="grid md:grid-cols-2 gap-4">
                {/* Configuration */}
                <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2"><Target size={14} /> Configuration</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-slate-400">Model</span><span className="text-white font-mono">{String(config.model || '—')}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Ranking</span><span className="text-white">{String(config.ranking_strategy || 'wilson')}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Selection</span><span className="text-white">{String(config.selection_strategy || 'random')}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Elimination</span><span className="text-white">{Number(config.elimination_pct) || 0}%</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Image Offset</span><span className="text-white">{Number(config.image_offset) || 0}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Random Seed</span><span className="text-yellow-400 font-mono">{Number(run.random_seed) || 0}</span></div>
                  </div>
                </div>

                {/* Timing */}
                <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2"><Clock size={14} /> Timing</h3>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between"><span className="text-slate-400">Started</span><span className="text-white">{run.started_at ? new Date(run.started_at).toLocaleString() : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Finished</span><span className="text-white">{run.finished_at ? new Date(run.finished_at).toLocaleString() : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Duration</span><span className="text-white">{formatDuration(Number(run.duration_sec) || 0)}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Symbols</span><span className="text-white">{Array.isArray(config.symbols) ? config.symbols.join(', ') : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Timeframes</span><span className="text-white">{Array.isArray(config.timeframes) ? config.timeframes.join(', ') : '—'}</span></div>
                    <div className="flex justify-between"><span className="text-slate-400">Images/Phase</span><span className="text-white">{Number(config.images_phase_1) || 0} → {Number(config.images_phase_2) || 0} → {Number(config.images_phase_3) || 0}</span></div>
                  </div>
                </div>
              </div>

              {/* Phase Details - Detailed breakdown */}
              {phaseDetails && typeof phaseDetails === 'object' && Object.keys(phaseDetails).length > 0 && (
                <div className="space-y-3">
                  {Object.entries(phaseDetails).sort().map(([phase, data]) => {
                    const phaseData = (data && typeof data === 'object') ? data as Record<string, unknown> : {};
                    const promptsTested = Array.isArray(phaseData.prompts_tested) ? phaseData.prompts_tested : [];
                    const imagesCount = typeof phaseData.images_count === 'number' ? phaseData.images_count : 0;
                    const trades = Array.isArray(phaseData.trades) ? phaseData.trades as Array<Record<string, unknown>> : [];
                    const eliminated = Array.isArray(phaseData.eliminated) ? phaseData.eliminated : [];
                    const rankings = Array.isArray(phaseData.rankings) ? phaseData.rankings as Array<Record<string, unknown>> : [];
                    const analyses = Array.isArray(phaseData.analyses) ? phaseData.analyses as Array<Record<string, unknown>> : [];
                    const apiCalls = analyses.length;
                    const wins = trades.filter(t => String(t.outcome).toUpperCase() === 'WIN').length;
                    const losses = trades.filter(t => String(t.outcome).toUpperCase() === 'LOSS').length;

                    return (
                      <details key={phase} className="bg-slate-800/50 rounded-lg border border-slate-700 group">
                        <summary className="p-4 cursor-pointer hover:bg-slate-800/70 transition flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <BarChart3 size={16} className="text-blue-400" />
                            <span className="text-white font-medium uppercase">{String(phase).replace('_', ' ')}</span>
                          </div>
                          <div className="flex items-center gap-4 text-xs">
                            <span className="text-slate-400">{promptsTested.length} prompts</span>
                            <span className="text-slate-400">{imagesCount} images</span>
                            <span className="text-blue-400">{apiCalls} API calls</span>
                            <span className="text-green-400">{wins}W</span>
                            <span className="text-red-400">{losses}L</span>
                            {eliminated.length > 0 && <span className="text-orange-400">−{eliminated.length} eliminated</span>}
                          </div>
                        </summary>
                        <div className="p-4 pt-0 space-y-3 border-t border-slate-700">
                          {/* Phase Rankings */}
                          {rankings.length > 0 && (
                            <div>
                              <div className="text-xs text-slate-400 mb-2">Rankings after this phase:</div>
                              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                                {rankings.map((r, i) => (
                                  <div key={i} className={`text-xs p-2 rounded ${r.survived ? 'bg-green-900/30 border border-green-800/50' : 'bg-red-900/30 border border-red-800/50'}`}>
                                    <div className="font-mono text-white truncate">{String(r.prompt || '').replace('get_analyzer_prompt_', '')}</div>
                                    <div className="flex gap-2 mt-1 text-slate-400">
                                      <span>{(Number(r.win_rate) || 0).toFixed(0)}% WR</span>
                                      <span className={Number(r.avg_pnl) >= 0 ? 'text-green-400' : 'text-red-400'}>{(Number(r.avg_pnl) || 0).toFixed(2)}%</span>
                                      <span>{Number(r.trades) || 0}T</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {/* Trades */}
                          {trades.length > 0 && (
                            <details className="mt-2">
                              <summary className="text-xs text-slate-400 cursor-pointer hover:text-white">View {trades.length} trades</summary>
                              <div className="mt-2 max-h-48 overflow-y-auto space-y-1">
                                {trades.map((t, i) => (
                                  <div key={i} className={`text-xs p-2 rounded flex justify-between ${String(t.outcome).toUpperCase() === 'WIN' ? 'bg-green-900/20' : 'bg-red-900/20'}`}>
                                    <span className="font-mono text-slate-300">{String(t.symbol || '')} • {String(t.direction || '').toUpperCase()}</span>
                                    <span className={String(t.outcome).toUpperCase() === 'WIN' ? 'text-green-400' : 'text-red-400'}>
                                      {String(t.outcome)} {Number(t.pnl) >= 0 ? '+' : ''}{(Number(t.pnl) || 0).toFixed(2)}%
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}
                        </div>
                      </details>
                    );
                  })}
                </div>
              )}

              {/* Full Rankings Table */}
              {Array.isArray(result.rankings) && result.rankings.length > 0 && (
                <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <h3 className="text-sm font-medium text-white mb-3 flex items-center gap-2"><Award size={14} /> Final Rankings</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-slate-400 text-xs border-b border-slate-700">
                          <th className="text-left py-2 px-2">#</th>
                          <th className="text-left py-2 px-2">Prompt</th>
                          <th className="text-right py-2 px-2">Win Rate</th>
                          <th className="text-right py-2 px-2">Avg PnL</th>
                          <th className="text-right py-2 px-2">Trades</th>
                          <th className="text-right py-2 px-2">Wilson LB</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.rankings.map((r, i) => {
                          const rank = Number(r.rank) || i + 1;
                          const prompt = String(r.prompt || '');
                          const winRate = Number(r.win_rate) || 0;
                          const avgPnl = Number(r.avg_pnl) || 0;
                          const trades = Number(r.trades) || 0;
                          const wilsonLower = Number(r.wilson_lower) || 0;
                          return (
                            <tr key={i} className={`border-b border-slate-700/50 ${i === 0 ? 'bg-yellow-900/20' : ''}`}>
                              <td className="py-2 px-2">
                                {i === 0 ? <Crown size={14} className="text-yellow-400" /> :
                                 i === 1 ? <Medal size={14} className="text-slate-300" /> :
                                 i === 2 ? <Award size={14} className="text-amber-600" /> :
                                 <span className="text-slate-500">{rank}</span>}
                              </td>
                              <td className="py-2 px-2 text-white font-mono text-xs">{prompt.replace('get_analyzer_prompt_', '')}</td>
                              <td className="py-2 px-2 text-right text-green-400">{winRate.toFixed(1)}%</td>
                              <td className={`py-2 px-2 text-right ${avgPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>{avgPnl.toFixed(2)}%</td>
                              <td className="py-2 px-2 text-right text-slate-300">{trades}</td>
                              <td className="py-2 px-2 text-right text-purple-400">{wilsonLower.toFixed(1)}%</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Prompts Tested */}
              {Array.isArray(config.prompts) && config.prompts.length > 0 && (
                <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <h3 className="text-sm font-medium text-white mb-3">Prompts Tested ({config.prompts.length})</h3>
                  <div className="flex flex-wrap gap-2">
                    {config.prompts.map((p, i) => (
                      <span key={i} className={`text-xs px-2 py-1 rounded ${String(p) === run.winner ? 'bg-yellow-600/30 text-yellow-300 border border-yellow-700' : 'bg-slate-700 text-slate-300'}`}>
                        {String(p).replace('get_analyzer_prompt_', '')}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};


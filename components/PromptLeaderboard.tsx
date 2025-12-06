'use client';

import { useState, useMemo } from 'react';
import { Trophy, Filter, ArrowUpDown, ArrowUp, ArrowDown, Shield, AlertTriangle } from 'lucide-react';
import type { PromptStats } from '@/types/learning';

interface PromptLeaderboardProps {
  prompts: PromptStats[];
}

type SortKey = 'avg_pnl_pct' | 'win_rate' | 'total_trades' | 'symbol_count';
type SortDir = 'asc' | 'desc';

export default function PromptLeaderboard({ prompts }: PromptLeaderboardProps) {
  const [minTrades, setMinTrades] = useState(10);
  const [minSymbols, setMinSymbols] = useState(2);
  const [sortKey, setSortKey] = useState<SortKey>('avg_pnl_pct');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const filtered = useMemo(() => {
    return prompts
      .filter(p => p.total_trades >= minTrades && (p.symbol_count || 0) >= minSymbols)
      .sort((a, b) => {
        const aVal = a[sortKey] ?? 0;
        const bVal = b[sortKey] ?? 0;
        return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
      });
  }, [prompts, minTrades, minSymbols, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ArrowUpDown size={12} className="text-slate-500" />;
    return sortDir === 'desc' ? <ArrowDown size={12} className="text-blue-400" /> : <ArrowUp size={12} className="text-blue-400" />;
  };

  const getConfidenceBadge = (trades: number, symbols: number) => {
    if (trades >= 50 && symbols >= 5) return { label: 'High', color: 'bg-green-600', icon: Shield };
    if (trades >= 20 && symbols >= 3) return { label: 'Medium', color: 'bg-yellow-600', icon: Shield };
    return { label: 'Low', color: 'bg-red-600', icon: AlertTriangle };
  };

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-white font-semibold flex items-center gap-2">
          <Trophy size={16} className="text-yellow-400" /> Prompt Leaderboard
        </h3>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <Filter size={12} className="text-slate-400" />
            <span className="text-slate-400">Min Trades:</span>
            <input
              type="range" min={1} max={50} value={minTrades}
              onChange={e => setMinTrades(Number(e.target.value))}
              className="w-20 accent-blue-500"
            />
            <span className="text-white w-6">{minTrades}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Min Symbols:</span>
            <input
              type="range" min={1} max={10} value={minSymbols}
              onChange={e => setMinSymbols(Number(e.target.value))}
              className="w-16 accent-blue-500"
            />
            <span className="text-white w-4">{minSymbols}</span>
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-slate-400 text-sm text-center py-8">No prompts match filters. Try lowering minimums.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-2">#</th>
                <th className="text-left py-2 px-2">Prompt</th>
                <th className="text-right py-2 px-2 cursor-pointer hover:text-white" onClick={() => handleSort('avg_pnl_pct')}>
                  <span className="flex items-center justify-end gap-1">Avg PnL % <SortIcon col="avg_pnl_pct" /></span>
                </th>
                <th className="text-right py-2 px-2 cursor-pointer hover:text-white" onClick={() => handleSort('win_rate')}>
                  <span className="flex items-center justify-end gap-1">Win Rate <SortIcon col="win_rate" /></span>
                </th>
                <th className="text-right py-2 px-2 cursor-pointer hover:text-white" onClick={() => handleSort('total_trades')}>
                  <span className="flex items-center justify-end gap-1">Trades <SortIcon col="total_trades" /></span>
                </th>
                <th className="text-right py-2 px-2 cursor-pointer hover:text-white" onClick={() => handleSort('symbol_count')}>
                  <span className="flex items-center justify-end gap-1">Symbols <SortIcon col="symbol_count" /></span>
                </th>
                <th className="text-center py-2 px-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p, i) => {
                const badge = getConfidenceBadge(p.total_trades, p.symbol_count || 0);
                const BadgeIcon = badge.icon;
                return (
                  <tr key={p.prompt_name} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-2 px-2 text-slate-500">{i + 1}</td>
                    <td className="py-2 px-2">
                      <span className="text-white font-medium">
                        {p.prompt_name.replace('get_analyzer_prompt_', '').slice(0, 30)}
                      </span>
                    </td>
                    <td className={`py-2 px-2 text-right font-mono ${p.avg_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {p.avg_pnl_pct >= 0 ? '+' : ''}{p.avg_pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 px-2 text-right text-white">{p.win_rate.toFixed(1)}%</td>
                    <td className="py-2 px-2 text-right text-slate-300">{p.total_trades}</td>
                    <td className="py-2 px-2 text-right text-slate-300">{p.symbol_count || 0}</td>
                    <td className="py-2 px-2 text-center">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${badge.color}`}>
                        <BadgeIcon size={10} /> {badge.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-slate-500 text-xs mt-3">
        Showing {filtered.length} of {prompts.length} prompts • Ranked by {sortKey.replace('_', ' ')} ({sortDir})
      </p>
    </div>
  );
}


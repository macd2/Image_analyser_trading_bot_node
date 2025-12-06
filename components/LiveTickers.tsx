'use client'

import { Ticker } from '@/hooks/useRealtime'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface LiveTickersProps {
  tickers: Record<string, Ticker>;
  loading?: boolean;
}

function formatPrice(val: string | undefined): string {
  if (!val) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  return n >= 1000 ? n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : n >= 1 ? n.toFixed(4)
    : n.toFixed(6);
}

function formatPct(val: string | undefined): string {
  if (!val) return '—';
  const n = parseFloat(val) * 100;
  if (isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function formatVolume(val: string | undefined): string {
  if (!val) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(2) + 'K';
  return n.toFixed(2);
}

export default function LiveTickers({ tickers, loading }: LiveTickersProps) {
  const symbols = Object.keys(tickers);

  if (loading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card p-3 animate-pulse">
            <div className="h-4 bg-slate-700 rounded w-20 mb-2"></div>
            <div className="h-6 bg-slate-700 rounded w-24"></div>
          </div>
        ))}
      </div>
    );
  }

  if (symbols.length === 0) {
    return (
      <div className="card p-4 text-center text-slate-400">
        Connecting to Bybit...
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {symbols.map((symbol) => {
        const t = tickers[symbol];
        const pct = parseFloat(t.price24hPcnt || '0') * 100;
        const isUp = pct >= 0;

        return (
          <div key={symbol} className="card p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-bold text-white">{symbol.replace('USDT', '')}</span>
              {isUp ? (
                <TrendingUp className="w-3 h-3 text-green-400" />
              ) : (
                <TrendingDown className="w-3 h-3 text-red-400" />
              )}
            </div>
            <div className="text-lg font-bold text-white">${formatPrice(t.lastPrice)}</div>
            <div className={`text-xs ${isUp ? 'text-green-400' : 'text-red-400'}`}>
              {formatPct(t.price24hPcnt)}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Vol: {formatVolume(t.volume24h)}
            </div>
          </div>
        );
      })}
    </div>
  );
}


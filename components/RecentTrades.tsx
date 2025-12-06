'use client'

const mockTrades = [
  { id: 1, symbol: 'BTCUSDT', side: 'LONG', pnl: 526.13, time: '2 min ago' },
  { id: 2, symbol: 'ETHUSDT', side: 'LONG', pnl: 17.65, time: '15 min ago' },
  { id: 3, symbol: 'SOLUSDT', side: 'SHORT', pnl: 4.80, time: '1 hour ago' },
  { id: 4, symbol: 'ADAUSDT', side: 'LONG', pnl: -12.50, time: '2 hours ago' },
  { id: 5, symbol: 'XRPUSDT', side: 'SHORT', pnl: 8.30, time: '3 hours ago' },
]

export default function RecentTrades() {
  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4">Recent Trades</h3>
      <div className="space-y-3">
        {mockTrades.map((trade) => (
          <div key={trade.id} className="flex items-center justify-between p-3 bg-slate-700/30 rounded">
            <div>
              <p className="font-semibold text-white">{trade.symbol}</p>
              <p className="text-xs text-slate-400">{trade.time}</p>
            </div>
            <div className="text-right">
              <span className={trade.side === 'LONG' ? 'badge-long' : 'badge-short'}>
                {trade.side}
              </span>
              <p className={`text-sm font-semibold mt-1 ${trade.pnl > 0 ? 'text-positive' : 'text-negative'}`}>
                ${trade.pnl.toFixed(2)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}


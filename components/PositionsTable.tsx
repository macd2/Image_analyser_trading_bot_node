'use client'

const mockPositions = [
  {
    id: 1,
    symbol: 'BTCUSDT',
    side: 'LONG',
    entry: 42150.50,
    current: 43200.75,
    quantity: 0.05,
    pnl: 526.13,
    pnlPercent: 2.49,
    confidence: 0.87,
  },
  {
    id: 2,
    symbol: 'ETHUSDT',
    side: 'LONG',
    entry: 2280.30,
    current: 2315.60,
    quantity: 0.5,
    pnl: 17.65,
    pnlPercent: 1.55,
    confidence: 0.72,
  },
  {
    id: 3,
    symbol: 'SOLUSDT',
    side: 'SHORT',
    entry: 145.20,
    current: 142.80,
    quantity: 2.0,
    pnl: 4.80,
    pnlPercent: 1.65,
    confidence: 0.65,
  },
]

export default function PositionsTable() {
  return (
    <div className="card">
      <h3 className="text-lg font-semibold text-white mb-4">Open Positions</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left py-3 px-4 text-slate-400">Symbol</th>
              <th className="text-left py-3 px-4 text-slate-400">Side</th>
              <th className="text-right py-3 px-4 text-slate-400">Entry</th>
              <th className="text-right py-3 px-4 text-slate-400">Current</th>
              <th className="text-right py-3 px-4 text-slate-400">P&L</th>
              <th className="text-right py-3 px-4 text-slate-400">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {mockPositions.map((pos) => (
              <tr key={pos.id} className="border-b border-slate-700 hover:bg-slate-700/50">
                <td className="py-3 px-4 font-semibold">{pos.symbol}</td>
                <td className="py-3 px-4">
                  <span className={pos.side === 'LONG' ? 'badge-long' : 'badge-short'}>
                    {pos.side}
                  </span>
                </td>
                <td className="py-3 px-4 text-right">${pos.entry.toFixed(2)}</td>
                <td className="py-3 px-4 text-right">${pos.current.toFixed(2)}</td>
                <td className={`py-3 px-4 text-right font-semibold ${pos.pnl > 0 ? 'text-positive' : 'text-negative'}`}>
                  ${pos.pnl.toFixed(2)} ({pos.pnlPercent.toFixed(2)}%)
                </td>
                <td className="py-3 px-4 text-right">{(pos.confidence * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}


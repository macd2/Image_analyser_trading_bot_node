# Quick Start - Trading Bot Prototype

## Installation

```bash
cd NextJsAppBot/V2/prototype
pnpm install
```

## Run

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000)

## What You'll See

### Dashboard Tab
- 4 stat cards (Total P&L, Win Rate, Active Positions, Trades Today)
- Open positions table with 3 mock trades
- Recent trades widget

### Positions Tab
- Summary stats (Total Positions, Exposure, Unrealized P&L, Avg Confidence)
- Detailed positions table

### Trades Tab
- Trade history stats (Total Trades, Win Rate, Total P&L, Avg Win)
- Complete trade history table

## Mock Data

All data is hardcoded in components. To modify:

1. **Positions**: Edit `components/PositionsTable.tsx` → `mockPositions`
2. **Trades**: Edit `components/RecentTrades.tsx` → `mockTrades`
3. **All Trades**: Edit `components/TradesView.tsx` → `mockAllTrades`

## Styling

- **Dark theme**: Tailwind CSS with slate-950 background
- **Colors**: Green for profit, Red for loss
- **Responsive**: Works on mobile, tablet, desktop

## Next: Connect to Backend

When ready to connect to real data:

1. Replace mock data with API calls
2. Use React Query for data fetching
3. Add socket.io for real-time updates
4. Connect to Railway PostgreSQL

See `../TECH_STACK.md` for architecture details.


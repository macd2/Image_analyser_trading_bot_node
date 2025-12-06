# Trading Bot Dashboard Prototype

A visual prototype of the trading bot dashboard with mock data. No backend required - just UI components with Tailwind CSS.

## Features

- 📊 **Dashboard**: Real-time stats, open positions, recent trades
- 💼 **Positions**: Detailed view of all open positions
- 📈 **Trades**: Complete trade history with P&L
- 🎨 **Dark Theme**: Professional trading UI with Tailwind CSS
- ⚡ **Fast**: Next.js 14 with App Router

## Quick Start

```bash
# Install dependencies
pnpm install

# Run dev server
pnpm dev

# Open browser
# http://localhost:3000
```

## Project Structure

```
prototype/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Main page with tabs
│   └── globals.css         # Global styles
├── components/
│   ├── Sidebar.tsx         # Navigation sidebar
│   ├── Dashboard.tsx       # Dashboard view
│   ├── PositionsView.tsx   # Positions page
│   ├── TradesView.tsx      # Trades history page
│   ├── PositionsTable.tsx  # Positions table
│   ├── RecentTrades.tsx    # Recent trades widget
│   └── StatCard.tsx        # Stat card component
├── package.json
├── tailwind.config.js
└── tsconfig.json
```

## Mock Data

All data is hardcoded in components:
- **Positions**: 3 open positions (BTC, ETH, SOL)
- **Trades**: 5 recent trades with P&L
- **Stats**: Dashboard metrics

## Styling

- **Colors**: Dark slate theme with green/red accents
- **Framework**: Tailwind CSS
- **Icons**: Lucide React
- **Charts**: Ready for Recharts integration

## Next Steps

1. Connect to real API endpoints
2. Add WebSocket for real-time updates
3. Integrate with Bybit API
4. Add authentication
5. Implement database persistence

## Build for Production

```bash
pnpm build
pnpm start
```


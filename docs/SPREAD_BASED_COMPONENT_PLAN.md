# Spread-Based Trading Component - Implementation Plan

## Overview
Build a shared React component to visualize spread-based cointegration trades with 3 synchronized panes:
1. **Z-Score Pane** - Primary decision tool (entry/exit thresholds)
2. **Spread Price Pane** - Risk management (statistical boundaries)
3. **Asset Prices Pane** - Context only (both pair symbols)

## Data Flow Architecture

### Source: TradingCycle → Database → Component

**TradingCycle Output** (from `trading_cycle.py`):
```
strategy_metadata: {
  beta: float,                    # Hedge ratio (y = beta * x)
  spread_mean: float,             # μ (mean)
  spread_std: float,              # σ (std dev)
  z_score_at_entry: float,        # Entry z-score
  pair_symbol: string,            # Second asset (e.g., "ETHUSDT")
  z_exit_threshold: float,        # Exit threshold (e.g., 0.5)
  max_spread_deviation: float     # Adaptive SL buffer
}
```

**Database Storage** (recommendations table):
- `strategy_metadata` (JSON) - Contains all above fields
- `symbol` - Primary asset (x)
- `entry_price` - Entry price of x
- `stop_loss`, `take_profit` - Price levels
- `confidence`, `risk_reward` - Trade metrics

**Trade Table** (for exit monitoring):
- Links to recommendation via `recommendation_id`
- Tracks `fill_price`, `fill_time`, `exit_price`, `exit_reason`

## Component Architecture

### File Structure
```
components/shared/
├── SpreadTradeChart.tsx          # Main component (3 panes)
├── SpreadTradeChart.types.ts     # TypeScript interfaces
├── hooks/
│   ├── useSpreadTradeData.ts     # Fetch & manage data
│   └── useSpreadChartSync.ts     # Sync 3 panes
└── __tests__/
    └── SpreadTradeChart.test.tsx
```

### Component Props
```typescript
interface SpreadTradeChartProps {
  trade: TradeData                 # Trade with strategy_metadata
  mode?: 'live' | 'historical'    # Live or closed trade
  height?: number                  # Container height
  showAssetPrices?: boolean        # Toggle pane 3
}
```

## Data Requirements

### 1. Historical Candles
- **Endpoint**: `/api/bot/trade-candles`
- **Params**: symbol, timeframe, timestamp, before=50, after=20
- **Returns**: OHLCV candles for charting

### 2. Pair Symbol Candles
- **New Endpoint Needed**: `/api/bot/spread-pair-candles`
- **Params**: pair_symbol, timeframe, timestamp, before=50, after=20
- **Returns**: OHLCV for second asset

### 3. Z-Score History
- **Source**: Recalculate from candles using strategy_metadata
- **Formula**: `z = (spread - mean) / std` where `spread = y - beta * x`
- **No new DB needed** - calculated client-side from candles

### 4. Exit Monitoring (Live Trades)
- **Endpoint**: `/api/bot/trades/:id` (existing)
- **Returns**: Current exit_price, exit_reason, status
- **WebSocket**: Real-time updates via Socket.io

## Visualization Strategy

### Library Choice: Recharts (NOT Lightweight-charts)
**Why Recharts**:
- Multiple synchronized Y-axes (z-score, spread, prices)
- Easier to manage 3 panes with shared X-axis (time)
- Built-in legend, tooltips, responsive
- Simpler than managing 3 separate Lightweight-charts instances

### Pane 1: Z-Score
- Line chart with z-score values
- Horizontal lines: z_entry (±2.0), z_exit (±0.5)
- Background shading: mean-reverting zones
- Markers: Entry (green/red), Exit (gray)

### Pane 2: Spread Price
- Line chart with spread values
- Horizontal lines: μ, μ±2σ (entry), μ±3.5σ (stop)
- Shaded bands: entry zone, stop zone
- Markers: Entry, Exit, TP1, TP2

### Pane 3: Asset Prices
- Two line charts: price_x (ASTER), price_y (LINK)
- No markers (context only)
- Synchronized time axis with panes 1-2

## Implementation Phases

### Phase 1: Data Fetching & Types
- [ ] Create TypeScript interfaces (SpreadTradeData, StrategyMetadata)
- [ ] Implement `useSpreadTradeData` hook
- [ ] Create `/api/bot/spread-pair-candles` endpoint
- [ ] Test data flow from DB → component

### Phase 2: Z-Score Pane
- [ ] Build z-score calculation logic
- [ ] Create Recharts line chart with thresholds
- [ ] Add entry/exit markers
- [ ] Add mean-reverting background shading

### Phase 3: Spread Price Pane
- [ ] Calculate spread from candles
- [ ] Create Recharts line chart with bands
- [ ] Add TP1/TP2 markers
- [ ] Sync X-axis with pane 1

### Phase 4: Asset Prices Pane
- [ ] Fetch pair symbol candles
- [ ] Create dual-line chart
- [ ] Sync X-axis with panes 1-2
- [ ] Add toggle to show/hide

### Phase 5: Live Trade Monitoring
- [ ] Implement exit monitoring via WebSocket
- [ ] Update exit markers in real-time
- [ ] Show exit_reason tooltip
- [ ] Handle trade closure

### Phase 6: Integration & Testing
- [ ] Add to RecentTrades component
- [ ] Add to PositionsTable component
- [ ] Write unit tests
- [ ] Test with real spread-based trades

## Database Schema (No Changes Needed)
- `strategy_metadata` already stores all required fields
- `trades` table already tracks exit data
- Existing indexes sufficient for queries

## API Endpoints Needed

### New Endpoint: GET /api/bot/spread-pair-candles
```typescript
// Query params:
// - pair_symbol: string (e.g., "ETHUSDT")
// - timeframe: string (e.g., "1h")
// - timestamp: number (milliseconds)
// - before: number (default: 50)
// - after: number (default: 20)

// Response:
{
  candles: Array<{
    time: number,
    open: number,
    high: number,
    low: number,
    close: number,
    volume: number
  }>,
  pair_symbol: string,
  timeframe: string
}
```

## Key Design Decisions

1. **Recharts over Lightweight-charts**: Easier multi-pane sync
2. **Client-side z-score calculation**: No DB changes, faster
3. **Shared X-axis**: All panes show same time range
4. **Strategy metadata in DB**: Already stored, no migration needed
5. **Reuse existing candle API**: Minimize new endpoints

## Success Criteria

- [ ] Component displays 3 synchronized panes
- [ ] Z-score, spread, and prices correctly calculated
- [ ] Entry/exit markers visible and accurate
- [ ] Live trades show real-time exit updates
- [ ] Works with both live and historical trades
- [ ] Responsive design (mobile-friendly)
- [ ] Unit tests pass (>80% coverage)


# Data Architecture for Long-Term Learning

## Core Principle: Store Everything, Query Anything

The database is the brain of the system. Every decision, every market condition, every outcome is stored for future learning.

---

## Database Choice: PostgreSQL (via Railway)

**Why PostgreSQL on Railway:**
- JSONB for flexible market snapshots
- Native timestamps with timezone
- Excellent query performance
- Railway plugin = one-click setup, auto-managed
- Always available (no cold starts)
- Can export to data science tools

---

## Schema Design

### 1. Core Tables (Stage 1)

```sql
-- Trades: The most important table
CREATE TABLE trades (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
  
  -- Entry
  entry_price REAL,
  quantity REAL NOT NULL,
  stop_loss REAL,
  take_profit REAL,
  
  -- Exit
  exit_price REAL,
  pnl REAL,
  pnl_percent REAL,
  exit_reason TEXT, -- 'tp_hit', 'sl_hit', 'manual', 'liquidated'
  
  -- Exchange
  bybit_order_id TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'open', 'closed', 'cancelled', 'error')),
  
  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  opened_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ,
  
  -- Learning links
  decision_id TEXT REFERENCES decisions(id),
  prompt_version TEXT
);

CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_created ON trades(created_at DESC);

-- Positions: Live sync with exchange
CREATE TABLE positions (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol TEXT UNIQUE NOT NULL,
  side TEXT NOT NULL,
  quantity REAL NOT NULL,
  entry_price REAL NOT NULL,
  current_price REAL,
  unrealized_pnl REAL,
  unrealized_pnl_percent REAL,
  trade_id TEXT REFERENCES trades(id),
  synced_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2. Decision Tracking (Stage 4)

```sql
-- Decisions: Every analysis and its outcome
CREATE TABLE decisions (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Context (what we saw)
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  chart_image_path TEXT,
  market_snapshot JSONB, -- Full market state at decision time
  
  -- Analysis (what AI said)
  recommendation TEXT CHECK (recommendation IN ('LONG', 'SHORT', 'HOLD')),
  confidence REAL,
  entry_price REAL,
  stop_loss REAL,
  take_profit REAL,
  reasoning TEXT,
  raw_response JSONB, -- Full API response for debugging
  
  -- Execution (what we did)
  traded BOOLEAN DEFAULT FALSE,
  skip_reason TEXT, -- 'low_confidence', 'no_slots', 'risk_exceeded', etc.
  trade_id TEXT REFERENCES trades(id),
  
  -- Outcome (what happened) - filled by background job
  actual_pnl REAL,
  actual_pnl_percent REAL,
  max_favorable REAL, -- Max profit before exit
  max_adverse REAL, -- Max drawdown before exit
  hold_duration_minutes INTEGER,
  outcome_correct BOOLEAN, -- Did we predict direction correctly?
  
  -- Learning metadata
  prompt_version TEXT NOT NULL,
  model_version TEXT DEFAULT 'gpt-4-vision-preview',
  analysis_duration_ms INTEGER,
  
  -- Timestamps
  analyzed_at TIMESTAMPTZ DEFAULT NOW(),
  outcome_recorded_at TIMESTAMPTZ
);

CREATE INDEX idx_decisions_symbol ON decisions(symbol);
CREATE INDEX idx_decisions_prompt ON decisions(prompt_version);
CREATE INDEX idx_decisions_outcome ON decisions(outcome_correct);
```

### 3. Market Snapshots (Stage 4)

```sql
-- Market snapshot structure (stored as JSONB in decisions)
-- This allows us to recreate the exact market conditions at decision time

{
  "symbol": "BTCUSDT",
  "timestamp": "2024-01-15T14:00:00Z",
  "price": {
    "current": 42500.50,
    "open_24h": 41800.00,
    "high_24h": 43200.00,
    "low_24h": 41500.00,
    "change_24h_percent": 1.68
  },
  "volume": {
    "24h": 28500000000,
    "relative_to_avg": 1.2
  },
  "indicators": {
    "rsi_14": 58.5,
    "ma_50": 41200.00,
    "ma_200": 38500.00,
    "atr_14": 850.00
  },
  "funding_rate": 0.0001,
  "open_interest": 15000000000,
  "sentiment": {
    "long_short_ratio": 1.15,
    "fear_greed_index": 65
  }
}
```

### 4. Prompt Performance (Stage 4)

```sql
-- Prompt versions and their performance
CREATE TABLE prompt_versions (
  id TEXT PRIMARY KEY DEFAULT gen_random_uuid(),
  version TEXT UNIQUE NOT NULL,
  name TEXT,
  description TEXT,
  prompt_text TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  is_active BOOLEAN DEFAULT FALSE
);

-- Aggregated stats (materialized view, updated hourly)
CREATE MATERIALIZED VIEW prompt_performance AS
SELECT 
  d.prompt_version,
  COUNT(*) as total_decisions,
  COUNT(CASE WHEN d.traded THEN 1 END) as trades_taken,
  COUNT(CASE WHEN d.outcome_correct THEN 1 END) as correct_predictions,
  ROUND(AVG(d.confidence)::numeric, 3) as avg_confidence,
  ROUND(AVG(t.pnl_percent)::numeric, 2) as avg_pnl_percent,
  COUNT(CASE WHEN t.pnl > 0 THEN 1 END)::float / NULLIF(COUNT(t.id), 0) as win_rate,
  SUM(t.pnl) as total_pnl
FROM decisions d
LEFT JOIN trades t ON d.trade_id = t.id
GROUP BY d.prompt_version;

CREATE UNIQUE INDEX ON prompt_performance(prompt_version);
```

---

## Drizzle Schema (TypeScript)

```typescript
// drizzle/schema.ts
import { pgTable, text, real, boolean, timestamp, jsonb, index } from 'drizzle-orm/pg-core';
import { createId } from '@paralleldrive/cuid2';

export const trades = pgTable('trades', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  symbol: text('symbol').notNull(),
  side: text('side', { enum: ['LONG', 'SHORT'] }).notNull(),
  entryPrice: real('entry_price'),
  quantity: real('quantity').notNull(),
  stopLoss: real('stop_loss'),
  takeProfit: real('take_profit'),
  exitPrice: real('exit_price'),
  pnl: real('pnl'),
  pnlPercent: real('pnl_percent'),
  exitReason: text('exit_reason'),
  bybitOrderId: text('bybit_order_id'),
  status: text('status', { enum: ['pending', 'open', 'closed', 'cancelled', 'error'] }).default('pending'),
  createdAt: timestamp('created_at').defaultNow(),
  openedAt: timestamp('opened_at'),
  closedAt: timestamp('closed_at'),
  decisionId: text('decision_id'),
  promptVersion: text('prompt_version'),
}, (table) => ({
  symbolIdx: index('idx_trades_symbol').on(table.symbol),
  statusIdx: index('idx_trades_status').on(table.status),
}));

export const positions = pgTable('positions', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  symbol: text('symbol').notNull().unique(),
  side: text('side', { enum: ['LONG', 'SHORT'] }).notNull(),
  quantity: real('quantity').notNull(),
  entryPrice: real('entry_price').notNull(),
  currentPrice: real('current_price'),
  unrealizedPnl: real('unrealized_pnl'),
  unrealizedPnlPercent: real('unrealized_pnl_percent'),
  tradeId: text('trade_id').references(() => trades.id),
  syncedAt: timestamp('synced_at').defaultNow(),
});

export const decisions = pgTable('decisions', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  symbol: text('symbol').notNull(),
  timeframe: text('timeframe').notNull(),
  chartImagePath: text('chart_image_path'),
  marketSnapshot: jsonb('market_snapshot'),
  recommendation: text('recommendation', { enum: ['LONG', 'SHORT', 'HOLD'] }),
  confidence: real('confidence'),
  entryPrice: real('entry_price'),
  stopLoss: real('stop_loss'),
  takeProfit: real('take_profit'),
  reasoning: text('reasoning'),
  rawResponse: jsonb('raw_response'),
  traded: boolean('traded').default(false),
  skipReason: text('skip_reason'),
  tradeId: text('trade_id').references(() => trades.id),
  actualPnl: real('actual_pnl'),
  actualPnlPercent: real('actual_pnl_percent'),
  maxFavorable: real('max_favorable'),
  maxAdverse: real('max_adverse'),
  holdDurationMinutes: real('hold_duration_minutes'),
  outcomeCorrect: boolean('outcome_correct'),
  promptVersion: text('prompt_version').notNull(),
  modelVersion: text('model_version').default('gpt-4-vision-preview'),
  analysisDurationMs: real('analysis_duration_ms'),
  analyzedAt: timestamp('analyzed_at').defaultNow(),
  outcomeRecordedAt: timestamp('outcome_recorded_at'),
}, (table) => ({
  symbolIdx: index('idx_decisions_symbol').on(table.symbol),
  promptIdx: index('idx_decisions_prompt').on(table.promptVersion),
}));
```

---

## Key Queries for Learning

```typescript
// Get prompt performance comparison
const promptStats = await db.execute(sql`
  SELECT * FROM prompt_performance ORDER BY win_rate DESC
`);

// Find patterns in winning trades
const winPatterns = await db.select()
  .from(decisions)
  .where(and(
    eq(decisions.outcomeCorrect, true),
    gt(decisions.actualPnlPercent, 2)
  ))
  .orderBy(desc(decisions.actualPnlPercent));

// Confidence calibration (is 80% confidence actually right 80% of the time?)
const calibration = await db.execute(sql`
  SELECT 
    FLOOR(confidence * 10) / 10 as confidence_bucket,
    COUNT(*) as total,
    AVG(CASE WHEN outcome_correct THEN 1 ELSE 0 END) as actual_accuracy
  FROM decisions
  WHERE traded = true
  GROUP BY confidence_bucket
  ORDER BY confidence_bucket
`);
```

---

## Migration from Python SQLite

```typescript
// scripts/migrate-from-sqlite.ts
import Database from 'better-sqlite3';
import { db } from '@/lib/db';

async function migrate() {
  const sqlite = new Database('./old-trading.db');
  
  // 1. Migrate trades
  const oldTrades = sqlite.prepare('SELECT * FROM trades').all();
  for (const trade of oldTrades) {
    await db.insert(trades).values({
      symbol: trade.symbol,
      side: trade.side.toUpperCase(),
      entryPrice: trade.entry_price,
      // ... map all fields
    });
  }
  
  // 2. Migrate analysis results as decisions
  const oldAnalysis = sqlite.prepare('SELECT * FROM analysis_results').all();
  // ... similar mapping
  
  console.log(`Migrated ${oldTrades.length} trades, ${oldAnalysis.length} decisions`);
}
```


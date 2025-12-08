# SQLite to PostgreSQL Migration Scripts

## Source Databases (Python Bot)

| Database | Path | Tables |
|----------|------|--------|
| **Analysis** | `trading_bot/data/analysis_results.db` | analysis_results, latest_recommendations, trades |
| **Trade States** | `trading_bot/data/trade_states.db` | trade_states, trade_state_history |
| **Backtests** | `prompt_performance/core/backtests.db` | runs, analyses, trades, summaries, opt_* |

---

## Step 1: Export SQLite to JSON

Create `scripts/export-sqlite.ts`:

```typescript
// scripts/export-sqlite.ts
import Database from 'better-sqlite3';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const EXPORT_DIR = './migration-data';
mkdirSync(EXPORT_DIR, { recursive: true });

// Database paths (adjust if needed)
const DBS = {
  analysis: '../trading_bot/data/analysis_results.db',
  tradeStates: '../trading_bot/data/trade_states.db',
  backtests: '../prompt_performance/core/backtests.db',
};

function exportTable(db: Database.Database, table: string, outputFile: string) {
  console.log(`Exporting ${table}...`);
  const rows = db.prepare(`SELECT * FROM ${table}`).all();
  writeFileSync(outputFile, JSON.stringify(rows, null, 2));
  console.log(`  → ${rows.length} rows exported`);
  return rows.length;
}

// Export Analysis DB
console.log('\n📦 Exporting Analysis Database...');
const analysisDb = new Database(DBS.analysis, { readonly: true });
exportTable(analysisDb, 'analysis_results', join(EXPORT_DIR, 'analysis_results.json'));
exportTable(analysisDb, 'latest_recommendations', join(EXPORT_DIR, 'latest_recommendations.json'));
exportTable(analysisDb, 'trades', join(EXPORT_DIR, 'trades.json'));
analysisDb.close();

// Export Trade States DB
console.log('\n📦 Exporting Trade States Database...');
const statesDb = new Database(DBS.tradeStates, { readonly: true });
exportTable(statesDb, 'trade_states', join(EXPORT_DIR, 'trade_states.json'));
exportTable(statesDb, 'trade_state_history', join(EXPORT_DIR, 'trade_state_history.json'));
statesDb.close();

// Export Backtests DB
console.log('\n📦 Exporting Backtests Database...');
const backtestDb = new Database(DBS.backtests, { readonly: true });
exportTable(backtestDb, 'runs', join(EXPORT_DIR, 'backtest_runs.json'));
exportTable(backtestDb, 'analyses', join(EXPORT_DIR, 'backtest_analyses.json'));
exportTable(backtestDb, 'trades', join(EXPORT_DIR, 'backtest_trades.json'));
exportTable(backtestDb, 'summaries', join(EXPORT_DIR, 'backtest_summaries.json'));
backtestDb.close();

console.log('\n✅ Export complete! Files in:', EXPORT_DIR);
```

---

## Step 2: PostgreSQL Schema (Drizzle)

Create `drizzle/schema.ts`:

```typescript
import { pgTable, text, real, boolean, timestamp, jsonb, integer, index, unique } from 'drizzle-orm/pg-core';
import { createId } from '@paralleldrive/cuid2';

// ============ CORE TRADING TABLES ============

export const analysisResults = pgTable('analysis_results', {
  id: text('id').primaryKey(),
  symbol: text('symbol').notNull(),
  timeframe: text('timeframe').notNull(),
  recommendation: text('recommendation').notNull(),
  confidence: real('confidence').notNull(),
  summary: text('summary'),
  evidence: text('evidence'),
  supportLevel: real('support_level'),
  resistanceLevel: real('resistance_level'),
  entryPrice: real('entry_price'),
  stopLoss: real('stop_loss'),
  takeProfit: real('take_profit'),
  direction: text('direction'),
  rr: real('rr'),
  riskFactors: jsonb('risk_factors'),
  analysisData: jsonb('analysis_data'),
  analysisPrompt: text('analysis_prompt'),
  timestamp: timestamp('timestamp'),
  imagePath: text('image_path'),
  marketCondition: text('market_condition'),
  marketDirection: text('market_direction'),
  promptId: text('prompt_id'),
  marketData: jsonb('market_data'),
}, (t) => ({
  symbolTimeframeIdx: index('idx_analysis_symbol_timeframe').on(t.symbol, t.timeframe),
  timestampIdx: index('idx_analysis_timestamp').on(t.timestamp),
}));

export const trades = pgTable('trades', {
  id: text('id').primaryKey(),
  recommendationId: text('recommendation_id').references(() => analysisResults.id),
  symbol: text('symbol').notNull(),
  side: text('side').notNull(),
  quantity: real('quantity').notNull(),
  entryPrice: real('entry_price'),
  takeProfit: real('take_profit'),
  stopLoss: real('stop_loss'),
  orderId: text('order_id').unique(),
  orderLinkId: text('order_link_id'),
  pnl: real('pnl').default(0),
  status: text('status').default('open'),
  state: text('state').default('trade'),
  avgExitPrice: real('avg_exit_price'),
  closedSize: real('closed_size'),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow(),
  placedBy: text('placed_by').default('BOT'),
  alterationDetails: jsonb('alteration_details'),
  promptName: text('prompt_name'),
  timeframe: text('timeframe'),
  confidence: real('confidence'),
  riskRewardRatio: real('risk_reward_ratio'),
  orderType: text('order_type').default('Limit'),
  lastTightenedMilestone: real('last_tightened_milestone'),
}, (t) => ({
  symbolIdx: index('idx_trades_symbol').on(t.symbol),
  statusIdx: index('idx_trades_status').on(t.status),
}));

export const tradeStates = pgTable('trade_states', {
  id: text('id').primaryKey(),
  tradeId: text('trade_id').notNull().unique().references(() => trades.id),
  symbol: text('symbol').notNull(),
  currentState: text('current_state').notNull(),
  previousState: text('previous_state'),
  mainOrderId: text('main_order_id'),
  tpOrderId: text('tp_order_id'),
  slOrderId: text('sl_order_id'),
  orderLinkId: text('order_link_id'),
  entryPrice: real('entry_price'),
  currentTp: real('current_tp'),
  currentSl: real('current_sl'),
  positionSize: real('position_size'),
  unrealizedPnl: real('unrealized_pnl'),
  exitTriggeredBy: text('exit_triggered_by'),
  exitOrderId: text('exit_order_id'),
  exitPrice: real('exit_price'),
  exitReason: text('exit_reason'),
  tighteningCount: integer('tightening_count').default(0),
  lastTightenedAt: timestamp('last_tightened_at'),
  tighteningHistory: jsonb('tightening_history'),
  cancelledBy: text('cancelled_by'),
  cancellationReason: text('cancellation_reason'),
  cancelledAt: timestamp('cancelled_at'),
  slotRiskData: jsonb('slot_risk_data'),
  slotAllocationData: jsonb('slot_allocation_data'),
  stateChangedAt: timestamp('state_changed_at').defaultNow(),
  stateChangedBy: text('state_changed_by').default('SYSTEM'),
  exchangeData: jsonb('exchange_data'),
  errorMessage: text('error_message'),
  retryCount: integer('retry_count').default(0),
  createdAt: timestamp('created_at').defaultNow(),
  updatedAt: timestamp('updated_at').defaultNow(),
}, (t) => ({
  tradeIdIdx: index('idx_trade_states_trade_id').on(t.tradeId),
  symbolIdx: index('idx_trade_states_symbol').on(t.symbol),
}));

export const tradeStateHistory = pgTable('trade_state_history', {
  id: text('id').primaryKey().$defaultFn(() => createId()),
  tradeStateId: text('trade_state_id').notNull().references(() => tradeStates.id),
  fromState: text('from_state'),
  toState: text('to_state').notNull(),
  transitionReason: text('transition_reason'),
  transitionData: jsonb('transition_data'),
  exchangeData: jsonb('exchange_data'),
  transitionAt: timestamp('transition_at').defaultNow(),
});

// ============ BACKTEST TABLES ============

export const backtestRuns = pgTable('backtest_runs', {
  id: integer('id').primaryKey(),
  runSignature: text('run_signature').notNull().unique(),
  startedAt: timestamp('started_at'),
  finishedAt: timestamp('finished_at'),
  durationSec: real('duration_sec'),
  chartsDir: text('charts_dir'),
  selectionStrategy: text('selection_strategy'),
  numImages: integer('num_images'),
  promptsJson: jsonb('prompts_json'),
  symbolsJson: jsonb('symbols_json'),
});

export const backtestAnalyses = pgTable('backtest_analyses', {
  id: integer('id').primaryKey(),
  runId: integer('run_id').notNull().references(() => backtestRuns.id),
  promptName: text('prompt_name').notNull(),
  promptVersion: text('prompt_version'),
  promptHash: text('prompt_hash'),
  symbol: text('symbol').notNull(),
  timeframe: text('timeframe').notNull(),
  timestamp: text('timestamp').notNull(),
  imagePath: text('image_path').notNull(),
  recommendation: text('recommendation'),
  confidence: real('confidence'),
  entryPrice: real('entry_price'),
  stopLoss: real('stop_loss'),
  takeProfit: real('take_profit'),
  rrRatio: real('rr_ratio'),
  status: text('status'),
  rawResponse: text('raw_response'),
  assistantId: text('assistant_id'),
  assistantModel: text('assistant_model'),
  rationale: text('rationale'),
  errorMessage: text('error_message'),
}, (t) => ({
  runPromptUnique: unique().on(t.runId, t.promptName, t.imagePath),
}));
```

---

## Step 3: Import to PostgreSQL

```typescript
// scripts/import-to-postgres.ts
import { db } from '@/lib/db';
import { analysisResults, trades, tradeStates, tradeStateHistory } from '@/drizzle/schema';
import { readFileSync } from 'fs';

const MIGRATION_DIR = './migration-data';

function loadJson<T>(file: string): T[] {
  return JSON.parse(readFileSync(`${MIGRATION_DIR}/${file}`, 'utf-8'));
}

async function migrate() {
  console.log('🚀 Starting PostgreSQL migration...\n');

  // 1. Import analysis results
  const analyses = loadJson<any>('analysis_results.json');
  console.log(`Importing ${analyses.length} analysis results...`);
  for (const row of analyses) {
    await db.insert(analysisResults).values({
      id: row.id,
      symbol: row.symbol,
      timeframe: row.timeframe,
      recommendation: row.recommendation,
      confidence: row.confidence,
      // ... map all fields, parse JSON strings to objects
      riskFactors: row.risk_factors ? JSON.parse(row.risk_factors) : null,
      analysisData: row.analysis_data ? JSON.parse(row.analysis_data) : null,
      timestamp: row.timestamp ? new Date(row.timestamp) : null,
    }).onConflictDoNothing();
  }

  // 2. Import trades
  const tradeRows = loadJson<any>('trades.json');
  console.log(`Importing ${tradeRows.length} trades...`);
  for (const row of tradeRows) {
    await db.insert(trades).values({
      id: row.id,
      symbol: row.symbol,
      side: row.side,
      quantity: row.quantity,
      // ... map all fields
    }).onConflictDoNothing();
  }

  // 3. Import trade states
  const states = loadJson<any>('trade_states.json');
  console.log(`Importing ${states.length} trade states...`);
  // ... similar pattern

  console.log('\n✅ Migration complete!');
}

migrate().catch(console.error);
```

---

## Running the Migration

```bash
# 1. In Python project - export SQLite
cd /path/to/python-bot
npx tsx scripts/export-sqlite.ts

# 2. In Next.js project - create schema
cd /path/to/nextjs-bot
pnpm db:push

# 3. Copy migration-data folder to Next.js project
cp -r migration-data /path/to/nextjs-bot/

# 4. Run import
npx tsx scripts/import-to-postgres.ts

# 5. Verify counts
npx tsx -e "
import { db } from './lib/db';
import { sql } from 'drizzle-orm';
const counts = await db.execute(sql\`
  SELECT 'analysis_results' as t, COUNT(*) as c FROM analysis_results
  UNION ALL SELECT 'trades', COUNT(*) FROM trades
  UNION ALL SELECT 'trade_states', COUNT(*) FROM trade_states
\`);
console.log(counts);
"
```

---

## Post-Migration Checks

```sql
-- Verify data integrity
SELECT 'analysis_results' as table_name, COUNT(*) FROM analysis_results
UNION ALL SELECT 'trades', COUNT(*) FROM trades
UNION ALL SELECT 'trade_states', COUNT(*) FROM trade_states;

-- Check for orphaned records
SELECT COUNT(*) as orphaned_trades
FROM trades t
LEFT JOIN analysis_results a ON t.recommendation_id = a.id
WHERE t.recommendation_id IS NOT NULL AND a.id IS NULL;
```


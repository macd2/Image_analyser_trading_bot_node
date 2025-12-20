# Production Readiness Checklist - Trading Bot A-Z

## 1. CONFIGURATION & SETUP ✅

### Database
- [ ] PostgreSQL/SQLite database initialized with migrations
- [ ] `DATABASE_URL` env var set correctly
- [ ] All tables created: instances, runs, recommendations, trades, etc.
- [ ] Row-level security (RLS) policies configured for Supabase

### Instance Configuration
- [ ] Instance created in database with unique ID
- [ ] Strategy selected (CointegrationSpreadTrader, AiImageAnalyzer, MarketStructure)
- [ ] Strategy config saved to `instances.settings` JSON
- [ ] Timeframe configured (1h, 4h, 1d, etc.)
- [ ] Max concurrent trades set
- [ ] Risk percentage configured
- [ ] Leverage configured

### API Keys & Secrets
- [ ] Bybit API key and secret configured
- [ ] OpenAI API key configured (if using PromptStrategy)
- [ ] TradingView credentials configured (if using PromptStrategy)
- [ ] All secrets in `.env.local` or environment variables

### Trading Parameters
- [ ] Entry price, TP, SL validation rules configured
- [ ] Min/max position size configured
- [ ] Kelly Criterion settings configured
- [ ] Stop loss adjustment settings configured
- [ ] Risk/reward ratio minimum configured

---

## 2. STRATEGY SYSTEM ✅

### Strategy Selection
- [ ] Strategy factory can load selected strategy
- [ ] Strategy config loaded from database
- [ ] Strategy UUID generated deterministically
- [ ] Strategy version tracked

### Strategy Execution
- [ ] `run_analysis_cycle()` executes without errors
- [ ] Stop signal respected (graceful shutdown)
- [ ] Heartbeat callbacks working
- [ ] Error handling and logging comprehensive
- [ ] Output format matches contract (symbol, recommendation, prices, etc.)

### Strategy-Specific
**CointegrationSpreadTrader:**
- [ ] Pair discovery mode working (static or auto_screen)
- [ ] Candle fetching working (API + cache)
- [ ] Cointegration analysis running
- [ ] Z-score calculations correct
- [ ] Entry/exit signals generated

**AiImageAnalyzer (PromptStrategy):**
- [ ] Chart capture from TradingView working
- [ ] Chart cleaning working
- [ ] OpenAI analysis working
- [ ] Prompt function loaded correctly

**MarketStructure (AlexAnalysisModule):**
- [ ] Multi-timeframe analysis working
- [ ] Indicator calculations correct
- [ ] Trend detection working

---

## 3. TRADING CYCLE ✅

### Cycle Flow
- [ ] Cycle starts at timeframe boundary
- [ ] Strategy analysis runs (STEP 0-2)
- [ ] Recommendations collected (STEP 3)
- [ ] Signals ranked by quality (STEP 4)
- [ ] Available slots checked (STEP 5)
- [ ] Best signals selected (STEP 6)
- [ ] Signals executed (STEP 7)

### Signal Validation
- [ ] Entry price > 0
- [ ] Stop loss != entry price
- [ ] Take profit != entry price
- [ ] Risk/reward ratio >= minimum
- [ ] Prices in correct order (long: SL < Entry < TP)

### Execution
- [ ] Position sizer calculates correct size
- [ ] Order executor places orders
- [ ] Trade recorded to database
- [ ] Trade ID generated with instance prefix

---

## 4. POSITION MONITORING ✅

### Real-time Monitoring
- [ ] WebSocket connection to Bybit active
- [ ] Position updates received
- [ ] Stop loss tightening working
- [ ] Exit conditions checked
- [ ] Trades closed correctly

### Logging
- [ ] All trades logged to database
- [ ] All errors logged to database
- [ ] Cycle logs stored
- [ ] Trade monitoring logs stored

---

## 5. ERROR HANDLING & RECOVERY ✅

### Error Logging
- [ ] All exceptions caught and logged
- [ ] Error context stored (cycle_id, symbol, etc.)
- [ ] Error messages clear and actionable
- [ ] Stack traces captured

### Graceful Shutdown
- [ ] Stop signal propagates to strategy
- [ ] Strategy halts gracefully
- [ ] Open positions monitored
- [ ] Database connections closed
- [ ] WebSocket connections closed

### Retry Logic
- [ ] API calls retry on failure
- [ ] Database queries retry on failure
- [ ] Exponential backoff implemented
- [ ] Max retries configured

---

## 6. TESTING CHECKLIST ✅

### Unit Tests
- [ ] Strategy tests passing
- [ ] Database layer tests passing
- [ ] Position sizer tests passing
- [ ] Order executor tests passing

### Integration Tests
- [ ] Full cycle test (analysis → ranking → execution)
- [ ] Multi-instance test
- [ ] Stop signal test
- [ ] Error recovery test

### End-to-End Tests
- [ ] Paper trading cycle complete
- [ ] Live trading cycle complete (testnet)
- [ ] Position monitoring working
- [ ] Trade closure working

---

## 7. MONITORING & LOGGING ✅

### Live Logs
- [ ] Logs display in real-time
- [ ] Log levels correct (INFO, WARNING, ERROR)
- [ ] Batch progress shown (Batch X/Y)
- [ ] No duplicate logs
- [ ] Timestamps accurate

### Metrics
- [ ] Win rate calculated
- [ ] Profit/loss tracked
- [ ] Risk metrics stored
- [ ] Performance stats available

---

## 8. DEPLOYMENT ✅

### Environment
- [ ] Production database configured
- [ ] All env vars set
- [ ] Secrets not in code
- [ ] Logging configured for production

### Monitoring
- [ ] Error alerts configured
- [ ] Performance monitoring active
- [ ] Database backups scheduled
- [ ] Logs persisted

---

## QUICK START COMMANDS

```bash
# 1. Setup database
python python/trading_bot/db/init_trading_db.py

# 2. Create instance
# Use UI or direct database insert

# 3. Run bot
python python/run_bot.py --instance <instance_id> [--live] [--testnet]

# 4. Run tests
pytest python/tests/ -v
pytest python/trading_bot/strategies/tests/ -v
pytest python/trading_bot/engine/tests/ -v
```

---

## TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| Strategy not loading | Check instance config in database |
| No signals generated | Check strategy logs, verify candle data |
| Trades not executing | Check available slots, verify prices |
| Position not closing | Check WebSocket connection, verify exit conditions |
| Database errors | Check DATABASE_URL, verify migrations |
| Stop not working | Check strategy has stop check in loop |



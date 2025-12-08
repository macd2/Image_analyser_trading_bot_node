# Quick Reference Guide: Autotrader Next.js

## 📚 Document Map

| Document | Purpose | Audience | Read Time |
|----------|---------|----------|-----------|
| **README.md** | Overview & navigation | Everyone | 5 min |
| **NEXTJS_CONVERSION_BLUEPRINT.md** | System architecture | Architects, PMs | 20 min |
| **TECHNICAL_DEEP_DIVE.md** | Implementation details | Developers | 30 min |
| **COMPONENT_MAPPING.md** | Python → Next.js mapping | Backend devs | 25 min |
| **API_SPECIFICATION.md** | REST API endpoints | Frontend devs | 20 min |
| **IMPLEMENTATION_ROADMAP.md** | Week-by-week plan | Project leads | 15 min |
| **ARCHITECTURE_DIAGRAMS.md** | Visual flows | Everyone | 10 min |
| **QUICK_REFERENCE.md** | This guide | Everyone | 5 min |

---

## 🎯 Common Questions & Answers

### "How long will this take?"
**Answer**: 13-17 weeks with a 2-4 person team
- Phase 1 (Backend): 4 weeks
- Phase 2 (Real-time): 3 weeks
- Phase 3 (Frontend): 4 weeks
- Phase 4 (Polish): 2 weeks

### "What's the tech stack?"
**Answer**: Modern full-stack JavaScript
- **Frontend**: Next.js 14, React 18, TypeScript, TailwindCSS
- **Backend**: Node.js 20, Express/Next.js API Routes, TypeScript
- **Database**: PostgreSQL 15 (primary), Redis (cache), SQLite (local)
- **Infrastructure**: Docker, Docker Compose, GitHub Actions

### "How many components need to be built?"
**Answer**: 12 core services
1. ChartSourcer (chart capture)
2. ChartAnalyzer (AI analysis)
3. SignalValidator (validation)
4. TradeExecutor (order placement)
5. PositionManager (tracking)
6. RiskManager (sizing)
7. Recommender (ranking)
8. EnhancedPositionMonitor (monitoring)
9. RealTimeTradeTracker (tracking)
10. TelegramBot (notifications)
11. DataAgent (database)
12. Config (settings)

### "What's the trading cycle?"
**Answer**: 6-step process that repeats every cycle boundary
1. Slot Check (are slots available?)
2. Fresh Data Check (do we have analysis?)
3. Chart Capture & Analysis (get new data)
4. Signal Filtering (validate & rank)
5. Position Sizing (calculate quantities)
6. Telegram Confirmation (get approval)
7. Trade Execution (place orders)

### "How do real-time updates work?"
**Answer**: WebSocket + Background Jobs
- WebSocket (Socket.io) for live UI updates
- Bull job queue for background tasks
- Position monitor runs every 2 minutes
- Updates emitted to connected clients

### "What about error handling?"
**Answer**: Multiple layers
- Circuit Breaker pattern for API calls
- Retry logic with exponential backoff
- Comprehensive error logging
- Graceful degradation
- Transaction rollback on failure

### "How is data stored?"
**Answer**: Multi-database approach
- **PostgreSQL**: Primary data (trades, positions, analysis)
- **Redis**: Cache & job queue
- **SQLite**: Local backup & logs

### "What APIs need to be integrated?"
**Answer**: 4 external integrations
1. **Bybit**: Trading (orders, positions, balance)
2. **OpenAI**: Chart analysis (GPT-4 Vision)
3. **Telegram**: Notifications & confirmations
4. **TradingView**: Chart capture (Playwright)

### "How is confidence calculated?"
**Answer**: Weighted formula
```
Confidence = (Setup Quality × 0.4) + 
             (Risk-Reward × 0.25) + 
             (Market Environment × 0.35)
```
Rounded to 3 decimal places before storing.

### "Can multiple trades run simultaneously?"
**Answer**: Yes, with slot management
- Max concurrent trades configured
- Symbol-level position blocking (no duplicate symbols)
- Slot check before each cycle
- Intelligent position sizing

### "What about testing?"
**Answer**: Comprehensive test strategy
- Unit tests (80%+ coverage target)
- Integration tests (API + database)
- E2E tests (full workflows)
- Load testing (performance)

### "How is the app deployed?"
**Answer**: Docker-based deployment
- Docker Compose for local/staging
- GitHub Actions for CI/CD
- Environment variables for config
- Nginx reverse proxy
- PostgreSQL + Redis containers

---

## 🔧 Key Concepts

### Slot Management
- Limits concurrent open trades
- Prevents over-leveraging
- Checked at cycle start
- Configurable per strategy

### Position Sizing
- Risk-based calculation
- Uses stop loss distance
- Respects min/max quantities
- Validates before execution

### Signal Validation
- Confidence threshold check
- Duplicate symbol prevention
- Risk score validation
- Ranking & filtering

### Real-time P&L
- Calculated every 2 minutes
- Unrealized P&L tracking
- Live R/R calculation
- Automatic SL adjustment when profitable

### Mid-cycle Restart
- Checks for existing recommendations
- Reuses analysis if available
- Only captures new charts if needed
- Prevents duplicate analysis

### Confidence Scoring
- 3 components weighted
- Rounded to 3 decimals
- Stored in database
- Used for ranking

---

## 📊 Database Schema Overview

### Core Tables
```
analysis_results
├─ id, symbol, timeframe
├─ recommendation, confidence
├─ entry_price, stop_loss, take_profit
├─ image_path, analysis_data (JSON)
└─ timestamp

trades
├─ id, recommendation_id
├─ symbol, side, quantity
├─ entry_price, take_profit, stop_loss
├─ order_id, pnl, status
├─ prompt_name, created_at, closed_at
└─ (1:N) position_tracking

position_tracking
├─ id, trade_id
├─ symbol, entry_price, current_price
├─ live_rr, unrealized_pnl
└─ checked_at

trading_stats
├─ id, symbol, timeframe
├─ total_trades, winning_trades, losing_trades
├─ total_pnl, win_rate, profit_factor
└─ expected_value

trade_states
├─ id, trade_id, symbol
├─ current_state, main_order_id
├─ tp_order_id, sl_order_id
├─ entry_price, current_tp, current_sl
└─ exit_triggered_by
```

---

## 🚀 Getting Started Checklist

### Before Development
- [ ] Review README.md
- [ ] Read NEXTJS_CONVERSION_BLUEPRINT.md
- [ ] Understand trading cycle (ARCHITECTURE_DIAGRAMS.md)
- [ ] Review tech stack requirements
- [ ] Setup development environment

### Phase 1 Setup
- [ ] Initialize Next.js project
- [ ] Setup PostgreSQL database
- [ ] Create Prisma schema
- [ ] Setup environment variables
- [ ] Create database migrations

### Phase 1 Development
- [ ] Build Bybit API client
- [ ] Build OpenAI integration
- [ ] Build core trading services
- [ ] Build database layer
- [ ] Write unit tests

### Phase 2 Development
- [ ] Setup Bull job queue
- [ ] Setup Socket.io WebSocket
- [ ] Build position monitor
- [ ] Build real-time updates
- [ ] Write integration tests

### Phase 3 Development
- [ ] Build dashboard layout
- [ ] Build live monitor UI
- [ ] Build trade history UI
- [ ] Build analytics UI
- [ ] Write E2E tests

### Phase 4 Finalization
- [ ] Performance optimization
- [ ] Security review
- [ ] Docker setup
- [ ] CI/CD pipeline
- [ ] Production deployment

---

## 💡 Pro Tips

### Development
1. **Start with database schema** - Get it right first
2. **Build API layer early** - Frontend can mock while backend develops
3. **Test as you go** - Don't leave testing for the end
4. **Use TypeScript strictly** - Catch errors early
5. **Document as you code** - Future you will thank you

### Performance
1. **Index database queries** - Especially on symbol, timestamp
2. **Cache analysis results** - Avoid re-analyzing same charts
3. **Use connection pooling** - For database connections
4. **Optimize WebSocket messages** - Send only deltas
5. **Lazy load components** - Especially charts

### Reliability
1. **Implement circuit breakers** - For external APIs
2. **Add retry logic** - With exponential backoff
3. **Log everything** - Especially errors
4. **Monitor uptime** - Setup alerts
5. **Backup data regularly** - Especially trades

### Security
1. **Never expose API keys** - Use environment variables
2. **Validate all inputs** - Frontend and backend
3. **Use HTTPS only** - In production
4. **Implement rate limiting** - Prevent abuse
5. **Rotate credentials regularly** - Especially API keys

---

## 📞 Troubleshooting

### "Database connection fails"
- Check PostgreSQL is running
- Verify DATABASE_URL in .env
- Check credentials are correct
- Run migrations: `npx prisma migrate dev`

### "Bybit API returns 401"
- Verify API key is correct
- Check API key has trading permissions
- Verify timestamp is synchronized
- Check IP whitelist settings

### "OpenAI API rate limited"
- Implement queue system (Bull)
- Add exponential backoff
- Cache analysis results
- Consider upgrading API tier

### "WebSocket not updating"
- Check Socket.io is running
- Verify client is connected
- Check firewall/proxy settings
- Review browser console for errors

### "Trades not executing"
- Check Bybit account has balance
- Verify order parameters (qty, price)
- Check position slots available
- Review error logs for details

---

## 📈 Success Metrics

Track these during development:

| Metric | Target | How to Measure |
|--------|--------|----------------|
| API Response Time | < 200ms | Monitor logs |
| WebSocket Latency | < 100ms | Client-side timing |
| Test Coverage | 80%+ | Jest coverage report |
| Database Query Time | < 50ms | Query logs |
| Uptime | 99.9% | Monitoring service |
| Trade Success Rate | 95%+ | Database stats |
| Error Rate | < 0.1% | Error logs |

---

## 🔗 Quick Links

- **Python Codebase**: `/trading_bot/`
- **Dashboard**: `/UltimateDashboard/`
- **Backtest**: `/prompt_performance/`
- **Config**: `/trading_bot/config/settings.py`
- **Main Orchestrator**: `/run_autotrader.py`

---

## 📝 File Structure (New Next.js App)

```
nextjs-autotrader/
├── app/
│   ├── api/
│   │   ├── trades/
│   │   ├── positions/
│   │   ├── analysis/
│   │   ├── account/
│   │   └── config/
│   ├── dashboard/
│   │   ├── live/
│   │   ├── trades/
│   │   ├── backtest/
│   │   └── prompt-builder/
│   └── layout.tsx
├── lib/
│   ├── services/
│   │   ├── bybit.ts
│   │   ├── chart-analyzer.ts
│   │   ├── trade-executor.ts
│   │   ├── position-manager.ts
│   │   └── ...
│   ├── db/
│   │   ├── prisma.ts
│   │   └── migrations/
│   ├── queue/
│   │   └── index.ts
│   ├── websocket/
│   │   └── server.ts
│   ├── config/
│   │   └── index.ts
│   └── utils/
│       └── logger.ts
├── jobs/
│   ├── trading-cycle.ts
│   └── position-monitor.ts
├── prisma/
│   └── schema.prisma
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── package.json
└── tsconfig.json
```

---

**Version**: 1.0  
**Last Updated**: 2025-11-26  
**Status**: Ready for Development


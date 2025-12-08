# Next.js Conversion Blueprint: Autotrader Bot

## Executive Summary
This document outlines the complete architecture for converting the Python-based autotrader bot into a full-stack Next.js application. The bot is a **crypto trading automation system** that analyzes chart images using AI, generates trade signals, and executes trades on the Bybit exchange.

---

## 1. SYSTEM OVERVIEW

### Current Architecture (Python)
- **Core Bot**: `run_autotrader.py` - Main orchestrator running continuous trading cycles
- **Language**: Python 3.12
- **Databases**: SQLite (3 separate DBs)
- **External APIs**: Bybit (trading), OpenAI (chart analysis), Telegram (notifications), TradingView (chart capture)
- **UI**: Streamlit dashboards (analysis_dashboard, UltimateDashboard)

### Target Architecture (Next.js)
- **Frontend**: Next.js 14+ (React) with TypeScript
- **Backend**: Next.js API Routes + Node.js services
- **Databases**: PostgreSQL (primary) + SQLite (local cache)
- **Real-time**: WebSockets for live updates
- **Deployment**: Docker containers

---

## 2. CORE BUSINESS LOGIC FLOW

### Trading Cycle (6-Step Process)
1. **Fresh Data Check**: Verify chart analysis exists for current cycle boundary
2. **Chart Capture & Analysis**: Capture charts from TradingView, analyze with OpenAI GPT-4 Vision
3. **Signal Filtering**: Apply intelligent filtering, deduplication, and ranking
4. **Position Sizing**: Calculate trade quantities based on risk management
5. **Telegram Confirmation**: Get user approval (auto-approve or manual)
6. **Trade Execution**: Execute on Bybit exchange, track in database

**Background Process**: Position monitor runs every 2 minutes to tighten stop losses on profitable positions.

---

## 3. DATABASE SCHEMA

### Primary Tables (SQLite → PostgreSQL)

#### analysis_results
- Stores chart analysis from OpenAI
- Fields: symbol, timeframe, recommendation, confidence, entry_price, stop_loss, take_profit, image_path, timestamp
- Key: Links recommendations to trades

#### trades
- Tracks all executed trades
- Fields: symbol, side, quantity, entry_price, take_profit, stop_loss, order_id, pnl, status, prompt_name
- Key: Real-time P&L tracking

#### latest_recommendations
- Cache of most recent signals per symbol/timeframe
- Prevents duplicate analysis

#### position_tracking
- Live position monitoring
- Fields: symbol, entry_price, current_price, live_rr, unrealized_pnl

#### trading_stats
- Aggregated metrics per symbol/timeframe
- Fields: win_rate, profit_factor, expected_value, total_trades

#### trade_states
- State machine tracking for order lifecycle
- Fields: trade_id, current_state, main_order_id, tp_order_id, sl_order_id

---

## 4. COMPONENT BREAKDOWN

### Backend Services (Node.js)

#### 4.1 Chart Processing Pipeline
- **ChartSourcer**: Playwright automation for TradingView chart capture
- **ChartAnalyzer**: OpenAI GPT-4 Vision integration for chart analysis
- **Confidence Calculator**: Weighted formula (Setup Quality 40% + Risk-Reward 25% + Market Environment 35%)

#### 4.2 Trading Execution
- **TradeExecutor**: Bybit API integration for order placement
- **PositionManager**: Track open positions and P&L
- **RiskManager**: Position sizing, slot management, risk validation
- **SlotManager**: Manage concurrent trade slots (max_concurrent_trades config)

#### 4.3 Signal Processing
- **SignalValidator**: Validate signals against thresholds
- **Recommender**: Generate trade recommendations from analysis
- **RecommendationService**: Check for mid-cycle recommendations
- **IntelligentOrderReplacement**: Optimize existing orders

#### 4.4 Real-time Monitoring
- **EnhancedPositionMonitor**: Background task for stop loss tightening
- **RealTimeTradeTracker**: Sync trades with exchange in real-time
- **IncrementalSyncManager**: Efficient real-time updates

#### 4.5 Notifications
- **TelegramBot**: Send trade signals for user confirmation
- **TelegramMonitor**: Listen for user responses

### Frontend Components (React/Next.js)

#### 4.6 Dashboard Pages
- **Backtest with Images**: Analyze historical performance with chart visualization
- **Intelligent Prompt Builder**: Iteratively improve trading prompts using AI
- **Live Trading Monitor**: Real-time position tracking and P&L
- **Trade History**: Detailed trade analysis and statistics
- **Prompt Performance**: Compare different prompts and their effectiveness

---

## 5. EXTERNAL INTEGRATIONS

| Service | Purpose | Auth | Rate Limits |
|---------|---------|------|------------|
| **Bybit API** | Trade execution, position data | API Key/Secret | 100 req/s |
| **OpenAI GPT-4 Vision** | Chart analysis | API Key | 500 req/min |
| **Telegram Bot API** | Notifications & confirmations | Bot Token | 30 msg/s |
| **TradingView** | Chart capture via Playwright | Username/Password | N/A |

---

## 6. KEY FEATURES TO IMPLEMENT

### Phase 1: Core Trading Engine
- [ ] Bybit API client (positions, orders, balance)
- [ ] OpenAI integration (chart analysis)
- [ ] Database layer (PostgreSQL)
- [ ] Trading cycle orchestrator
- [ ] Position tracking

### Phase 2: Real-time Features
- [ ] WebSocket connections for live updates
- [ ] Background job queue (Bull/BullMQ)
- [ ] Position monitor service
- [ ] Telegram integration

### Phase 3: Frontend Dashboard
- [ ] Live trading monitor
- [ ] Trade history & analytics
- [ ] Chart visualization with trade markers
- [ ] Real-time P&L updates

### Phase 4: Advanced Features
- [ ] Intelligent Prompt Builder
- [ ] Backtest engine
- [ ] Multi-timeframe support
- [ ] Risk management controls

---

## 7. TECH STACK RECOMMENDATION

```
Frontend:
- Next.js 14+ (App Router)
- React 18+
- TypeScript
- TailwindCSS
- Recharts (charting)
- Socket.io-client (real-time)

Backend:
- Node.js 20+
- Express.js (or Next.js API Routes)
- TypeScript
- Prisma ORM (PostgreSQL)
- Bull/BullMQ (job queue)
- Socket.io (WebSockets)
- Playwright (chart capture)

Infrastructure:
- PostgreSQL 15+
- Redis (caching + job queue)
- Docker + Docker Compose
- GitHub Actions (CI/CD)
```

---

## 8. MIGRATION STRATEGY

### Step 1: Backend Services
1. Create Node.js service layer
2. Implement Bybit API client
3. Migrate database schema to PostgreSQL
4. Implement trading cycle logic

### Step 2: Real-time Features
1. Set up WebSocket server
2. Implement job queue
3. Migrate background services

### Step 3: Frontend
1. Build Next.js dashboard
2. Implement real-time updates
3. Create trading controls

### Step 4: Integration & Testing
1. End-to-end testing
2. Performance optimization
3. Gradual migration from Python

---

## 9. CONFIGURATION MANAGEMENT

Key configs to migrate:
- Trading parameters (max_slots, min_confidence, risk_per_trade)
- API credentials (Bybit, OpenAI, Telegram)
- Timeframes and symbols
- Risk management rules
- Prompt selection

**Recommendation**: Use environment variables + `.env.local` for secrets

---

## 10. MONITORING & LOGGING

- Structured logging (Winston/Pino)
- Error tracking (Sentry)
- Performance monitoring (New Relic/DataDog)
- Database query logging
- API call tracking

---

## 11. SECURITY CONSIDERATIONS

- [ ] API key rotation
- [ ] Rate limiting on endpoints
- [ ] Input validation
- [ ] SQL injection prevention (use Prisma)
- [ ] CORS configuration
- [ ] Authentication for dashboard
- [ ] Audit logging for trades

---

## 12. ESTIMATED EFFORT

| Component | Effort | Priority |
|-----------|--------|----------|
| Backend API Layer | 3-4 weeks | P0 |
| Database Migration | 1-2 weeks | P0 |
| Trading Engine | 2-3 weeks | P0 |
| Real-time Features | 2 weeks | P1 |
| Frontend Dashboard | 3-4 weeks | P1 |
| Testing & Optimization | 2-3 weeks | P1 |
| **Total** | **13-17 weeks** | - |

---

## 13. NEXT STEPS

1. **Validate Architecture**: Review with full-stack dev
2. **Setup Project**: Initialize Next.js + PostgreSQL
3. **Implement Core**: Start with Bybit API client
4. **Iterate**: Build incrementally with testing
5. **Deploy**: Docker + staging environment

---

## 14. APPENDIX: FILE STRUCTURE

```
nextjs-autotrader/
├── app/
│   ├── api/
│   │   ├── trades/
│   │   ├── positions/
│   │   ├── analysis/
│   │   └── orders/
│   ├── dashboard/
│   ├── backtest/
│   └── layout.tsx
├── lib/
│   ├── db/
│   ├── services/
│   │   ├── bybit.ts
│   │   ├── openai.ts
│   │   ├── trading-engine.ts
│   │   └── position-monitor.ts
│   └── utils/
├── components/
│   ├── charts/
│   ├── trades/
│   └── common/
├── prisma/
│   └── schema.prisma
├── jobs/
│   ├── trading-cycle.ts
│   └── position-monitor.ts
└── docker-compose.yml
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-26  
**Status**: Ready for Development


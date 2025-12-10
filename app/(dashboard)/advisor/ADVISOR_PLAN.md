# Advisor System Integration Plan

## Current Status
The Advisor page (`app/(dashboard)/advisor/page.tsx`) is a **UI prototype** that displays **mock data only**. It does not connect to a backend, and all interactions (creating strategies, nodes, toggling switches) are simulated in React state.

## Integration Roadmap

### Phase 1: Backend Foundation
- Create database tables for strategies, nodes, backtest runs, and backtest trades.
- Implement REST API endpoints for CRUD operations on strategies and nodes.
- Integrate with existing SQLite/PostgreSQL database.

### Phase 2: Strategy Evaluation Engine
- Develop `StrategyRunner` Python class that evaluates TA strategies on historical candle data.
- Support basic indicators (SMA, EMA, RSI, MACD) via `pandas_ta` or `TA‑Lib`.
- Define a JSON schema for strategy configuration.

### Phase 3: Backtest Integration
- Extend the existing `ImageBacktester` to support strategy backtesting.
- Add API endpoint `POST /api/advisor/backtest` to trigger backtests.
- Implement progress tracking and result aggregation (reuse prompt‑backtest infrastructure).

### Phase 4: Frontend Enhancements
- Add “Test Strategy” button to each strategy card.
- Create a backtest configuration modal and real‑time progress view.
- Display backtest results with metrics and trade details.

### Phase 5: Deployment & Integration
- Connect advisor nodes to live trading‑bot instances.
- Enable/disable nodes based on backtest performance.
- Add monitoring, alerts, and performance optimizations.

## Success Criteria
1. Users can create a TA strategy via the UI and persist it.
2. Users can run a backtest on historical data with real‑time progress.
3. Backtest results show win rate, profit factor, expectancy, and trade‑by‑trade details.
4. Users can deploy a strategy as an advisor node on a bot instance.
5. The system reuses the existing backtest engine’s infrastructure.

## Next Steps
1. Begin with Phase 1 by drafting the database migration and API stubs.
2. Simultaneously, prototype the `StrategyRunner` in Python with a simple moving‑average crossover strategy.
3. Validate the integration by running a full backtest from the UI.

---

*This document was generated on 2025‑12‑10 as part of the Advisor system design.*
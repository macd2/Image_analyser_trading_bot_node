# Key Components Breakdown - Trading Bot

## Core Purpose
AI-Powered Trading with Continuous Learning

The bot has TWO main purposes:
1. Execute trades based on AI chart analysis
2. Learn and improve the AI prompts over time

---

## 5 Key Components

### 1. Chart Capture (Sourcer)
- Captures TradingView charts as screenshots
- Multiple symbols (BTC, ETH, SOL, etc.)
- Multiple timeframes (1h, 4h, 1d, etc.)
- Stores images with timestamps

**Input**: Symbol + Timeframe
**Output**: Screenshot image file

### 2. Chart Analysis (Analyzer)
- Sends chart image to AI (OpenAI/Anthropic)
- Uses prompt to extract trading signals
- Returns: BUY/SELL/HOLD + Entry/TP/SL + Confidence
- Calculates confidence score from components

**Input**: Chart image + Prompt
**Output**: Trading signal (recommendation, prices, confidence)

### 3. Trade Execution (Trader)
- Validates signals against risk rules
- Places orders on Bybit exchange
- Manages TP/SL orders
- Tracks position lifecycle

**Input**: Trading signal
**Output**: Order placed on exchange

### 4. Position Monitoring
- Tracks open positions
- Monitors P&L in real-time
- Detects TP/SL hits
- Records trade outcomes

**Input**: Open positions
**Output**: Trade results (win/loss/P&L)

### 5. Learning System (Prompt Optimization)
- Stores all analysis results + outcomes
- Backtests prompts against historical data
- Compares prompt versions
- Iteratively improves prompts

**Input**: Historical trades + prompts
**Output**: Improved prompt version

---

## The Trading Cycle (Every Hour)

| Step | Action | Details |
|------|--------|---------|
| 1. Capture | Wait for boundary, capture charts | 12:00, 13:00, etc. |
| 2. Analyze | Send to AI, parse response | BUY/SELL/HOLD + prices |
| 3. Filter | Check confidence, positions, slots | Risk validation |
| 4. Execute | Place order on Bybit | Limit order + TP/SL |
| 5. Monitor | Track P&L, detect hits | Real-time updates |
| 6. Learn | Aggregate outcomes, improve | Background process |

---

## The Learning System

### Data Collected
- Chart images (input)
- AI analysis (output)
- Trade outcomes (win/loss/P&L)
- Confidence scores
- Symbol/timeframe
- Prompt version used

### Backtest Process
1. Take historical chart images
2. Run through prompt
3. Simulate trades based on signals
4. Calculate win rate, P&L, etc.
5. Compare to other prompt versions

### Improvement Cycle
1. Analyze backtest results
2. Identify weak areas (low accuracy symbols)
3. Generate improved prompt
4. Backtest new prompt
5. Compare to current best
6. Deploy winner

---

## Key Metrics

### Trading Metrics
- Total P&L ($)
- Win Rate (%)
- Active Positions (#)
- Avg Confidence Score

### Learning Metrics
- Current Prompt Version
- Iterations Tested
- Images Analyzed
- Improvement vs Baseline

### Per-Symbol Metrics
- Accuracy (%)
- Trades (#)
- Avg Confidence
- Improvement Trend

---

## Data Flow

```
Chart Image → AI Analysis → Trading Signal → Validation → Trade Execution
                                                              ↓
                                                    Position Monitoring
                                                              ↓
                                                      Trade Outcome
                                                              ↓
                                                    Store in Database
                                                              ↓
                                                  Backtest & Analysis
                                                              ↓
                                                    Improve Prompt
                                                              ↓
                                                   Deploy Better Prompt
                                                              ↓
                                                         (Repeat)
```

---

## UI Components Needed

### Dashboard (Main View - All-in-One)
- Trading Stats (P&L, Win Rate, Positions, Confidence)
- Open Positions (Symbol, Side, Entry, P&L, Confidence)
- Learning Status (Prompt Version, Iterations, Progress)
- Key Insights (Correlation, Patterns, Gaps)
- Symbol Performance (Accuracy per symbol)

### Detail Views (Click to expand)
- Positions → Full position management
- Trades → Complete trade history
- Analysis → Confidence breakdown
- Cycle → Execution timeline
- Learning → Deep insights
- Optimization → Iteration details

---

## Summary - What Prototype Should Show

### 1. Current State (Trading)
- Open positions with P&L
- Trading stats (win rate, total P&L)
- Current cycle status

### 2. Learning State (Optimization)
- Current prompt version
- Backtest progress
- Symbol performance

### 3. Insights (Actionable)
- Key findings
- Recommended improvements
- Next steps

### 4. History (Reference)
- Trade history
- Iteration history
- Performance trends


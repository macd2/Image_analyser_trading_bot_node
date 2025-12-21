# Trading Dashboard - REDESIGNED v2.0
## Strategy-Timeframe Performance Focus with Advanced Metrics

---

## 1. DATABASE FINDINGS - STRATEGY & TIMEFRAME DATA ✅

### Available Data:
- **Strategy Types**: `price_based` (PromptStrategy)
- **Strategy Names**: PromptStrategy, MarketStructure, CointegrationSpreadTrader
- **Timeframes**: 1h, 2h, 4h (stored in trades.timeframe)
- **All 586 trades** have strategy_type and strategy_name populated
- **Instances** store strategy config in settings JSON

### Strategy-Timeframe Combinations Found:
```
price_based | PromptStrategy | 1h  → 29 trades
price_based | PromptStrategy | 2h  → 15 trades
price_based | PromptStrategy | 4h  → 5 trades
price_based | PromptStrategy | NULL → 2 trades
```

### Instance Strategy Mapping:
- **FastTrader**: PromptStrategy, 1h timeframe
- **Playboy1**: PromptStrategy, 2h timeframe
- **TestingInstance**: MarketStructure (Cointegration), 2h timeframe
- **SpreadTrader**: CointegrationSpreadTrader, 1h analysis timeframe

---

## 2. REDESIGNED DASHBOARD STRUCTURE

### **SECTION 1: SYSTEM HEALTH & OVERVIEW** (Unchanged)
- KPI Cards: Active Instances, Total P&L, Win Rate, Active Positions
- P&L Trend Chart (7-day)
- Trade Volume Chart
- System Status Indicator

---

### **SECTION 2: STRATEGY-TIMEFRAME PERFORMANCE** (REDESIGNED)
**Purpose**: Analyze performance by strategy-timeframe combination

#### Key Metrics per Strategy-Timeframe:
- **Trade Count**: Number of trades
- **Win Rate**: % of winning trades
- **Total P&L**: Cumulative profit/loss
- **Average P&L**: Mean P&L per trade
- **Sharpe Ratio**: Risk-adjusted returns
- **Expectancy**: Average expected profit per trade
- **Profit Factor**: Gross Profit / Gross Loss
- **Max Drawdown**: Largest peak-to-trough decline
- **Recovery Factor**: Total Profit / Max Drawdown
- **Sortino Ratio**: Downside deviation penalized
- **Average Confidence**: Mean confidence score
- **Best Trade**: Highest P&L
- **Worst Trade**: Lowest P&L

#### Visualizations:
- **Strategy-Timeframe Ranking Table** (sortable by Sharpe, Expectancy, Win Rate, P&L)
  - Color-coded: Green (positive), Red (negative)
  - Top 3 performers highlighted with ⭐ badges
- **Comparison Charts**:
  - Bar Chart: Win Rate by Strategy-Timeframe
  - Bar Chart: Sharpe Ratio by Strategy-Timeframe
  - Bar Chart: Expectancy by Strategy-Timeframe
  - Line Chart: Cumulative P&L per Strategy-Timeframe
- **Radar Chart**: Multi-metric comparison (Win Rate, Sharpe, Expectancy, Profit Factor)
- **Heatmap**: Strategy-Timeframe vs Metrics matrix

---

## 3. ADVANCED TRADING METRICS DEFINITIONS

### Risk-Adjusted Returns:
- **Sharpe Ratio**: (Avg Return - Risk-Free Rate) / Std Dev
- **Sortino Ratio**: Return / Downside Deviation (penalizes only losses)
- **Calmar Ratio**: Annual Return / Max Drawdown
- **Recovery Factor**: Total Profit / Max Drawdown

### Trade Quality:
- **Expectancy**: (Win% × Avg Win) - (Loss% × Avg Loss)
- **Profit Factor**: Gross Profit / Gross Loss
- **Win Rate**: Winning Trades / Total Trades

### Risk Metrics:
- **Max Drawdown**: Largest peak-to-trough decline
- **Drawdown Duration**: Bars/candles to recover from max drawdown
- **Consecutive Losses**: Max losing streak

---

## 4. CORRELATION ANALYSIS SECTION (NEW)

### Analyses:
1. **Strategy-Timeframe vs Confidence Correlation**
   - Scatter plot: Confidence vs Win Rate (colored by strategy-timeframe)
   - Heatmap: Strategy-Timeframe vs Confidence Level vs Win Rate

2. **Strategy-Timeframe vs Trade Outcome Consistency**
   - Box plot: P&L distribution by strategy-timeframe
   - Coefficient of variation (CV) by strategy-timeframe

3. **Position Size vs P&L by Strategy-Timeframe**
   - Scatter plot: Position Size vs P&L (colored by strategy-timeframe)
   - Correlation coefficient per strategy-timeframe

4. **Confidence Level vs Win Rate by Strategy-Timeframe**
   - Heatmap: Strategy-Timeframe rows, Confidence Level columns, Win Rate values

---

## 5. AI INSIGHTS SECTION (NEW - Mock Data)

#### Mock Insight Examples:
```
🏆 TOP PERFORMERS
├─ PromptStrategy 1h: 37.93% win rate, 0.45 Sharpe Ratio
├─ PromptStrategy 2h: 26.67% win rate, 0.32 Sharpe Ratio
└─ PromptStrategy 4h: 20% win rate, 0.18 Sharpe Ratio

⚠️ RISK ALERTS
├─ Max drawdown: -$45.23 (PromptStrategy 1h)
├─ Concentration risk: 33x position size variance
└─ Confidence anomaly: All trades at 0.8 level

💡 RECOMMENDATIONS
├─ "Focus on PromptStrategy 1h (highest Sharpe Ratio)"
├─ "RENDERUSDT & 1000PEPEUSDT: 100% win rate"
├─ "Increase position size for high-confidence trades"
└─ "Consider testing PromptStrategy 4h with more data"
```

---

## 6. API ENDPOINTS NEEDED

```
GET /api/dashboard/overview
GET /api/dashboard/strategy-performance
GET /api/dashboard/symbol-performance
GET /api/dashboard/position-sizing
GET /api/dashboard/correlation-analysis
GET /api/dashboard/ai-insights
GET /api/dashboard/trades?strategy=X&timeframe=Y&days=7
```

---

## 7. KEY INSIGHTS FROM CURRENT DATA

1. **PromptStrategy 1h is best performer** (29 trades)
2. **PromptStrategy 2h is secondary** (15 trades)
3. **PromptStrategy 4h has limited data** (5 trades)
4. **All trades at 0.8 confidence** - test higher thresholds
5. **RENDERUSDT & 1000PEPEUSDT** - 100% win rate
6. **Position sizing variance** - 33x difference
7. **Sharpe Ratio focus** - best metric for strategy comparison


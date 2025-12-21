# Dashboard v2.0 - Chart Recommendations & Elegant Visualizations

## Overview
Using Recharts components already in codebase: LineChart, BarChart, ComposedChart, ScatterChart, RadarChart, PieChart, AreaChart, Heatmap

---

## SECTION 1: SYSTEM HEALTH & OVERVIEW

### 1.1 P&L Trend Chart (7-day)
**Chart Type**: `AreaChart` (elegant gradient fill)
**Why**: Shows cumulative P&L trend with visual area fill for better perception
**Data**: Daily P&L aggregated from trades
**Features**: 
- Gradient fill (green for positive, red for negative)
- Smooth curves
- Tooltip with daily breakdown

### 1.2 Trade Volume Chart
**Chart Type**: `BarChart` (vertical bars)
**Why**: Clear comparison of trade counts per day
**Data**: Trade count per day
**Features**:
- Color-coded by win/loss ratio
- Stacked bars (wins vs losses)
- Hover tooltip with percentages

### 1.3 System Status Indicator
**Chart Type**: `PieChart` (donut style)
**Why**: Quick visual of instance status distribution
**Data**: Active/Inactive/Error instances
**Features**:
- Donut chart (cleaner than pie)
- Color-coded by status
- Center label with total count

---

## SECTION 2: STRATEGY-TIMEFRAME PERFORMANCE

### 2.1 Strategy Ranking Table
**Chart Type**: Interactive table with inline sparklines
**Why**: Sortable comparison of all metrics
**Data**: All strategy-timeframe combinations
**Features**:
- Sortable columns (Sharpe, Expectancy, Win Rate, P&L)
- Color-coded cells (green/red)
- ⭐ badges for top 3
- Inline mini-charts for trends

### 2.2 Win Rate Comparison
**Chart Type**: `BarChart` (horizontal bars)
**Why**: Easy comparison of win rates across strategies
**Data**: Win rate % per strategy-timeframe
**Features**:
- Horizontal layout for long strategy names
- Color gradient (red to green)
- Target line at 50% (breakeven)

### 2.3 Sharpe Ratio Comparison
**Chart Type**: `BarChart` (vertical bars with reference line)
**Why**: Risk-adjusted returns comparison
**Data**: Sharpe ratio per strategy-timeframe
**Features**:
- Reference line at 0 (no excess return)
- Color-coded (negative red, positive green)
- Tooltip with detailed metrics

### 2.4 Expectancy Comparison
**Chart Type**: `BarChart` (vertical bars)
**Why**: Expected profit per trade comparison
**Data**: Expectancy per strategy-timeframe
**Features**:
- Reference line at 0
- Color-coded by value
- Tooltip with calculation breakdown

### 2.5 Cumulative P&L Over Time
**Chart Type**: `ComposedChart` (Line + Area)
**Why**: Shows strategy performance trajectory
**Data**: Cumulative P&L per strategy-timeframe over time
**Features**:
- Multiple lines (one per strategy)
- Area fill for visual distinction
- Legend with strategy names
- Tooltip with date and P&L

### 2.6 Multi-Metric Radar Chart
**Chart Type**: `RadarChart` (5-6 metrics)
**Why**: Elegant comparison of multiple dimensions
**Data**: Normalized metrics (0-100 scale)
**Metrics**:
- Win Rate (%)
- Sharpe Ratio (normalized)
- Expectancy (normalized)
- Profit Factor (normalized)
- Consistency (1 - Coefficient of Variation)
**Features**:
- Multiple radar overlays (top 3 strategies)
- Different colors per strategy
- Smooth curves
- Legend with strategy names

### 2.7 Strategy-Timeframe Heatmap
**Chart Type**: Custom heatmap (table with color cells)
**Why**: Quick visual pattern recognition
**Data**: Rows = strategies, Columns = metrics
**Metrics**: Win Rate, Sharpe, Expectancy, Profit Factor, Max Drawdown
**Features**:
- Color intensity = metric value
- Green (positive) to Red (negative)
- Tooltip with exact values
- Sortable by column

---

## SECTION 3: SYMBOL PERFORMANCE

### 3.1 Win Rate by Symbol
**Chart Type**: `BarChart` (horizontal bars)
**Why**: Easy comparison of symbol performance
**Data**: Win rate % per symbol
**Features**:
- Sorted by win rate (descending)
- Color gradient (red to green)
- Trade count label on bars

### 3.2 Confidence vs Win Rate Scatter
**Chart Type**: `ScatterChart`
**Why**: Identify confidence-outcome relationship
**Data**: X=Confidence, Y=Win Rate, Size=Trade Count
**Features**:
- Bubble size = trade count
- Color = symbol
- Tooltip with symbol, confidence, win rate, count
- Trend line overlay

### 3.3 Symbol P&L Distribution
**Chart Type**: `PieChart` (donut)
**Why**: Visual breakdown of P&L contribution
**Data**: P&L per symbol
**Features**:
- Donut chart (cleaner)
- Color-coded by symbol
- Center label with total P&L
- Tooltip with symbol and amount

---

## SECTION 4: POSITION MANAGEMENT

### 4.1 Position Size Distribution
**Chart Type**: `BarChart` (histogram style)
**Why**: Understand position sizing patterns
**Data**: Position size buckets (e.g., $0-100, $100-200, etc.)
**Features**:
- Frequency on Y-axis
- Position size ranges on X-axis
- Average line overlay
- Tooltip with count and percentage

### 4.2 Risk Percentage Distribution
**Chart Type**: `AreaChart` (stacked)
**Why**: Show risk distribution over time
**Data**: Risk % per trade over time
**Features**:
- Area fill for visual impact
- Color-coded by risk level
- Tooltip with date and risk %

### 4.3 Position Size vs P&L Scatter
**Chart Type**: `ScatterChart`
**Why**: Identify optimal position sizing
**Data**: X=Position Size, Y=P&L, Color=Strategy
**Features**:
- Bubble size = confidence
- Color = strategy-timeframe
- Quadrant lines (breakeven)
- Tooltip with all details

### 4.4 Position Size Quartiles
**Chart Type**: `ComposedChart` (Box plot style)
**Why**: Statistical distribution view
**Data**: Min, Q1, Median, Q3, Max per strategy
**Features**:
- Box plot visualization
- Whiskers for min/max
- Median line
- Outlier dots

---

## SECTION 5: CORRELATION ANALYSIS

### 5.1 Confidence vs Win Rate Heatmap
**Chart Type**: Custom heatmap (2D grid)
**Why**: Identify confidence-outcome patterns
**Data**: Rows=Confidence Levels, Columns=Strategies, Values=Win Rate
**Features**:
- Color intensity = win rate
- Green (high) to Red (low)
- Tooltip with exact values
- Identifies optimal confidence thresholds

### 5.2 P&L Distribution by Strategy
**Chart Type**: `ComposedChart` (Box plot + scatter)
**Why**: Show consistency and outliers
**Data**: P&L per trade by strategy
**Features**:
- Box plot for distribution
- Scatter dots for individual trades
- Median line
- Outlier highlighting

### 5.3 Position Size vs P&L Correlation
**Chart Type**: `ScatterChart` with trend line
**Why**: Identify sizing-outcome relationship
**Data**: X=Position Size, Y=P&L, Color=Strategy
**Features**:
- Trend line per strategy
- Color-coded by strategy
- Bubble size = confidence
- Correlation coefficient in tooltip

### 5.4 Strategy Consistency Radar
**Chart Type**: `RadarChart`
**Why**: Compare consistency metrics
**Data**: Normalized consistency metrics
**Metrics**:
- Coefficient of Variation (lower = better)
- Win/Loss Ratio
- Consecutive Wins
- Consecutive Losses
- Drawdown Recovery Speed
**Features**:
- Multiple overlays (top strategies)
- Different colors
- Legend with strategy names

---

## SECTION 6: AI INSIGHTS

### 6.1 Top Performers Card
**Chart Type**: Ranked list with mini-sparklines
**Why**: Quick visual of best strategies
**Data**: Top 3 strategies with trend
**Features**:
- Sparkline showing P&L trend
- Ranking badges (🥇🥈🥉)
- Key metrics inline
- Click to drill down

### 6.2 Risk Alerts Dashboard
**Chart Type**: `AreaChart` (drawdown visualization)
**Why**: Visualize risk metrics
**Data**: Cumulative drawdown over time
**Features**:
- Red area fill for drawdown
- Reference line at max drawdown
- Tooltip with recovery time
- Highlight current drawdown

### 6.3 Correlation Matrix Heatmap
**Chart Type**: Custom heatmap (NxN grid)
**Why**: Identify metric relationships
**Data**: Correlation coefficients between metrics
**Features**:
- Color intensity = correlation strength
- Blue (positive) to Red (negative)
- Diagonal = 1.0 (perfect correlation)
- Tooltip with exact correlation value

### 6.4 Opportunity Identification
**Chart Type**: `ScatterChart` (bubble chart)
**Why**: Identify underperforming opportunities
**Data**: X=Trade Count, Y=Win Rate, Size=Potential
**Features**:
- Bubble size = potential improvement
- Color = strategy
- Quadrant analysis (high count + low win rate = opportunity)
- Tooltip with recommendation

---

## IMPLEMENTATION PRIORITY

### Phase 1 (Core - Must Have)
1. Strategy Ranking Table (2.1)
2. Win Rate Comparison (2.2)
3. Cumulative P&L Chart (2.5)
4. P&L Trend Area Chart (1.1)
5. Trade Volume Bar Chart (1.2)

### Phase 2 (Advanced - Should Have)
1. Multi-Metric Radar Chart (2.6)
2. Confidence vs Win Rate Scatter (3.2)
3. Position Size vs P&L Scatter (4.3)
4. Confidence vs Win Rate Heatmap (5.1)
5. Sharpe Ratio Comparison (2.3)

### Phase 3 (Polish - Nice to Have)
1. Strategy-Timeframe Heatmap (2.7)
2. Correlation Matrix Heatmap (6.3)
3. Risk Alerts Drawdown Chart (6.2)
4. Opportunity Identification Bubble (6.4)
5. Position Size Quartiles Box Plot (4.4)

---

## RECHARTS COMPONENTS USED

```typescript
// Already in codebase:
import {
  LineChart, Line,
  BarChart, Bar,
  AreaChart, Area,
  ComposedChart,
  ScatterChart, Scatter,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  PieChart, Pie, Cell,
  XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
  ReferenceLine, ReferenceDot,
} from 'recharts'
```

All components are already available in the project!


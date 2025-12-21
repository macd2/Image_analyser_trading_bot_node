# Dashboard Chart Implementation Guide

## Quick Reference - Chart Types by Section

### SECTION 1: SYSTEM HEALTH (3 charts)
```
1. AreaChart - P&L Trend (gradient fill, smooth curves)
2. BarChart - Trade Volume (stacked wins/losses)
3. PieChart - Instance Status (donut style)
```

### SECTION 2: STRATEGY PERFORMANCE (6 visualizations)
```
1. Interactive Table - Strategy Ranking (sortable, inline sparklines)
2. BarChart Horizontal - Win Rate (color gradient, target line)
3. BarChart Vertical - Sharpe Ratio (reference line at 0)
4. ComposedChart - Cumulative P&L (line + area, multiple strategies)
5. RadarChart - Multi-Metric (5-6 normalized dimensions)
6. Custom Heatmap - Strategy vs Metrics (color intensity)
```

### SECTION 3: SYMBOL PERFORMANCE (3 charts)
```
1. BarChart Horizontal - Win Rate by Symbol (sorted, color gradient)
2. ScatterChart - Confidence vs Win Rate (bubble size = trade count)
3. PieChart - P&L Distribution (donut, color per symbol)
```

### SECTION 4: POSITION MANAGEMENT (4 charts)
```
1. BarChart Histogram - Position Size Distribution (with average line)
2. AreaChart Stacked - Risk % Distribution (over time)
3. ScatterChart - Position Size vs P&L (color = strategy, size = confidence)
4. ComposedChart - Box Plot Style (quartiles visualization)
```

### SECTION 5: CORRELATION ANALYSIS (4 visualizations)
```
1. Custom Heatmap - Confidence vs Win Rate (2D grid)
2. ComposedChart - P&L Distribution (box plot + scatter)
3. ScatterChart - Position Size vs P&L (with trend line)
4. RadarChart - Strategy Consistency (5 metrics)
```

### SECTION 6: AI INSIGHTS (4 visualizations)
```
1. Ranked List - Top Performers (mini-sparklines, 🥇🥈🥉 badges)
2. AreaChart - Risk Alerts (red fill, drawdown visualization)
3. Custom Heatmap - Correlation Matrix (NxN grid, blue-red scale)
4. ScatterChart Bubble - Opportunity Identification (quadrant analysis)
```

---

## Implementation Patterns

### Pattern 1: AreaChart with Gradient
```typescript
<AreaChart data={data}>
  <defs>
    <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
      <stop offset="5%" stopColor="#10b981" stopOpacity={0.8}/>
      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
    </linearGradient>
  </defs>
  <Area type="monotone" dataKey="pnl" stroke="#10b981" 
        fill="url(#colorPnl)" strokeWidth={2} />
</AreaChart>
```

### Pattern 2: BarChart with Reference Line
```typescript
<BarChart data={data}>
  <Bar dataKey="sharpeRatio" fill="#3b82f6" />
  <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="5 5" />
  <ReferenceLine y={1} stroke="#10b981" strokeDasharray="5 5" label="Good" />
</BarChart>
```

### Pattern 3: ComposedChart (Line + Area)
```typescript
<ComposedChart data={data}>
  <Area type="monotone" dataKey="pnl" fill="#3b82f6" stroke="none" />
  <Line type="monotone" dataKey="pnl" stroke="#3b82f6" strokeWidth={2} />
</ComposedChart>
```

### Pattern 4: RadarChart Multi-Metric
```typescript
<RadarChart data={normalizedData}>
  <PolarGrid stroke="#334155" />
  <PolarAngleAxis dataKey="metric" />
  <PolarRadiusAxis angle={90} domain={[0, 100]} />
  <Radar name="Strategy 1" dataKey="value1" stroke="#3b82f6" fill="#3b82f6" />
  <Radar name="Strategy 2" dataKey="value2" stroke="#10b981" fill="#10b981" />
</RadarChart>
```

### Pattern 5: ScatterChart with Bubble Size
```typescript
<ScatterChart data={data}>
  <Scatter name="Trades" dataKey="winRate" fill="#3b82f6">
    {data.map((entry, index) => (
      <Cell key={`cell-${index}`} fill={getColorByStrategy(entry.strategy)} />
    ))}
  </Scatter>
</ScatterChart>
```

### Pattern 6: Custom Heatmap
```typescript
// Use table with colored cells
<div className="grid grid-cols-6 gap-1">
  {data.map((row) => (
    <div key={row.id} className="flex gap-1">
      {row.metrics.map((metric) => (
        <div
          key={metric.id}
          className="w-12 h-12 rounded"
          style={{
            backgroundColor: getHeatmapColor(metric.value),
          }}
          title={`${metric.name}: ${metric.value}`}
        />
      ))}
    </div>
  ))}
</div>
```

---

## Color Coding Strategy

### Positive/Negative Values
- **Green (#10b981)**: Positive values, wins, good metrics
- **Red (#ef4444)**: Negative values, losses, poor metrics
- **Blue (#3b82f6)**: Neutral, primary data
- **Amber (#f59e0b)**: Warnings, attention needed

### Heatmap Colors
- **Green (#10b981)**: High values (good)
- **Yellow (#fbbf24)**: Medium values
- **Red (#ef4444)**: Low values (bad)

### Strategy Colors (Consistent)
- **PromptStrategy 1h**: #3b82f6 (Blue)
- **PromptStrategy 2h**: #10b981 (Green)
- **PromptStrategy 4h**: #f59e0b (Amber)
- **MarketStructure**: #8b5cf6 (Purple)
- **CointegrationSpreadTrader**: #ec4899 (Pink)

---

## Data Transformation Examples

### Normalize Metrics for Radar (0-100 scale)
```typescript
const normalizeMetric = (value, min, max) => {
  return ((value - min) / (max - min)) * 100
}

const radarData = strategies.map(s => ({
  name: s.name,
  winRate: s.winRate * 100,
  sharpeRatio: normalizeMetric(s.sharpeRatio, -2, 2) * 100,
  expectancy: normalizeMetric(s.expectancy, -10, 10) * 100,
  profitFactor: normalizeMetric(s.profitFactor, 0, 3) * 100,
  consistency: (1 - s.coefficientOfVariation) * 100,
}))
```

### Create Heatmap Data
```typescript
const heatmapData = strategies.map(strategy => ({
  strategy: strategy.name,
  metrics: [
    { name: 'Win Rate', value: strategy.winRate },
    { name: 'Sharpe', value: strategy.sharpeRatio },
    { name: 'Expectancy', value: strategy.expectancy },
    { name: 'Profit Factor', value: strategy.profitFactor },
    { name: 'Max Drawdown', value: -strategy.maxDrawdown },
  ]
}))
```

### Create Box Plot Data
```typescript
const boxPlotData = strategies.map(s => ({
  strategy: s.name,
  min: Math.min(...s.trades.map(t => t.pnl)),
  q1: percentile(s.trades.map(t => t.pnl), 25),
  median: percentile(s.trades.map(t => t.pnl), 50),
  q3: percentile(s.trades.map(t => t.pnl), 75),
  max: Math.max(...s.trades.map(t => t.pnl)),
}))
```

---

## Responsive Design

All charts use `ResponsiveContainer` with `width="100%" height={300}`:
```typescript
<ResponsiveContainer width="100%" height={300}>
  <BarChart data={data}>
    {/* chart content */}
  </BarChart>
</ResponsiveContainer>
```

---

## Performance Optimization

1. **Memoize chart data**: Use `useMemo` to prevent recalculations
2. **Lazy load charts**: Load charts below fold on scroll
3. **Limit data points**: Show last 100 trades, aggregate older data
4. **Cache calculations**: Store metric calculations in database
5. **Debounce filters**: Debounce filter changes before re-rendering

---

## Testing Charts

1. **Visual regression**: Screenshot tests for chart appearance
2. **Data accuracy**: Verify calculations match expected values
3. **Responsiveness**: Test on mobile, tablet, desktop
4. **Performance**: Monitor render time with large datasets
5. **Accessibility**: Ensure tooltips and legends are readable


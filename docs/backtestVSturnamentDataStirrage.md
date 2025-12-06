

Now let me check the tournament's `_simulate_trade` to compare:

Now I have a complete picture. Here's the comparison:

---

## Backtest with Images vs Tournament - Core Differences

### ✅ SAME: Core Components
| Component | Backtest | Tournament |
|-----------|----------|------------|
| AI Analysis | `prompt_analyzer.analyze_image()` | `backtester.prompt_analyzer.analyze_image()` |
| Trade Simulator | `trade_simulator.simulate_trade()` | `backtester.trade_simulator.simulate_trade()` |
| Candle Fetcher | `candle_fetcher.get_candles_for_simulation()` | `backtester.candle_fetcher.get_candles_for_simulation()` |

**The actual analysis and simulation logic is IDENTICAL** - tournament just wraps the same components.

---

### ❌ DIFFERENT: Data Captured/Stored

| Field | Backtest (`trades` table) | Tournament (`phase_details_json`) |
|-------|---------------------------|-----------------------------------|
| `prompt_version` | ✅ | ❌ (not captured) |
| `rr_ratio` | ✅ | ❌ |
| `achieved_rr` | ✅ | ❌ |
| `exit_candle_index` | ✅ | ✅ |
| `entry_candle_index` | ✅ | ✅ |
| `mfe_price` | ✅ | ❌ |
| `mae_price` | ✅ | ❌ |
| `mfe_percent` | ✅ | ❌ |
| `mae_percent` | ✅ | ❌ |
| `mfe_r` | ✅ | ❌ |
| `mae_r` | ✅ | ❌ |
| `realized_pnl_price` | ✅ | ❌ |
| `realized_pnl_percent` | ✅ | ✅ |
| `image_path` | ✅ | ✅ |
| `metadata` (extended) | ❌ | ✅ (we just added this) |

---

### ❌ DIFFERENT: Storage Location

| System | Where | Used By |
|--------|-------|---------|
| Backtest | `trades` table (normalized) | Learning System |
| Tournament | `tournament_runs.phase_details_json` (JSON blob) | Trade Verification Modal |

---

### ❌ DIFFERENT: Caching

| Feature | Backtest | Tournament |
|---------|----------|------------|
| Analysis caching | ✅ `has_cached_analysis()` - skips re-analysis | ❌ Always re-analyzes |
| Verification & repair | ✅ `_verify_persistence_and_repair()` | ❌ None |

---

## Summary

**Results are identical** for the same image+prompt+candles because they use the same simulator.

**But tournament captures LESS data** per trade and stores it differently (JSON blob vs normalized table).

Would you like me to:
1. **Align tournament trade data** to capture all the same fields as backtest?
2. **Have tournament also write to `trades` table** so Learning System sees it?
3. **Both** of the above?

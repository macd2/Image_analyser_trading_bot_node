//@version=5
indicator("✅ Cointegration Z-Score + Size × | Actionable Rules", overlay=false, shorttitle="Coint + Size")

// —————— HOW TO TRADE THIS SYSTEM ——————
// ▶ STEP 1: WAIT FOR BLUE BACKGROUND (Hurst < 0.5) — only trade when mean-reversion is confirmed.
// ▶ STEP 2: WATCH Z-SCORE (orange line):
//      • When z ≤ -2.0 → prepare LONG SPREAD (long Asset2, short β × Asset1)
//      • When z ≥ +2.0 → prepare SHORT SPREAD (short Asset2, long β × Asset1)
// ▶ STEP 3: ENTER ONLY ON FIRST GREEN ▲ OR RED ▼ — avoids overtrading.
//      • Label shows size multiplier (e.g., "×1.72").
//      • Multiply your base risk (e.g., 1% equity) by this number → actual risk.
// ▶ STEP 4: EXIT AUTOMATICALLY when |z| ≤ 0.5 (z-score crosses gray line) — take profit.
// ▶ STEP 5: IF RED BACKGROUND APPEARS (Hurst ≥ 0.5) → DO NOT ENTER — regime broken.

// —————— INPUTS ——————
symbol1 = input.symbol("BINANCE:RNDRUSDT", "Asset 1 (e.g., RNDR)")
symbol2 = input.symbol("BINANCE:AKTUSDT", "Asset 2 (e.g., AKT)")
lookback = input.int(120, "Lookback Period (days)", minval=30)
zEntry = input.float(2.0, "Z Entry Threshold", minval=1.5, tooltip="Lower = more signals, higher = higher confidence")
zExit  = input.float(0.5, "Z Exit Threshold", minval=0.0, tooltip="Closer to 0 = tighter profit-taking")
baseMultiplier = input.float(1.0, "Base Risk Multiplier", minval=0.1, tooltip="1.0 = use raw size; 0.5 = halve all sizes")
useSoftVol = input.bool(false, "☑ Use Soft Vol Scaling (for choppy markets)", 
   tooltip="ON: smoother sizing (0.5x–2.5x). OFF: aggressive (0.3x–3.0x) — default for stable pairs.")

// —————— DATA & STATISTICS ——————
p1 = request.security(symbol1, "D", close)
p2 = request.security(symbol2, "D", close)

// Compute hedge ratio β: how much of Asset1 offsets 1 unit of Asset2
avgX = ta.sma(p1, lookback)
avgY = ta.sma(p2, lookback)
covXY = ta.sma((p1 - avgX) * (p2 - avgY), lookback)
varX = ta.sma((p1 - avgX) * (p1 - avgX), lookback)
beta = varX != 0 ? covXY / varX : 1.0

// Spread = residual (should be mean-reverting if cointegrated)
spread = p2 - beta * p1
spreadMean = ta.sma(spread, lookback)
spreadStdev = ta.stdev(spread, lookback)
zScore = spreadStdev != 0 ? (spread - spreadMean) / spreadStdev : 0

// Hurst exponent: <0.5 = mean-reverting (safe), ≥0.5 = trending (avoid)
hurst = (ta.stdev(spread, lookback) > 0 and ta.stdev(spread - spread[1], lookback) > 0) ?
   0.5 + math.log(ta.stdev(spread - spread[1], lookback) / ta.stdev(spread, lookback)) / math.log(2) : 0.5
isMeanReverting = hurst < 0.5

// —————— DYNAMIC POSITION SIZING ——————
// Higher |z| beyond entry = stronger edge → larger size.
// Lower spread volatility = more reliable edge → larger size.
spreadMeanAbs = math.abs(spreadMean) + 0.001
edgeAdjust = 1.0 + math.max(0, math.abs(zScore) - zEntry) * 0.5
volRatio = spreadStdev / spreadMeanAbs
volAdjust = useSoftVol ? math.min(1.0 / math.sqrt(volRatio), 1.8) : math.min(1.0 / volRatio, 2.0)
sizeMultiplier = baseMultiplier * edgeAdjust * volAdjust
// Clamp to prevent extremes
sizeMultiplier := useSoftVol ? math.max(0.5, math.min(sizeMultiplier, 2.5)) : math.max(0.3, math.min(sizeMultiplier, 3.0))

// —————— TRADE STATE MANAGEMENT (ONE TRADE PER CYCLE) ——————
var bool inLong  = false
var bool inShort = false

longCondition  = zScore <= -zEntry and isMeanReverting
shortCondition = zScore >= zEntry and isMeanReverting
exitCondition  = math.abs(zScore) <= zExit

// Enter only once per cycle
if longCondition and not inLong and not inShort
    inLong := true
if shortCondition and not inShort and not inLong
    inShort := true
// Exit and reset
if exitCondition
    inLong := false
    inShort := false

// —————— VISUAL SIGNALS ——————
// ▲ GREEN TRIANGLE + LABEL BELOW BAR → ENTER LONG SPREAD
//    Action: Buy Asset2, Sell (β × Asset1) — e.g., Buy AKT, Sell 0.82 × RNDR
var label longLabel = na
if (inLong and inLong[1] == false)
    label.delete(longLabel)
    longLabel := label.new(
      x=bar_index, 
      y=low * 0.995, 
      text="×" + str.tostring(sizeMultiplier, "#.##"), 
      color=color.green, 
      textcolor=color.white,
      style=label.style_label_up,
      size=size.normal)

// ▼ RED TRIANGLE + LABEL ABOVE BAR → ENTER SHORT SPREAD
//    Action: Sell Asset2, Buy (β × Asset1) — e.g., Sell AKT, Buy 0.82 × RNDR
var label shortLabel = na
if (inShort and inShort[1] == false)
    label.delete(shortLabel)
    shortLabel := label.new(
      x=bar_index, 
      y=high * 1.005, 
      text="×" + str.tostring(sizeMultiplier, "#.##"), 
      color=color.red, 
      textcolor=color.white,
      style=label.style_label_down,
      size=size.normal)

// —————— PLOTS ——————
plot(zScore, "Z-Score", color=color.orange, linewidth=2)
hline(zEntry, "Short Entry", color=color.red, linestyle=hline.style_dashed)
hline(-zEntry, "Long Entry", color=color.green, linestyle=hline.style_dashed)
hline(0, "Exit (Take Profit)", color=color.gray, linestyle=hline.style_dotted)
// BLUE = SAFE TO TRADE | RED = DO NOT TRADE
bgcolor(isMeanReverting ? color.new(color.blue, 95) : color.new(color.red, 95))

// For debugging: current size in Data Window
plot(sizeMultiplier, "Size ×", display=display.data_window, color=color.blue)
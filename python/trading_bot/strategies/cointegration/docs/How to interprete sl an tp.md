Exactly! You've identified a key difference between **cointegration pairs trading** and **classic directional trading**.

**Classic Trade (e.g., BUY LINKUSDT):**
```
Entry Price: 14.16
SL: 13.90 (fixed price)
TP: 14.50 (fixed price)

On each tick:
  if price <= 13.90: STOP OUT
  if price >= 14.50: TAKE PROFIT
```
The levels are **fixed at entry time** and don't change.

---

**Cointegration Pairs Trade (SHORT spread):**
```
Entry Spread: 6.118384
SL Spread: 6.333760
TP1 Spread: 5.579943
TP2 Spread: 5.759423

On each tick:
  current_spread = price_y - beta * price_x
  
  if current_spread >= 6.333760: STOP OUT
  if current_spread <= 5.579943: TAKE PROFIT 1
  if current_spread <= 5.759423: TAKE PROFIT 2
```

The levels are **also fixed at entry time**, but they're in **spread space**, not asset price space.

---

**The key difference:**
- **Classic trade**: You set SL/TP in asset prices (14.16, 13.90, 14.50)
- **Pairs trade**: You set SL/TP in spread values (6.118, 6.334, 5.580)

But **both are fixed at entry time** - they don't change as prices move.

So yes, you **CAN set SL/TP at signal time** for pairs trading, just like classic trading. The execution engine just needs to monitor the spread instead of the asset price.


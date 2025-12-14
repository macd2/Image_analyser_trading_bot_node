# Bybit Wallet Fields Explained

## Account-Level Fields (UNIFIED Account)

These fields are at the account level and represent totals across ALL coins in your account.

### `totalEquity`
- **What it is**: Total equity value of your account in USD
- **Formula**: Sum of all coin equities converted to USD
- **Includes**: Wallet balance + unrealized P&L from all positions
- **Use case**: Overall account health indicator
- **Example**: $4604.41 (total across all coins)

### `totalAvailableBalance`
- **What it is**: Total balance available to trade with (after accounting for margin requirements)
- **Formula**: Total wallet balance - Initial Margin (IM) for open positions
- **Includes**: Cash available for new trades
- **Use case**: How much you can use to open new positions
- **Example**: $4604.36 (available for trading)
- **Note**: For UNIFIED accounts, `availableToWithdraw` is deprecated and always returns empty

### `totalPerpUPL`
- **What it is**: Total Unrealized Profit/Loss from perpetual futures positions
- **Formula**: Sum of unrealized P&L from all open perpetual positions
- **Includes**: Only perpetual contracts, not spot positions
- **Use case**: See how much you're winning/losing on open positions
- **Example**: $0 (no open positions) or $+500 (winning) or $-200 (losing)

---

## Coin-Level Fields (USDT Coin)

These fields are specific to a single coin (e.g., USDT).

### `walletBalance`
- **What it is**: Your actual USDT balance in the wallet
- **Formula**: Just the USDT you have
- **Includes**: Only USDT, not other coins
- **Use case**: How much USDT you actually own
- **Example**: $4592.06 (just USDT)

### `equity` (coin-level)
- **What it is**: Equity for this specific coin
- **Formula**: Wallet balance + unrealized P&L for this coin
- **Includes**: Only this coin's positions
- **Use case**: Health of this specific coin
- **Example**: $4592.06 (USDT equity)

---

## Key Differences

| Field | Level | Scope | Includes |
|-------|-------|-------|----------|
| `totalEquity` | Account | All coins | All coin equities in USD |
| `totalAvailableBalance` | Account | All coins | Available for trading |
| `totalPerpUPL` | Account | Perpetuals only | Unrealized P&L from futures |
| `walletBalance` | Coin | USDT only | Just USDT balance |
| `equity` | Coin | USDT only | USDT + unrealized P&L |

---

## In Your Dashboard

The Account Summary card now displays:
- **Balance**: `walletBalance` (your actual USDT)
- **Equity**: `totalEquity` (total account value)
- **Available**: `totalAvailableBalance` (can use for new trades)
- **Unrealised PnL**: `totalPerpUPL` (profit/loss on open positions)
- **Slots**: Used/Max concurrent trades

All values update in real-time from Bybit WebSocket or fallback to API if WebSocket unavailable.


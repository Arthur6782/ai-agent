# Crypto Trading Bot — SMC DEX Strategy

A modular, professional-grade DEX trading bot built with **Node.js**, implementing **Smart Money Concepts (SMC)** for precise sniper entries on Solana and EVM-compatible chains.

---

## Architecture

```
crypto-trading-bot/
├── src/
│   ├── data/
│   │   ├── dexscreener.js     # Dexscreener API client (price, volume, liquidity)
│   │   ├── jupiter.js         # Jupiter aggregator client (Solana prices & quotes)
│   │   └── marketData.js      # Unified market data fetcher + candle cache
│   │
│   ├── strategy/
│   │   ├── zones.js           # Supply & Demand zone detection
│   │   ├── smc.js             # BOS, CHoCH, Liquidity Sweeps, Order Blocks
│   │   └── signals.js         # Entry signal generation (sniper logic)
│   │
│   ├── execution/
│   │   ├── paperTrade.js      # Paper trading simulator (safe mode)
│   │   ├── realTrade.js       # Live trading stub (wallet integration scaffold)
│   │   └── orderManager.js    # Trade lifecycle: open, monitor, close
│   │
│   ├── risk/
│   │   ├── riskManager.js     # Position sizing, SL/TP, daily loss limit
│   │   └── cooldown.js        # Anti-overtrading cooldown system
│   │
│   ├── utils/
│   │   ├── config.js          # Config loader (JSON + env overrides)
│   │   ├── logger.js          # Winston logger (console + file)
│   │   ├── journal.js         # Trade journal (JSON + CSV)
│   │   └── validator.js       # Token safety checks (liquidity, volume, rugs)
│   │
│   ├── cli/
│   │   └── interface.js       # CLI commands (start, status, journal, config)
│   │
│   └── bot.js                 # Main orchestrator
│
├── config/
│   └── default.json           # Default bot configuration
├── journal/                   # Trade records (auto-created)
├── logs/                      # Log files (auto-created)
├── .env.example               # Environment variable template
└── package.json
```

---

## Features

### Market Data
- Real-time prices from **Dexscreener** (Solana, Ethereum, BSC, and more)
- Jupiter price API fallback for Solana tokens
- Tracks price, volume (5m/1h/24h), liquidity, FDV
- Pseudo-OHLCV candle cache built from polling ticks

### SMC Strategy
| Concept | What it detects |
|---|---|
| **Break of Structure (BOS)** | Trend continuation when price closes beyond a swing high/low |
| **Change of Character (CHoCH)** | First opposing BOS — signals potential reversal |
| **Supply & Demand Zones** | High-probability reversal areas from prior institutional moves |
| **Liquidity Sweeps** | Stop hunts where price wicks through a level then reverses |
| **Order Blocks** | Last opposing candle before a BOS — institutional footprint |

Entry fires only when **multiple confirmations** align (configurable threshold).

### Risk Management
- **Fixed fractional position sizing**: risk exactly X% per trade
- **Stop Loss** placed below demand zone / above supply zone
- **Take Profit** at minimum 2:1 R:R (or nearest opposing zone)
- **Daily loss limit**: stops trading if daily drawdown exceeds threshold
- **Consecutive loss protection**: halts after N losses in a row
- **Cooldown system**: per-pair and global cooldown after losses

### Execution
- **Paper mode** (default): full simulation with virtual balance
- **Live mode stub**: scaffold ready for wallet integration
- Duplicate trade prevention per pair

### Trade Journal
- Every trade saved to `journal/trades.json` (append)
- Closed trades exported to `journal/trades.csv`
- Includes: entry/exit price, reason, PnL, PnL%, mode

### Safety Filters
- Minimum liquidity check (default $50,000 USD)
- Minimum 24h volume check (default $10,000 USD)
- Minimum FDV check
- Token blacklist support
- High buy/sell tax detection (honeypot heuristic)

---

## Quick Start

### 1. Install

```bash
npm install
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — BOT_MODE=paper is the safe default
```

### 3. Run in Paper Mode

```bash
# npm script
npm run paper

# Or directly
node src/bot.js --mode=paper

# Or via CLI
node src/cli/interface.js start --mode=paper --interval=30
```

### 4. Check Status

```bash
node src/cli/interface.js status
```

### 5. View Trade Journal

```bash
node src/cli/interface.js journal
node src/cli/interface.js journal --count=50
node src/cli/interface.js journal --all
```

### 6. View Config

```bash
node src/cli/interface.js config
```

---

## Configuration Reference

Edit `config/default.json` or override via `.env`:

```json
{
  "bot": {
    "mode": "paper",          // paper | live
    "interval": 30,           // polling interval (seconds)
    "maxOpenTrades": 3        // max simultaneous positions
  },
  "risk": {
    "maxRiskPerTrade": 0.02,          // 2% of balance per trade
    "defaultStopLossPct": 0.03,       // 3% SL fallback
    "defaultTakeProfitMultiplier": 2, // 2:1 R:R minimum
    "maxDailyLoss": 0.06,             // stop at 6% daily drawdown
    "cooldownAfterLoss": 300,         // 5 min cooldown per pair after loss
    "maxConsecutiveLosses": 3         // halt after 3 losses in a row
  },
  "filters": {
    "minLiquidityUSD": 50000,    // minimum pool liquidity
    "minVolumeUSD": 10000,       // minimum 24h volume
    "minMarketCapUSD": 100000    // minimum FDV
  },
  "strategy": {
    "bosLookback": 20,                // candles to look back for BOS
    "zoneLookback": 50,               // candles to look back for zones
    "liquiditySweepThreshold": 0.005, // 0.5% wick pierce = sweep
    "entryConfirmations": 2           // minimum SMC signals required
  }
}
```

---

## Adding Tokens to Watch

Edit the `WATCHLIST` array in `src/bot.js`:

```js
const WATCHLIST = [
  // By token address (Solana)
  { tokenAddress: 'So11...', chainId: 'solana', label: 'SOL/USDC' },

  // By pair address (EVM)
  { pairAddress: '0xABC...', chainId: 'ethereum', label: 'ETH/USDC' },

  // By search query (picks highest-liquidity result)
  { query: 'BONK', label: 'BONK' },
];
```

---

## Enabling Live Trading (Solana)

1. Install wallet dependencies:
   ```bash
   npm install @solana/web3.js @jup-ag/api bs58
   ```
2. Set `BOT_MODE=live` and `WALLET_PRIVATE_KEY=<base58-key>` in `.env`
3. Set `RPC_URL` to a reliable endpoint (Helius, QuickNode, etc.)
4. Open `src/execution/realTrade.js` — swap logic scaffold is inside with step-by-step comments
5. **Test with a tiny balance first!**

---

## Safety Warning

> This bot is for **educational purposes**. Crypto trading involves significant financial risk.
> - Always start in **paper mode**
> - Never risk money you cannot afford to lose
> - Test on **devnet** before mainnet
> - Audit all code before connecting a real wallet

---

## License

MIT

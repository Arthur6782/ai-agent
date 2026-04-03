'use strict';

/**
 * ============================================================
 *  CRYPTO TRADING BOT — Main Orchestrator
 *  Smart Money Concepts (SMC) DEX trading on Solana / EVM
 * ============================================================
 */

require('dotenv').config();

const config = require('./utils/config');
const logger = require('./utils/logger');
const { fetchMarketData, getCandles } = require('./data/marketData');
const { generateSignal } = require('./strategy/signals');
const { handleSignal, monitorTrades } = require('./execution/orderManager');
const { getStats } = require('./utils/journal');
const { getRiskState, dailyReset } = require('./risk/riskManager');
const { getActiveCooldowns } = require('./risk/cooldown');
const paperTrade = require('./execution/paperTrade');

// ─── WATCHLIST ────────────────────────────────────────────────────────────────
// Configure the tokens/pairs to monitor here.
// Each target is an object: { tokenAddress?, pairAddress?, chainId?, query? }
//
// Examples:
//   Solana token by address:  { tokenAddress: 'So11...', chainId: 'solana' }
//   Pair by address:          { pairAddress: '0xABC...', chainId: 'ethereum' }
//   Search by name:           { query: 'WIF' }

const WATCHLIST = [
  // Wrapped SOL / USDC on Solana (Raydium)
  {
    tokenAddress: 'So11111111111111111111111111111111111111112',
    chainId: 'solana',
    label: 'SOL/USDC',
  },
  // WIF (dogwifhat) on Solana
  {
    tokenAddress: 'EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm',
    chainId: 'solana',
    label: 'WIF/USDC',
  },
  // Uncomment to add EVM pairs:
  // { pairAddress: '0xUNIPOOL...', chainId: 'ethereum', label: 'ETH/USDC' },
];

// ─── STATE ────────────────────────────────────────────────────────────────────
let isRunning = false;
let tickCount = 0;
let intervalHandle = null;

// ─── CORE TICK ────────────────────────────────────────────────────────────────

/**
 * Main trading tick — runs on every interval.
 * For each watched token:
 *   1. Fetch market data
 *   2. Check open trades for SL/TP
 *   3. Generate SMC signal
 *   4. If signal, attempt to open trade
 */
async function tick() {
  tickCount++;
  const balance = paperTrade.getState().balance;
  dailyReset(balance);

  logger.debug(`── Tick #${tickCount} | Mode: ${config.bot.mode.toUpperCase()} | Balance: $${balance.toFixed(2)} ──`);

  const tickPromises = WATCHLIST.map(async target => {
    try {
      // 1. Fetch market data
      const pair = await fetchMarketData(target);
      if (!pair) {
        logger.debug(`No valid data for ${target.label ?? target.tokenAddress}`);
        return;
      }

      // 2. Monitor open trades (check SL/TP)
      await monitorTrades(pair);

      // 3. Get candle history for this pair
      const candles = getCandles(pair.pairAddress);

      // 4. Generate SMC signal
      const signal = generateSignal(pair, candles);

      logger.debug(`${pair.symbol} | Price: $${pair.price} | Signal: ${signal.type} (confidence: ${signal.confidence})`);

      // 5. Act on signal
      if (signal.type !== 'NONE') {
        await handleSignal(signal, pair);
      }
    } catch (err) {
      logger.error(`Tick error for ${target.label ?? 'unknown'}`, { err: err.message });
    }
  });

  await Promise.allSettled(tickPromises);
}

// ─── STARTUP ──────────────────────────────────────────────────────────────────

function printBanner() {
  const mode = config.bot.mode.toUpperCase();
  const modeLabel = mode === 'PAPER' ? '📄 PAPER TRADING' : '🔴 LIVE TRADING';
  console.log('\n' + '═'.repeat(55));
  console.log('  CRYPTO TRADING BOT — SMC Strategy');
  console.log(`  Mode: ${modeLabel}`);
  console.log(`  Watching: ${WATCHLIST.length} pair(s)`);
  console.log(`  Interval: ${config.bot.interval}s`);
  console.log(`  Balance: $${config.wallet.paperBalance}`);
  console.log(`  Max Risk/Trade: ${(config.risk.maxRiskPerTrade * 100).toFixed(1)}%`);
  console.log('═'.repeat(55) + '\n');
}

async function start() {
  if (isRunning) {
    logger.warn('Bot is already running');
    return;
  }

  printBanner();

  if (config.bot.mode === 'live') {
    logger.warn('LIVE MODE: Make sure your wallet is configured in .env!');
    logger.warn('First trade will execute in 10 seconds. Press Ctrl+C to abort.');
    await new Promise(r => setTimeout(r, 10000));
  }

  isRunning = true;
  logger.info(`Bot started. Scanning ${WATCHLIST.length} pair(s) every ${config.bot.interval}s`);

  // Run first tick immediately
  await tick();

  // Schedule subsequent ticks
  intervalHandle = setInterval(async () => {
    if (!isRunning) return;
    try {
      await tick();
    } catch (err) {
      logger.error('Unexpected tick error', { err: err.message });
    }
  }, config.bot.interval * 1000);
}

function stop() {
  if (!isRunning) return;
  isRunning = false;
  if (intervalHandle) clearInterval(intervalHandle);

  logger.info('Bot stopped.');

  const stats = getStats();
  const state = paperTrade.getState();

  console.log('\n' + '─'.repeat(45));
  console.log('  SESSION SUMMARY');
  console.log('─'.repeat(45));
  console.log(`  Final Balance : $${state.balance.toFixed(2)}`);
  console.log(`  Total PnL     : $${state.totalPnl.toFixed(2)} (${state.returnPct}%)`);
  console.log(`  Total Trades  : ${stats.totalTrades}`);
  console.log(`  Win Rate      : ${stats.winRate}%`);
  console.log(`  Best Trade    : $${stats.bestTrade ?? 0}`);
  console.log(`  Worst Trade   : $${stats.worstTrade ?? 0}`);
  console.log('─'.repeat(45) + '\n');
}

// ─── STATUS HELPERS (used by CLI) ────────────────────────────────────────────

function getStatus() {
  return {
    running: isRunning,
    mode: config.bot.mode,
    tickCount,
    watchlist: WATCHLIST.map(t => t.label ?? t.tokenAddress),
    paper: paperTrade.getState(),
    risk: getRiskState(),
    cooldowns: getActiveCooldowns(),
    stats: getStats(),
  };
}

// ─── GRACEFUL SHUTDOWN ───────────────────────────────────────────────────────

process.on('SIGINT', () => {
  logger.info('SIGINT received, shutting down...');
  stop();
  process.exit(0);
});

process.on('SIGTERM', () => {
  logger.info('SIGTERM received, shutting down...');
  stop();
  process.exit(0);
});

process.on('uncaughtException', err => {
  logger.error('Uncaught exception', { err: err.message, stack: err.stack });
  stop();
  process.exit(1);
});

// ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if (require.main === module) {
  start().catch(err => {
    logger.error('Fatal startup error', { err: err.message });
    process.exit(1);
  });
}

module.exports = { start, stop, getStatus, tick, WATCHLIST };

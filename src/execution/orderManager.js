'use strict';

const config = require('../utils/config');
const logger = require('../utils/logger');
const { calculatePositionSize, canTrade, evaluateExit, recordTradeResult } = require('../risk/riskManager');
const { activateCooldown, activateGlobalCooldown, isCoolingDown } = require('../risk/cooldown');
const { validateTradeParams } = require('../utils/validator');
const paperTrade = require('./paperTrade');
const realTrade = require('./realTrade');

// Active orders store (for both paper and live)
const activeOrders = new Map(); // pairAddress -> { tradeId, ... }

/**
 * Attempts to open a new trade based on a generated signal.
 *
 * @param {Object} signal - From strategy/signals.js: { type, stopLoss, takeProfit, reasons }
 * @param {Object} pair - Normalized pair data
 * @returns {Object|null} Opened trade or null if rejected
 */
async function handleSignal(signal, pair) {
  if (signal.type === 'NONE') return null;

  const { pairAddress, symbol, price } = pair;
  const side = signal.type === 'BUY' ? 'buy' : 'sell';

  // Cooldown check
  const cooldown = isCoolingDown(pairAddress);
  if (!cooldown.allowed) {
    logger.info(`OrderManager: ${symbol} in cooldown (${cooldown.remainingSec}s remaining) — ${cooldown.reason}`);
    return null;
  }

  // Get current balance
  const currentState = config.bot.mode === 'paper'
    ? paperTrade.getState()
    : { balance: await realTrade.getWalletBalance() };

  const balance = currentState.balance;
  const openCount = paperTrade.getOpenTrades().length;

  // Risk permission check
  const { allowed, reason: riskReason } = canTrade(balance, openCount);
  if (!allowed) {
    logger.risk('Trade blocked', { pair: symbol, reason: riskReason });
    return null;
  }

  // Calculate position size
  const { sizeUSD, sizeTokens, riskUSD } = calculatePositionSize(
    balance,
    price,
    signal.stopLoss
  );

  // Validate trade parameters
  const { valid, reason: validReason } = validateTradeParams({ size: sizeUSD, price, balance });
  if (!valid) {
    logger.warn(`OrderManager: trade params invalid — ${validReason}`);
    return null;
  }

  // Prevent duplicate trades on the same pair
  if (activeOrders.has(pairAddress)) {
    logger.info(`OrderManager: already have an open trade on ${symbol}`);
    return null;
  }

  const tradeParams = {
    pairAddress,
    symbol,
    side,
    entryPrice: price,
    sizeUSD,
    sizeTokens,
    stopLoss: signal.stopLoss,
    takeProfit: signal.takeProfit,
    entryReason: signal.reasons.join(' | '),
  };

  logger.info(`OrderManager: opening ${side.toUpperCase()} on ${symbol}`, {
    price,
    size: `$${sizeUSD.toFixed(2)}`,
    risk: `$${riskUSD.toFixed(2)}`,
    sl: signal.stopLoss.toFixed(6),
    tp: signal.takeProfit.toFixed(6),
    confidence: signal.confidence,
  });

  let trade;
  if (config.bot.mode === 'paper') {
    trade = paperTrade.openTrade(tradeParams);
  } else {
    const result = await realTrade.executeTrade(tradeParams);
    trade = result; // Live trade tracking (stub)
  }

  if (trade) {
    activeOrders.set(pairAddress, { tradeId: trade.id, side });
  }

  return trade;
}

/**
 * Checks all open trades against current market prices.
 * Closes trades that have hit SL or TP.
 *
 * @param {Object} pair - Current pair with updated price
 */
async function monitorTrades(pair) {
  const { pairAddress, price } = pair;
  const openTrades = paperTrade.getOpenTrades().filter(t => t.pairAddress === pairAddress);

  for (const trade of openTrades) {
    const { shouldExit, reason } = evaluateExit(trade, price);

    if (shouldExit) {
      const closed = config.bot.mode === 'paper'
        ? paperTrade.closeTrade(trade.id, price, reason)
        : await realTrade.closePosition(trade, price, reason);

      if (closed) {
        // Record result in risk manager
        recordTradeResult(closed.pnl);

        // Activate cooldown after a loss
        if (closed.pnl < 0) {
          activateCooldown(pairAddress, undefined, `Loss on ${pair.symbol}: $${closed.pnl.toFixed(2)}`);
        }

        // Remove from active orders
        activeOrders.delete(pairAddress);

        logger.info(`OrderManager: trade closed on ${pair.symbol}`, {
          reason,
          pnl: `$${closed.pnl.toFixed(2)}`,
          pnlPct: `${closed.pnlPct.toFixed(2)}%`,
        });
      }
    } else {
      // Log unrealized PnL
      const unrealized = paperTrade.updateOpenTrades(pairAddress, price);
      for (const u of unrealized) {
        logger.debug(`OrderManager: ${pair.symbol} open trade unrealized P&L`, {
          id: u.id,
          unrealizedPnl: u.unrealizedPnl.toFixed(4),
          currentPrice: price,
          sl: u.stopLoss.toFixed(6),
          tp: u.takeProfit.toFixed(6),
        });
      }
    }
  }
}

/**
 * Returns a summary of all current active orders.
 */
function getActiveOrders() {
  return [...activeOrders.entries()].map(([pair, data]) => ({ pair, ...data }));
}

module.exports = { handleSignal, monitorTrades, getActiveOrders };

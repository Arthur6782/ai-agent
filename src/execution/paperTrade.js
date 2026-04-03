'use strict';

const { v4: uuidv4 } = require === undefined
  ? { v4: () => `${Date.now()}-${Math.random().toString(36).slice(2)}` }
  : require;

// Simple UUID without external dep
function generateId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

const config = require('../utils/config');
const logger = require('../utils/logger');
const { calculatePnL } = require('../risk/riskManager');
const { recordTrade, updateTrade } = require('../utils/journal');

// In-memory paper trading state
const state = {
  balance: config.wallet.paperBalance,
  openTrades: new Map(), // id -> trade
  closedTrades: [],
  totalPnl: 0,
};

/**
 * Opens a simulated (paper) trade.
 *
 * @param {Object} params
 * @param {string} params.pairAddress
 * @param {string} params.symbol
 * @param {'buy'|'sell'} params.side
 * @param {number} params.entryPrice
 * @param {number} params.sizeUSD
 * @param {number} params.sizeTokens
 * @param {number} params.stopLoss
 * @param {number} params.takeProfit
 * @param {string} params.entryReason
 * @returns {Object} trade object
 */
function openTrade(params) {
  const {
    pairAddress, symbol, side, entryPrice,
    sizeUSD, sizeTokens, stopLoss, takeProfit, entryReason,
  } = params;

  if (sizeUSD > state.balance) {
    logger.warn(`PaperTrade: insufficient balance. Need $${sizeUSD.toFixed(2)}, have $${state.balance.toFixed(2)}`);
    return null;
  }

  const id = generateId();
  const trade = {
    id,
    pairAddress,
    pair: symbol,
    side,
    entryPrice,
    exitPrice: null,
    sizeUSD,
    sizeTokens,
    stopLoss,
    takeProfit,
    pnl: null,
    pnlPct: null,
    status: 'open',
    entryReason,
    exitReason: null,
    mode: 'paper',
    timestamp: new Date().toISOString(),
  };

  // Reserve funds
  state.balance -= sizeUSD;
  state.openTrades.set(id, trade);

  recordTrade(trade);

  logger.trade('PAPER OPEN', {
    id,
    pair: symbol,
    side,
    price: entryPrice,
    size: sizeUSD,
    sl: stopLoss,
    tp: takeProfit,
    balance: state.balance.toFixed(2),
  });

  return trade;
}

/**
 * Closes an open paper trade at the given price.
 *
 * @param {string} id - Trade ID
 * @param {number} exitPrice
 * @param {string} exitReason
 * @returns {Object|null} closed trade or null
 */
function closeTrade(id, exitPrice, exitReason) {
  const trade = state.openTrades.get(id);
  if (!trade) {
    logger.warn(`PaperTrade: trade ${id} not found`);
    return null;
  }

  const pnl = calculatePnL({ ...trade, exitPrice });
  const pnlPct = (pnl / trade.sizeUSD) * 100;

  const closed = {
    ...trade,
    exitPrice,
    exitReason,
    pnl: parseFloat(pnl.toFixed(4)),
    pnlPct: parseFloat(pnlPct.toFixed(2)),
    status: 'closed',
    closedAt: new Date().toISOString(),
  };

  // Return funds + PnL to balance
  state.balance += trade.sizeUSD + pnl;
  state.totalPnl += pnl;
  state.openTrades.delete(id);
  state.closedTrades.push(closed);

  updateTrade(id, {
    exitPrice: closed.exitPrice,
    exitReason: closed.exitReason,
    pnl: closed.pnl,
    pnlPct: closed.pnlPct,
    status: 'closed',
    closedAt: closed.closedAt,
  });

  logger.trade('PAPER CLOSE', {
    id,
    pair: closed.pair,
    side: closed.side,
    entryPrice: closed.entryPrice,
    exitPrice,
    pnl: `$${pnl.toFixed(2)}`,
    pnlPct: `${pnlPct.toFixed(2)}%`,
    reason: exitReason,
    balance: state.balance.toFixed(2),
  });

  return closed;
}

/**
 * Updates unrealized PnL for all open trades (for display).
 * @param {string} pairAddress
 * @param {number} currentPrice
 * @returns {Object[]} open trades with unrealized PnL
 */
function updateOpenTrades(pairAddress, currentPrice) {
  const updated = [];
  for (const trade of state.openTrades.values()) {
    if (trade.pairAddress !== pairAddress) continue;
    const unrealizedPnl = calculatePnL({ ...trade, exitPrice: currentPrice });
    updated.push({ ...trade, currentPrice, unrealizedPnl });
  }
  return updated;
}

/**
 * Returns all open trades.
 */
function getOpenTrades() {
  return [...state.openTrades.values()];
}

/**
 * Returns current paper trading state snapshot.
 */
function getState() {
  return {
    balance: state.balance,
    openTradesCount: state.openTrades.size,
    closedTradesCount: state.closedTrades.length,
    totalPnl: state.totalPnl,
    initialBalance: config.wallet.paperBalance,
    returnPct: ((state.totalPnl / config.wallet.paperBalance) * 100).toFixed(2),
  };
}

module.exports = { openTrade, closeTrade, updateOpenTrades, getOpenTrades, getState };

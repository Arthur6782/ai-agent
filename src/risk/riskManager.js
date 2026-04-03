'use strict';

const config = require('../utils/config');
const logger = require('../utils/logger');

const {
  maxRiskPerTrade,
  defaultStopLossPct,
  maxDailyLoss,
  maxConsecutiveLosses,
} = config.risk;

// Runtime state
const state = {
  dailyPnl: 0,
  consecutiveLosses: 0,
  dailyStartBalance: null,
  lastResetDate: null,
};

// ─── DAILY RESET ────────────────────────────────────────────────────────────

/**
 * Resets daily counters at the start of each trading day.
 * @param {number} currentBalance
 */
function dailyReset(currentBalance) {
  const today = new Date().toDateString();
  if (state.lastResetDate !== today) {
    state.dailyPnl = 0;
    state.dailyStartBalance = currentBalance;
    state.lastResetDate = today;
    logger.info('RiskManager: daily counters reset', { balance: currentBalance });
  }
}

// ─── POSITION SIZING ────────────────────────────────────────────────────────

/**
 * Calculates the position size based on account balance and risk parameters.
 * Uses fixed fractional position sizing:
 *   riskAmount = balance * maxRiskPerTrade
 *   positionSize = riskAmount / (entryPrice - stopLoss) * entryPrice
 *
 * @param {number} balance - Current account balance in USD
 * @param {number} entryPrice - Planned entry price
 * @param {number} stopLoss - Stop loss price
 * @param {number} [customRiskPct] - Override risk % (optional)
 * @returns {{ sizeUSD: number, sizeTokens: number, riskUSD: number, rr: number }}
 */
function calculatePositionSize(balance, entryPrice, stopLoss, customRiskPct) {
  const riskPct = customRiskPct ?? maxRiskPerTrade;
  const riskUSD = balance * riskPct;
  const stopDistancePct = Math.abs(entryPrice - stopLoss) / entryPrice;

  if (stopDistancePct === 0) {
    logger.warn('RiskManager: stop distance is zero, using default stop');
    const fallback = balance * riskPct / defaultStopLossPct;
    return { sizeUSD: Math.min(fallback, balance * 0.5), sizeTokens: 0, riskUSD, rr: 0 };
  }

  // Position size = how much USD to allocate so that if SL is hit, we lose exactly riskUSD
  const sizeUSD = riskUSD / stopDistancePct;
  const capped = Math.min(sizeUSD, balance * 0.5); // Never risk more than 50% of balance
  const sizeTokens = capped / entryPrice;

  return {
    sizeUSD: parseFloat(capped.toFixed(4)),
    sizeTokens: parseFloat(sizeTokens.toFixed(8)),
    riskUSD: parseFloat(riskUSD.toFixed(4)),
    stopDistancePct: parseFloat((stopDistancePct * 100).toFixed(2)),
  };
}

// ─── TRADE PERMISSION CHECKS ────────────────────────────────────────────────

/**
 * Determines if a new trade is allowed given current risk state.
 * @param {number} balance
 * @param {number} openTradesCount
 * @returns {{ allowed: boolean, reason: string|null }}
 */
function canTrade(balance, openTradesCount) {
  // Max open trades
  if (openTradesCount >= config.bot.maxOpenTrades) {
    return { allowed: false, reason: `Max open trades reached (${config.bot.maxOpenTrades})` };
  }

  // Daily loss limit
  dailyReset(balance);
  const dailyDrawdown = state.dailyPnl / (state.dailyStartBalance || balance);
  if (dailyDrawdown <= -maxDailyLoss) {
    return {
      allowed: false,
      reason: `Daily loss limit hit: ${(dailyDrawdown * 100).toFixed(2)}% (max ${(maxDailyLoss * 100).toFixed(1)}%)`,
    };
  }

  // Consecutive losses
  if (state.consecutiveLosses >= maxConsecutiveLosses) {
    return {
      allowed: false,
      reason: `Too many consecutive losses: ${state.consecutiveLosses} (max ${maxConsecutiveLosses})`,
    };
  }

  return { allowed: true, reason: null };
}

// ─── TRADE EXIT CHECKS ──────────────────────────────────────────────────────

/**
 * Evaluates whether an open trade should be exited based on current price.
 * @param {Object} trade - Open trade object
 * @param {number} currentPrice
 * @returns {{ shouldExit: boolean, reason: string|null }}
 */
function evaluateExit(trade, currentPrice) {
  const { side, stopLoss, takeProfit } = trade;

  if (side === 'buy') {
    if (currentPrice <= stopLoss) {
      return { shouldExit: true, reason: 'Stop loss hit' };
    }
    if (currentPrice >= takeProfit) {
      return { shouldExit: true, reason: 'Take profit hit' };
    }
  }

  if (side === 'sell') {
    if (currentPrice >= stopLoss) {
      return { shouldExit: true, reason: 'Stop loss hit' };
    }
    if (currentPrice <= takeProfit) {
      return { shouldExit: true, reason: 'Take profit hit' };
    }
  }

  return { shouldExit: false, reason: null };
}

// ─── PNL & STATE TRACKING ───────────────────────────────────────────────────

/**
 * Records the result of a closed trade, updating risk counters.
 * @param {number} pnl - Realized PnL in USD
 */
function recordTradeResult(pnl) {
  state.dailyPnl += pnl;

  if (pnl < 0) {
    state.consecutiveLosses++;
    logger.risk('Loss recorded', {
      pnl: pnl.toFixed(2),
      consecutiveLosses: state.consecutiveLosses,
      dailyPnl: state.dailyPnl.toFixed(2),
    });
  } else {
    state.consecutiveLosses = 0;
    logger.info('RiskManager: win recorded', {
      pnl: pnl.toFixed(2),
      dailyPnl: state.dailyPnl.toFixed(2),
    });
  }
}

/**
 * Returns current risk state snapshot.
 */
function getRiskState() {
  return { ...state };
}

/**
 * Computes the realized PnL for a closed trade.
 * @param {Object} trade - { side, entryPrice, exitPrice, sizeTokens }
 * @returns {number} PnL in USD
 */
function calculatePnL(trade) {
  const { side, entryPrice, exitPrice, sizeTokens } = trade;
  if (side === 'buy') {
    return (exitPrice - entryPrice) * sizeTokens;
  }
  return (entryPrice - exitPrice) * sizeTokens;
}

module.exports = {
  calculatePositionSize,
  canTrade,
  evaluateExit,
  recordTradeResult,
  getRiskState,
  calculatePnL,
  dailyReset,
};

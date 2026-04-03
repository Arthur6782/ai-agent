'use strict';

const { detectZones, detectSwings, isPriceInZone } = require('./zones');
const { analyzeSMC } = require('./smc');
const config = require('../utils/config');
const logger = require('../utils/logger');

const { entryConfirmations } = config.strategy;

/**
 * Signal types:
 *   - BUY  : enter long position
 *   - SELL : enter short position (or close long)
 *   - NONE : no actionable signal
 */

/**
 * Core SMC sniper entry logic.
 *
 * Entry conditions for LONG:
 *   1. Bullish BOS or Bullish CHoCH confirmed
 *   2. Price retraces into a Demand zone (or order block)
 *   3. Optional: bullish liquidity sweep occurred before entry
 *   4. Enough confirmations met (configurable)
 *
 * Entry conditions for SHORT:
 *   1. Bearish BOS or Bearish CHoCH confirmed
 *   2. Price retraces into a Supply zone (or order block)
 *   3. Optional: bearish liquidity sweep occurred before entry
 *   4. Enough confirmations met
 *
 * @param {Object} pair - Normalized market data (from marketData.js)
 * @param {Object[]} candles - OHLCV candle history
 * @returns {Object} Signal: { type, confidence, reasons, stopLoss, takeProfit }
 */
function generateSignal(pair, candles) {
  if (candles.length < 30) {
    return { type: 'NONE', confidence: 0, reasons: ['Insufficient candle data'] };
  }

  const price = pair.price;
  const swings = detectSwings(candles);
  const { supplyZones, demandZones } = detectZones(candles);
  const smc = analyzeSMC(candles, swings);

  const buyReasons = [];
  const sellReasons = [];
  let buyConfidence = 0;
  let sellConfidence = 0;

  // ── BULLISH SIGNALS ──────────────────────────────────────────────

  // 1. Bullish BOS
  if (smc.bos?.direction === 'bullish') {
    buyReasons.push(`Bullish BOS at ${smc.bos.level.toFixed(6)}`);
    buyConfidence += 2;
  }

  // 2. Bullish CHoCH (stronger reversal signal)
  if (smc.choch?.direction === 'bullish') {
    buyReasons.push(`Bullish CHoCH at ${smc.choch.level.toFixed(6)}`);
    buyConfidence += 2;
  }

  // 3. Price in demand zone
  const activeDemandZone = demandZones.find(z => isPriceInZone(price, z));
  if (activeDemandZone) {
    buyReasons.push(`Price in demand zone ${activeDemandZone.bottom.toFixed(6)}–${activeDemandZone.top.toFixed(6)} (strength: ${activeDemandZone.strength})`);
    buyConfidence += activeDemandZone.strength;
  }

  // 4. Price in bullish order block
  if (smc.orderBlock?.direction === 'bullish' && isPriceInZone(price, smc.orderBlock)) {
    buyReasons.push(`Price in bullish OB ${smc.orderBlock.bottom.toFixed(6)}–${smc.orderBlock.top.toFixed(6)}`);
    buyConfidence += 2;
  }

  // 5. Bullish liquidity sweep (stop hunt = smart money accumulation)
  if (smc.liquiditySweep?.direction === 'bullish') {
    buyReasons.push(`Bullish liquidity sweep — swept ${smc.liquiditySweep.sweptLevel.toFixed(6)}`);
    buyConfidence += 3;
  }

  // 6. Bullish trend confirmation
  if (smc.trend === 'bullish') {
    buyReasons.push('Overall bullish market structure');
    buyConfidence += 1;
  }

  // ── BEARISH SIGNALS ──────────────────────────────────────────────

  // 1. Bearish BOS
  if (smc.bos?.direction === 'bearish') {
    sellReasons.push(`Bearish BOS at ${smc.bos.level.toFixed(6)}`);
    sellConfidence += 2;
  }

  // 2. Bearish CHoCH
  if (smc.choch?.direction === 'bearish') {
    sellReasons.push(`Bearish CHoCH at ${smc.choch.level.toFixed(6)}`);
    sellConfidence += 2;
  }

  // 3. Price in supply zone
  const activeSupplyZone = supplyZones.find(z => isPriceInZone(price, z));
  if (activeSupplyZone) {
    sellReasons.push(`Price in supply zone ${activeSupplyZone.bottom.toFixed(6)}–${activeSupplyZone.top.toFixed(6)} (strength: ${activeSupplyZone.strength})`);
    sellConfidence += activeSupplyZone.strength;
  }

  // 4. Price in bearish order block
  if (smc.orderBlock?.direction === 'bearish' && isPriceInZone(price, smc.orderBlock)) {
    sellReasons.push(`Price in bearish OB ${smc.orderBlock.bottom.toFixed(6)}–${smc.orderBlock.top.toFixed(6)}`);
    sellConfidence += 2;
  }

  // 5. Bearish liquidity sweep
  if (smc.liquiditySweep?.direction === 'bearish') {
    sellReasons.push(`Bearish liquidity sweep — swept ${smc.liquiditySweep.sweptLevel.toFixed(6)}`);
    sellConfidence += 3;
  }

  // 6. Bearish trend confirmation
  if (smc.trend === 'bearish') {
    sellReasons.push('Overall bearish market structure');
    sellConfidence += 1;
  }

  // ── DECISION ──────────────────────────────────────────────────────

  // Require minimum confirmations to fire a signal
  if (buyConfidence >= entryConfirmations && buyConfidence > sellConfidence) {
    const sl = computeStopLoss('buy', price, activeDemandZone, smc);
    const tp = computeTakeProfit('buy', price, sl, supplyZones);

    logger.signal('BUY', {
      pair: pair.symbol,
      price,
      confidence: buyConfidence,
      reasons: buyReasons,
    });

    return {
      type: 'BUY',
      confidence: buyConfidence,
      reasons: buyReasons,
      stopLoss: sl,
      takeProfit: tp,
      smcContext: smc,
    };
  }

  if (sellConfidence >= entryConfirmations && sellConfidence > buyConfidence) {
    const sl = computeStopLoss('sell', price, activeSupplyZone, smc);
    const tp = computeTakeProfit('sell', price, sl, demandZones);

    logger.signal('SELL', {
      pair: pair.symbol,
      price,
      confidence: sellConfidence,
      reasons: sellReasons,
    });

    return {
      type: 'SELL',
      confidence: sellConfidence,
      reasons: sellReasons,
      stopLoss: sl,
      takeProfit: tp,
      smcContext: smc,
    };
  }

  return {
    type: 'NONE',
    confidence: Math.max(buyConfidence, sellConfidence),
    reasons: buyConfidence > sellConfidence ? buyReasons : sellReasons,
    smcContext: smc,
  };
}

// ── STOP LOSS & TAKE PROFIT HELPERS ─────────────────────────────────────────

/**
 * Computes the stop loss level for a trade.
 * For BUY: SL is placed just below the demand zone bottom (or OB bottom).
 * For SELL: SL is placed just above the supply zone top (or OB top).
 */
function computeStopLoss(side, price, activeZone, smc) {
  const defaultSlPct = config.risk.defaultStopLossPct;
  const buffer = 0.001; // 0.1% buffer beyond zone

  if (side === 'buy') {
    const zoneBottom = activeZone?.bottom ?? smc.orderBlock?.bottom;
    if (zoneBottom) return zoneBottom * (1 - buffer);
    return price * (1 - defaultSlPct);
  }

  if (side === 'sell') {
    const zoneTop = activeZone?.top ?? smc.orderBlock?.top;
    if (zoneTop) return zoneTop * (1 + buffer);
    return price * (1 + defaultSlPct);
  }

  return price * (1 - defaultSlPct);
}

/**
 * Computes take profit using the Risk:Reward ratio.
 * TP is set at a minimum 2:1 R:R unless a stronger zone is nearby.
 */
function computeTakeProfit(side, price, stopLoss, opposingZones) {
  const rrRatio = config.risk.defaultTakeProfitMultiplier;
  const risk = Math.abs(price - stopLoss);

  const defaultTP = side === 'buy'
    ? price + risk * rrRatio
    : price - risk * rrRatio;

  // If there's an opposing zone closer than default TP, use that as target
  if (opposingZones.length > 0) {
    const nearestOpposing = side === 'buy'
      ? opposingZones.find(z => z.midpoint > price)
      : opposingZones.find(z => z.midpoint < price);

    if (nearestOpposing) {
      const zoneTP = side === 'buy' ? nearestOpposing.bottom : nearestOpposing.top;
      // Only use zone TP if it gives at least 1.5:1 R:R
      const zoneRR = Math.abs(price - zoneTP) / risk;
      if (zoneRR >= 1.5) return zoneTP;
    }
  }

  return defaultTP;
}

module.exports = { generateSignal };

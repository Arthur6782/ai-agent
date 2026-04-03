'use strict';

const config = require('../utils/config');

/**
 * Smart Money Concepts (SMC) Engine
 *
 * Implements:
 *   1. Break of Structure (BOS) — trend continuation signal
 *   2. Change of Character (CHoCH) — trend reversal signal
 *   3. Liquidity Sweeps — detecting stop hunts above/below swing points
 *   4. Order Blocks — institutional candles before a BOS
 */

const { bosLookback, liquiditySweepThreshold } = config.strategy;

// ─── TREND & STRUCTURE ───────────────────────────────────────────────────────

/**
 * Determines the current market structure trend.
 * Bullish: price making higher highs (HH) and higher lows (HL).
 * Bearish: price making lower highs (LH) and lower lows (LL).
 *
 * @param {Object[]} candles
 * @returns {'bullish'|'bearish'|'ranging'}
 */
function detectTrend(candles) {
  if (candles.length < 4) return 'ranging';

  const recent = candles.slice(-bosLookback);
  let hhCount = 0;
  let hlCount = 0;
  let lhCount = 0;
  let llCount = 0;

  for (let i = 1; i < recent.length; i++) {
    if (recent[i].high > recent[i - 1].high) hhCount++;
    else lhCount++;
    if (recent[i].low > recent[i - 1].low) hlCount++;
    else llCount++;
  }

  if (hhCount > lhCount && hlCount > llCount) return 'bullish';
  if (lhCount > hhCount && llCount > hlCount) return 'bearish';
  return 'ranging';
}

// ─── BREAK OF STRUCTURE (BOS) ─────────────────────────────────────────────────

/**
 * Detects a Break of Structure.
 * BOS occurs when price closes ABOVE a prior swing high (bullish BOS)
 * or BELOW a prior swing low (bearish BOS).
 *
 * @param {Object[]} candles
 * @param {{ swingHighs: Object[], swingLows: Object[] }} swings
 * @returns {Object|null} BOS event or null
 */
function detectBOS(candles, swings) {
  if (candles.length < 3) return null;

  const currentClose = candles[candles.length - 1].close;
  const prevClose = candles[candles.length - 2].close;

  // Bullish BOS: close above last swing high
  if (swings.swingHighs.length > 0) {
    const lastSwingHigh = swings.swingHighs[swings.swingHighs.length - 1];
    if (prevClose <= lastSwingHigh.price && currentClose > lastSwingHigh.price) {
      return {
        type: 'BOS',
        direction: 'bullish',
        level: lastSwingHigh.price,
        candle: candles[candles.length - 1],
        description: `Bullish BOS — closed above swing high at ${lastSwingHigh.price.toFixed(6)}`,
      };
    }
  }

  // Bearish BOS: close below last swing low
  if (swings.swingLows.length > 0) {
    const lastSwingLow = swings.swingLows[swings.swingLows.length - 1];
    if (prevClose >= lastSwingLow.price && currentClose < lastSwingLow.price) {
      return {
        type: 'BOS',
        direction: 'bearish',
        level: lastSwingLow.price,
        candle: candles[candles.length - 1],
        description: `Bearish BOS — closed below swing low at ${lastSwingLow.price.toFixed(6)}`,
      };
    }
  }

  return null;
}

// ─── CHANGE OF CHARACTER (CHoCH) ─────────────────────────────────────────────

/**
 * Detects a Change of Character — first opposing BOS after a trend.
 * Signals potential trend reversal.
 *
 * @param {Object[]} candles
 * @param {string} currentTrend - 'bullish' | 'bearish'
 * @param {{ swingHighs: Object[], swingLows: Object[] }} swings
 * @returns {Object|null}
 */
function detectCHoCH(candles, currentTrend, swings) {
  if (candles.length < 3) return null;

  const currentClose = candles[candles.length - 1].close;
  const prevClose = candles[candles.length - 2].close;

  if (currentTrend === 'bullish' && swings.swingLows.length > 0) {
    // In bullish trend: CHoCH if we break BELOW an HL (higher low)
    const lastSwingLow = swings.swingLows[swings.swingLows.length - 1];
    if (prevClose >= lastSwingLow.price && currentClose < lastSwingLow.price) {
      return {
        type: 'CHoCH',
        direction: 'bearish',
        level: lastSwingLow.price,
        candle: candles[candles.length - 1],
        description: `Bearish CHoCH — bullish structure broken at ${lastSwingLow.price.toFixed(6)}`,
      };
    }
  }

  if (currentTrend === 'bearish' && swings.swingHighs.length > 0) {
    // In bearish trend: CHoCH if we break ABOVE an LH (lower high)
    const lastSwingHigh = swings.swingHighs[swings.swingHighs.length - 1];
    if (prevClose <= lastSwingHigh.price && currentClose > lastSwingHigh.price) {
      return {
        type: 'CHoCH',
        direction: 'bullish',
        level: lastSwingHigh.price,
        candle: candles[candles.length - 1],
        description: `Bullish CHoCH — bearish structure broken at ${lastSwingHigh.price.toFixed(6)}`,
      };
    }
  }

  return null;
}

// ─── LIQUIDITY SWEEPS ────────────────────────────────────────────────────────

/**
 * Detects a liquidity sweep event.
 * A sweep occurs when price briefly pierces a swing high/low (taking out stops)
 * but then quickly reverses back within the same or next candle.
 *
 * @param {Object[]} candles
 * @param {{ swingHighs: Object[], swingLows: Object[] }} swings
 * @returns {Object|null} sweep event or null
 */
function detectLiquiditySweep(candles, swings) {
  if (candles.length < 2) return null;

  const current = candles[candles.length - 1];
  const threshold = liquiditySweepThreshold; // 0.5% pierce by default

  // Bullish sweep: wick went below swing low then closed above it
  if (swings.swingLows.length > 0) {
    const lastLow = swings.swingLows[swings.swingLows.length - 1];
    const piercedBelow = current.low < lastLow.price * (1 - threshold);
    const closedAbove = current.close > lastLow.price;

    if (piercedBelow && closedAbove) {
      return {
        type: 'liquiditySweep',
        direction: 'bullish',
        sweptLevel: lastLow.price,
        wickLow: current.low,
        close: current.close,
        candle: current,
        description: `Bullish liquidity sweep — swept low at ${lastLow.price.toFixed(6)}, reversed to ${current.close.toFixed(6)}`,
      };
    }
  }

  // Bearish sweep: wick went above swing high then closed below it
  if (swings.swingHighs.length > 0) {
    const lastHigh = swings.swingHighs[swings.swingHighs.length - 1];
    const piercedAbove = current.high > lastHigh.price * (1 + threshold);
    const closedBelow = current.close < lastHigh.price;

    if (piercedAbove && closedBelow) {
      return {
        type: 'liquiditySweep',
        direction: 'bearish',
        sweptLevel: lastHigh.price,
        wickHigh: current.high,
        close: current.close,
        candle: current,
        description: `Bearish liquidity sweep — swept high at ${lastHigh.price.toFixed(6)}, reversed to ${current.close.toFixed(6)}`,
      };
    }
  }

  return null;
}

// ─── ORDER BLOCKS ─────────────────────────────────────────────────────────────

/**
 * Identifies order blocks — the last opposing candle before a BOS.
 * Bullish OB: last bearish (red) candle before a bullish BOS.
 * Bearish OB: last bullish (green) candle before a bearish BOS.
 *
 * @param {Object[]} candles
 * @param {Object} bos - BOS event
 * @returns {Object|null} order block zone
 */
function findOrderBlock(candles, bos) {
  if (!bos) return null;

  const bosIdx = candles.findIndex(c => c.timestamp === bos.candle.timestamp);
  if (bosIdx < 2) return null;

  if (bos.direction === 'bullish') {
    // Find last bearish candle before the BOS
    for (let i = bosIdx - 1; i >= Math.max(0, bosIdx - 10); i--) {
      const c = candles[i];
      if (c.close < c.open) { // bearish candle
        return {
          type: 'orderBlock',
          direction: 'bullish',
          top: c.open,
          bottom: c.close,
          midpoint: (c.open + c.close) / 2,
          candle: c,
          description: `Bullish OB at ${c.close.toFixed(6)} – ${c.open.toFixed(6)}`,
        };
      }
    }
  }

  if (bos.direction === 'bearish') {
    // Find last bullish candle before the BOS
    for (let i = bosIdx - 1; i >= Math.max(0, bosIdx - 10); i--) {
      const c = candles[i];
      if (c.close > c.open) { // bullish candle
        return {
          type: 'orderBlock',
          direction: 'bearish',
          top: c.close,
          bottom: c.open,
          midpoint: (c.open + c.close) / 2,
          candle: c,
          description: `Bearish OB at ${c.open.toFixed(6)} – ${c.close.toFixed(6)}`,
        };
      }
    }
  }

  return null;
}

// ─── FULL SMC ANALYSIS ───────────────────────────────────────────────────────

/**
 * Runs the full SMC analysis on candle data + pre-detected swings/zones.
 * Returns all active SMC signals.
 *
 * @param {Object[]} candles
 * @param {{ swingHighs: Object[], swingLows: Object[] }} swings
 * @returns {Object} Full SMC analysis result
 */
function analyzeSMC(candles, swings) {
  const trend = detectTrend(candles);
  const bos = detectBOS(candles, swings);
  const choch = detectCHoCH(candles, trend, swings);
  const liquiditySweep = detectLiquiditySweep(candles, swings);
  const orderBlock = findOrderBlock(candles, bos || choch);

  return {
    trend,
    bos,
    choch,
    liquiditySweep,
    orderBlock,
    timestamp: Date.now(),
  };
}

module.exports = {
  analyzeSMC,
  detectTrend,
  detectBOS,
  detectCHoCH,
  detectLiquiditySweep,
  findOrderBlock,
};

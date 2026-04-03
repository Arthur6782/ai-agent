'use strict';

const config = require('../utils/config');

/**
 * Supply & Demand Zone Detection
 *
 * A Supply zone is a price area where price previously turned sharply DOWN
 * (sellers overwhelmed buyers — unfilled sell orders remain).
 *
 * A Demand zone is a price area where price previously turned sharply UP
 * (buyers overwhelmed sellers — unfilled buy orders remain).
 *
 * Zone strength = number of times price has respected (bounced off) the zone.
 */

const { zoneLookback, minZoneStrength } = config.strategy;

/**
 * Detects swing highs and lows from candle data.
 * A swing high = candle whose high is the highest in a window of `window` candles.
 * A swing low  = candle whose low is the lowest in a window of `window` candles.
 *
 * @param {Object[]} candles - OHLCV candle array
 * @param {number} window - pivot window size (default 5)
 * @returns {{ swingHighs: Object[], swingLows: Object[] }}
 */
function detectSwings(candles, window = 5) {
  const swingHighs = [];
  const swingLows = [];

  for (let i = window; i < candles.length - window; i++) {
    const slice = candles.slice(i - window, i + window + 1);
    const center = candles[i];

    const isSwingHigh = slice.every(c => c.high <= center.high);
    const isSwingLow = slice.every(c => c.low >= center.low);

    if (isSwingHigh) {
      swingHighs.push({ index: i, price: center.high, candle: center });
    }
    if (isSwingLow) {
      swingLows.push({ index: i, price: center.low, candle: center });
    }
  }

  return { swingHighs, swingLows };
}

/**
 * Builds Supply zones from swing highs.
 * Each zone spans from the base candle's open to its high.
 *
 * @param {Object[]} candles
 * @param {Object[]} swingHighs
 * @returns {Object[]} Supply zones
 */
function buildSupplyZones(candles, swingHighs) {
  return swingHighs.map(sh => {
    const c = sh.candle;
    const zoneTop = c.high;
    const zoneBottom = Math.min(c.open, c.close); // base of the zone

    // Count how many times price touched this zone from below
    const touches = candles.filter(
      candle => candle.high >= zoneBottom && candle.high <= zoneTop
    ).length;

    return {
      type: 'supply',
      top: zoneTop,
      bottom: zoneBottom,
      midpoint: (zoneTop + zoneBottom) / 2,
      strength: touches,
      index: sh.index,
      timestamp: c.timestamp,
      active: true,
    };
  }).filter(z => z.strength >= minZoneStrength);
}

/**
 * Builds Demand zones from swing lows.
 * Each zone spans from the base candle's low to its open/close (whichever is higher).
 *
 * @param {Object[]} candles
 * @param {Object[]} swingLows
 * @returns {Object[]} Demand zones
 */
function buildDemandZones(candles, swingLows) {
  return swingLows.map(sl => {
    const c = sl.candle;
    const zoneBottom = c.low;
    const zoneTop = Math.max(c.open, c.close); // base of the zone

    // Count how many times price touched this zone from above
    const touches = candles.filter(
      candle => candle.low <= zoneTop && candle.low >= zoneBottom
    ).length;

    return {
      type: 'demand',
      top: zoneTop,
      bottom: zoneBottom,
      midpoint: (zoneTop + zoneBottom) / 2,
      strength: touches,
      index: sl.index,
      timestamp: c.timestamp,
      active: true,
    };
  }).filter(z => z.strength >= minZoneStrength);
}

/**
 * Main zone detection function.
 * Returns supply and demand zones sorted by strength (strongest first).
 *
 * @param {Object[]} candles - OHLCV candles (most recent = last)
 * @returns {{ supplyZones: Object[], demandZones: Object[] }}
 */
function detectZones(candles) {
  if (candles.length < zoneLookback) {
    return { supplyZones: [], demandZones: [] };
  }

  // Use only the recent N candles for zone detection
  const recent = candles.slice(-zoneLookback);
  const { swingHighs, swingLows } = detectSwings(recent);

  const supplyZones = buildSupplyZones(recent, swingHighs)
    .sort((a, b) => b.strength - a.strength);

  const demandZones = buildDemandZones(recent, swingLows)
    .sort((a, b) => b.strength - a.strength);

  return { supplyZones, demandZones };
}

/**
 * Checks if current price is inside or touching a zone.
 * @param {number} price
 * @param {Object} zone
 * @param {number} bufferPct - tolerance buffer as fraction (default 0.002 = 0.2%)
 * @returns {boolean}
 */
function isPriceInZone(price, zone, bufferPct = 0.002) {
  const buffer = zone.midpoint * bufferPct;
  return price >= zone.bottom - buffer && price <= zone.top + buffer;
}

module.exports = { detectZones, detectSwings, isPriceInZone };

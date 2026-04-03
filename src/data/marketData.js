'use strict';

const { getPairsByToken, getPairByAddress, searchPairs, normalizePair } = require('./dexscreener');
const { getPrices, normalizeJupiterPrice } = require('./jupiter');
const { validatePair } = require('../utils/validator');
const logger = require('../utils/logger');
const config = require('../utils/config');

// Candle / price history cache per pair
// Structure: { [pairAddress]: Candle[] }
const priceHistory = {};
const MAX_CANDLES = 200;

/**
 * Represents one OHLCV candle built from polling price data.
 */
function makeCandle(price, volume, timestamp) {
  return { open: price, high: price, low: price, close: price, volume, timestamp };
}

/**
 * Updates the candle cache for a pair on each tick.
 * Groups ticks into pseudo-candles (one per poll interval).
 */
function updateCandle(pairAddress, price, volume) {
  if (!priceHistory[pairAddress]) priceHistory[pairAddress] = [];

  const history = priceHistory[pairAddress];
  const now = Date.now();

  if (history.length === 0) {
    history.push(makeCandle(price, volume, now));
    return;
  }

  // Each poll tick creates a new candle (interval-based)
  const lastCandle = history[history.length - 1];
  const intervalMs = config.bot.interval * 1000;

  if (now - lastCandle.timestamp < intervalMs) {
    // Update current candle
    lastCandle.close = price;
    lastCandle.high = Math.max(lastCandle.high, price);
    lastCandle.low = Math.min(lastCandle.low, price);
    lastCandle.volume = (lastCandle.volume || 0) + volume;
  } else {
    // New candle
    history.push(makeCandle(price, volume, now));
    if (history.length > MAX_CANDLES) history.shift();
  }
}

/**
 * Returns cached OHLCV candles for a pair.
 * @param {string} pairAddress
 * @returns {Object[]}
 */
function getCandles(pairAddress) {
  return priceHistory[pairAddress] ?? [];
}

/**
 * Fetches and validates market data for a given token/pair.
 * Tries Dexscreener first; falls back to Jupiter for Solana.
 *
 * @param {Object} target - { tokenAddress?, chainId?, pairAddress?, source? }
 * @returns {Object|null} Normalized pair data or null if invalid
 */
async function fetchMarketData(target) {
  let normalizedPair = null;

  try {
    if (target.pairAddress && target.chainId) {
      // Fetch specific pair
      const raw = await getPairByAddress(target.chainId, target.pairAddress);
      if (raw) normalizedPair = normalizePair(raw);
    } else if (target.tokenAddress) {
      // Fetch by token address
      const pairs = await getPairsByToken(target.tokenAddress);
      if (pairs.length > 0) {
        // Pick pair with highest liquidity
        const best = pairs.sort((a, b) => (b.liquidity?.usd ?? 0) - (a.liquidity?.usd ?? 0))[0];
        normalizedPair = normalizePair(best);
      } else if (target.chainId === 'solana') {
        // Fallback: Jupiter price for Solana
        const prices = await getPrices(target.tokenAddress);
        const jupData = prices[target.tokenAddress];
        if (jupData) normalizedPair = normalizeJupiterPrice(target.tokenAddress, jupData);
      }
    } else if (target.query) {
      const pairs = await searchPairs(target.query);
      if (pairs.length > 0) {
        const best = pairs.sort((a, b) => (b.liquidity?.usd ?? 0) - (a.liquidity?.usd ?? 0))[0];
        normalizedPair = normalizePair(best);
      }
    }
  } catch (err) {
    logger.error('MarketData: fetch error', { target, err: err.message });
  }

  if (!normalizedPair) {
    logger.warn('MarketData: no data found', { target });
    return null;
  }

  // Safety validation
  const { safe, reason } = validatePair(normalizedPair);
  if (!safe) {
    logger.warn(`MarketData: pair failed safety check — ${reason}`, {
      pair: normalizedPair.symbol,
    });
    return null;
  }

  // Update candle cache
  updateCandle(normalizedPair.pairAddress, normalizedPair.price, normalizedPair.volume.m5);

  logger.debug('MarketData: fetched', {
    pair: normalizedPair.symbol,
    price: normalizedPair.price,
    liq: normalizedPair.liquidity.usd,
  });

  return normalizedPair;
}

/**
 * Fetches market data for multiple targets in parallel.
 * @param {Object[]} targets
 * @returns {Object[]} Array of valid normalized pairs
 */
async function fetchMultiple(targets) {
  const results = await Promise.allSettled(targets.map(t => fetchMarketData(t)));
  return results
    .filter(r => r.status === 'fulfilled' && r.value !== null)
    .map(r => r.value);
}

module.exports = { fetchMarketData, fetchMultiple, getCandles };

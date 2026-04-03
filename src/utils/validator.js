'use strict';

const config = require('./config');
const logger = require('./logger');

/**
 * Validates a token/pair for safety before trading.
 * Checks liquidity, volume, price impact and blacklists.
 */

const { minLiquidityUSD, minVolumeUSD, minMarketCapUSD, maxPriceImpactPct, blacklistedTokens } = config.filters;

/**
 * Checks whether a token pair is safe to trade.
 * @param {Object} pair - Pair data from Dexscreener
 * @returns {{ safe: boolean, reason: string|null }}
 */
function validatePair(pair) {
  const { baseToken, quoteToken, liquidity, volume, priceImpact, fdv } = pair;

  // Blacklist check
  const tokenAddresses = [baseToken?.address?.toLowerCase(), quoteToken?.address?.toLowerCase()];
  for (const addr of tokenAddresses) {
    if (addr && blacklistedTokens.map(t => t.toLowerCase()).includes(addr)) {
      return { safe: false, reason: `Token ${addr} is blacklisted` };
    }
  }

  // Liquidity check
  const liqUSD = liquidity?.usd ?? 0;
  if (liqUSD < minLiquidityUSD) {
    return {
      safe: false,
      reason: `Liquidity too low: $${liqUSD.toLocaleString()} < $${minLiquidityUSD.toLocaleString()} minimum`,
    };
  }

  // Volume check (24h)
  const vol24h = volume?.h24 ?? 0;
  if (vol24h < minVolumeUSD) {
    return {
      safe: false,
      reason: `24h volume too low: $${vol24h.toLocaleString()} < $${minVolumeUSD.toLocaleString()} minimum`,
    };
  }

  // Market cap / FDV check
  if (fdv && fdv < minMarketCapUSD) {
    return {
      safe: false,
      reason: `FDV too low: $${fdv.toLocaleString()} < $${minMarketCapUSD.toLocaleString()} minimum`,
    };
  }

  // Price impact check (if provided by aggregator)
  if (priceImpact !== undefined && priceImpact > maxPriceImpactPct) {
    return {
      safe: false,
      reason: `Price impact too high: ${priceImpact.toFixed(2)}% > ${maxPriceImpactPct}% maximum`,
    };
  }

  // Honeypot heuristic: if buy/sell tax embedded in pair data
  if (pair.buyTax > 10 || pair.sellTax > 10) {
    return {
      safe: false,
      reason: `Suspicious tax: buy=${pair.buyTax}% sell=${pair.sellTax}%`,
    };
  }

  return { safe: true, reason: null };
}

/**
 * Validates trade parameters before execution.
 * @param {Object} params - { size, price, balance }
 * @returns {{ valid: boolean, reason: string|null }}
 */
function validateTradeParams({ size, price, balance }) {
  if (!size || size <= 0) return { valid: false, reason: 'Trade size must be positive' };
  if (!price || price <= 0) return { valid: false, reason: 'Price must be positive' };
  if (size > balance) return { valid: false, reason: `Trade size $${size} exceeds balance $${balance}` };
  return { valid: true, reason: null };
}

module.exports = { validatePair, validateTradeParams };

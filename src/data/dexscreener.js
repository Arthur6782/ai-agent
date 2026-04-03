'use strict';

const axios = require('axios');
const logger = require('../utils/logger');

const BASE_URL = 'https://api.dexscreener.com/latest/dex';

// Simple in-memory rate limiter: max 1 req / 300ms
let lastCallTime = 0;
const MIN_INTERVAL_MS = 300;

async function rateLimitedGet(url) {
  const now = Date.now();
  const elapsed = now - lastCallTime;
  if (elapsed < MIN_INTERVAL_MS) {
    await new Promise(r => setTimeout(r, MIN_INTERVAL_MS - elapsed));
  }
  lastCallTime = Date.now();
  return axios.get(url, { timeout: 10000 });
}

/**
 * Fetch pair data by token address (works for Solana, EVM).
 * @param {string} tokenAddress
 * @returns {Object[]} array of pair objects
 */
async function getPairsByToken(tokenAddress) {
  try {
    const { data } = await rateLimitedGet(`${BASE_URL}/tokens/${tokenAddress}`);
    return data.pairs ?? [];
  } catch (err) {
    logger.error('Dexscreener: failed to fetch pairs by token', {
      token: tokenAddress,
      err: err.message,
    });
    return [];
  }
}

/**
 * Fetch specific pair by chain + pair address.
 * @param {string} chainId  e.g. 'solana', 'ethereum', 'bsc'
 * @param {string} pairAddress
 * @returns {Object|null} pair object
 */
async function getPairByAddress(chainId, pairAddress) {
  try {
    const { data } = await rateLimitedGet(`${BASE_URL}/pairs/${chainId}/${pairAddress}`);
    return data.pair ?? null;
  } catch (err) {
    logger.error('Dexscreener: failed to fetch pair by address', {
      chain: chainId,
      pair: pairAddress,
      err: err.message,
    });
    return null;
  }
}

/**
 * Search pairs by token name or symbol.
 * @param {string} query
 * @returns {Object[]}
 */
async function searchPairs(query) {
  try {
    const { data } = await rateLimitedGet(`${BASE_URL}/search/?q=${encodeURIComponent(query)}`);
    return data.pairs ?? [];
  } catch (err) {
    logger.error('Dexscreener: search failed', { query, err: err.message });
    return [];
  }
}

/**
 * Normalizes a Dexscreener pair object into the standard internal format.
 * @param {Object} pair - Raw Dexscreener pair
 * @returns {Object} Normalized pair
 */
function normalizePair(pair) {
  return {
    pairAddress: pair.pairAddress,
    chainId: pair.chainId,
    dexId: pair.dexId,
    symbol: `${pair.baseToken?.symbol}/${pair.quoteToken?.symbol}`,
    baseToken: pair.baseToken,
    quoteToken: pair.quoteToken,
    price: parseFloat(pair.priceUsd ?? 0),
    priceNative: parseFloat(pair.priceNative ?? 0),
    liquidity: {
      usd: pair.liquidity?.usd ?? 0,
      base: pair.liquidity?.base ?? 0,
      quote: pair.liquidity?.quote ?? 0,
    },
    volume: {
      h24: pair.volume?.h24 ?? 0,
      h6: pair.volume?.h6 ?? 0,
      h1: pair.volume?.h1 ?? 0,
      m5: pair.volume?.m5 ?? 0,
    },
    priceChange: {
      h24: pair.priceChange?.h24 ?? 0,
      h6: pair.priceChange?.h6 ?? 0,
      h1: pair.priceChange?.h1 ?? 0,
      m5: pair.priceChange?.m5 ?? 0,
    },
    txns: pair.txns ?? {},
    fdv: pair.fdv ?? 0,
    url: pair.url,
    fetchedAt: Date.now(),
  };
}

module.exports = { getPairsByToken, getPairByAddress, searchPairs, normalizePair };

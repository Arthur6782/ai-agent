'use strict';

const axios = require('axios');
const logger = require('../utils/logger');

// Jupiter V6 API (Solana)
const JUPITER_PRICE_API = 'https://price.jup.ag/v4/price';
const JUPITER_QUOTE_API = 'https://quote-api.jup.ag/v6/quote';

/**
 * Fetch price(s) from Jupiter Price API.
 * @param {string|string[]} mintAddresses - Token mint address(es)
 * @param {string} vsToken - Quote token mint (default: USDC)
 * @returns {Object} map of mintAddress -> price data
 */
async function getPrices(mintAddresses, vsToken = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v') {
  const ids = Array.isArray(mintAddresses) ? mintAddresses.join(',') : mintAddresses;
  try {
    const { data } = await axios.get(JUPITER_PRICE_API, {
      params: { ids, vsToken },
      timeout: 8000,
    });
    return data.data ?? {};
  } catch (err) {
    logger.error('Jupiter: failed to fetch prices', { err: err.message });
    return {};
  }
}

/**
 * Get a quote from Jupiter for a potential swap.
 * Useful for estimating price impact before executing.
 * @param {Object} params
 * @param {string} params.inputMint - Input token mint
 * @param {string} params.outputMint - Output token mint
 * @param {number} params.amount - Amount in lamports/smallest unit
 * @param {number} params.slippageBps - Slippage in basis points (default 50 = 0.5%)
 * @returns {Object|null} Quote response
 */
async function getQuote({ inputMint, outputMint, amount, slippageBps = 50 }) {
  try {
    const { data } = await axios.get(JUPITER_QUOTE_API, {
      params: { inputMint, outputMint, amount, slippageBps },
      timeout: 10000,
    });
    return data;
  } catch (err) {
    logger.error('Jupiter: failed to fetch quote', {
      inputMint,
      outputMint,
      err: err.message,
    });
    return null;
  }
}

/**
 * Normalizes Jupiter price data into standard internal format.
 * @param {string} mintAddress
 * @param {Object} jupiterPriceData - Single token from Jupiter /price response
 * @returns {Object}
 */
function normalizeJupiterPrice(mintAddress, jupiterPriceData) {
  return {
    pairAddress: mintAddress,
    chainId: 'solana',
    dexId: 'jupiter',
    symbol: `${jupiterPriceData.mintSymbol}/USDC`,
    baseToken: { address: mintAddress, symbol: jupiterPriceData.mintSymbol },
    quoteToken: { symbol: 'USDC' },
    price: jupiterPriceData.price ?? 0,
    priceNative: jupiterPriceData.price ?? 0,
    liquidity: { usd: 0, base: 0, quote: 0 }, // Jupiter price API doesn't include liquidity
    volume: { h24: 0, h6: 0, h1: 0, m5: 0 },
    priceChange: { h24: 0, h6: 0, h1: 0, m5: 0 },
    fdv: 0,
    fetchedAt: Date.now(),
  };
}

module.exports = { getPrices, getQuote, normalizeJupiterPrice };

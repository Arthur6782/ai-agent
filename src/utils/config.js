'use strict';

const fs = require('fs');
const path = require('path');
require('dotenv').config();

// Load default config
const defaultConfig = JSON.parse(
  fs.readFileSync(path.join(__dirname, '../../config/default.json'), 'utf-8')
);

// Deep merge two objects
function deepMerge(target, source) {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      result[key] = deepMerge(target[key] || {}, source[key]);
    } else {
      result[key] = source[key];
    }
  }
  return result;
}

// Build config from defaults + env overrides
function buildConfig() {
  const cfg = deepMerge({}, defaultConfig);

  // Override from environment variables
  if (process.env.BOT_MODE) cfg.bot.mode = process.env.BOT_MODE;
  if (process.env.BOT_INTERVAL) cfg.bot.interval = parseInt(process.env.BOT_INTERVAL);
  if (process.env.MAX_RISK_PER_TRADE) cfg.risk.maxRiskPerTrade = parseFloat(process.env.MAX_RISK_PER_TRADE);
  if (process.env.PAPER_BALANCE) cfg.wallet.paperBalance = parseFloat(process.env.PAPER_BALANCE);
  if (process.env.MIN_LIQUIDITY_USD) cfg.filters.minLiquidityUSD = parseFloat(process.env.MIN_LIQUIDITY_USD);
  if (process.env.LOG_LEVEL) cfg.logging.level = process.env.LOG_LEVEL;
  if (process.env.RPC_URL) cfg.wallet.rpcUrl = process.env.RPC_URL;
  if (process.env.WALLET_PRIVATE_KEY) cfg.wallet.privateKey = process.env.WALLET_PRIVATE_KEY;

  // CLI arg override: --mode=paper|live
  const modeArg = process.argv.find(a => a.startsWith('--mode='));
  if (modeArg) cfg.bot.mode = modeArg.split('=')[1];

  return cfg;
}

const config = buildConfig();

module.exports = config;

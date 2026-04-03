'use strict';

const config = require('../utils/config');
const logger = require('../utils/logger');

const { cooldownAfterLoss } = config.risk;

// Per-pair cooldown registry: { [pairAddress]: { until: timestamp, reason: string } }
const cooldownRegistry = {};

// Global cooldown after hitting max consecutive losses
let globalCooldownUntil = 0;

/**
 * Activates a cooldown for a specific pair (e.g., after a losing trade).
 * @param {string} pairAddress
 * @param {number} durationMs - How long to cool down (ms). Defaults to config value.
 * @param {string} reason
 */
function activateCooldown(pairAddress, durationMs = cooldownAfterLoss * 1000, reason = 'Loss cooldown') {
  const until = Date.now() + durationMs;
  cooldownRegistry[pairAddress] = { until, reason };
  logger.risk(`Cooldown activated for ${pairAddress}`, {
    durationSec: durationMs / 1000,
    reason,
    until: new Date(until).toISOString(),
  });
}

/**
 * Activates a global cooldown (blocks ALL pairs).
 * @param {number} durationMs
 * @param {string} reason
 */
function activateGlobalCooldown(durationMs = cooldownAfterLoss * 2 * 1000, reason = 'Max losses reached') {
  globalCooldownUntil = Date.now() + durationMs;
  logger.risk(`GLOBAL cooldown activated`, {
    durationSec: durationMs / 1000,
    reason,
    until: new Date(globalCooldownUntil).toISOString(),
  });
}

/**
 * Checks whether trading is currently allowed for a pair.
 * @param {string} pairAddress
 * @returns {{ allowed: boolean, reason: string|null, remainingSec: number }}
 */
function isCoolingDown(pairAddress) {
  const now = Date.now();

  // Check global cooldown first
  if (now < globalCooldownUntil) {
    const remainingSec = Math.ceil((globalCooldownUntil - now) / 1000);
    return {
      allowed: false,
      reason: 'Global cooldown active',
      remainingSec,
    };
  }

  // Check pair-specific cooldown
  const cd = cooldownRegistry[pairAddress];
  if (cd && now < cd.until) {
    const remainingSec = Math.ceil((cd.until - now) / 1000);
    return {
      allowed: false,
      reason: cd.reason,
      remainingSec,
    };
  }

  return { allowed: true, reason: null, remainingSec: 0 };
}

/**
 * Clears cooldown for a pair (e.g., after manual override).
 * @param {string} pairAddress
 */
function clearCooldown(pairAddress) {
  delete cooldownRegistry[pairAddress];
  logger.info(`Cooldown cleared for ${pairAddress}`);
}

/**
 * Returns a summary of all active cooldowns.
 * @returns {Object[]}
 */
function getActiveCooldowns() {
  const now = Date.now();
  const active = [];

  if (now < globalCooldownUntil) {
    active.push({
      pair: 'GLOBAL',
      remainingSec: Math.ceil((globalCooldownUntil - now) / 1000),
      reason: 'Global cooldown',
    });
  }

  for (const [pair, cd] of Object.entries(cooldownRegistry)) {
    if (now < cd.until) {
      active.push({
        pair,
        remainingSec: Math.ceil((cd.until - now) / 1000),
        reason: cd.reason,
      });
    }
  }

  return active;
}

module.exports = {
  activateCooldown,
  activateGlobalCooldown,
  isCoolingDown,
  clearCooldown,
  getActiveCooldowns,
};

'use strict';

const fs = require('fs');
const path = require('path');
const { createObjectCsvWriter } = require('csv-writer');
const config = require('./config');
const logger = require('./logger');

const JSON_PATH = path.resolve(config.journal.path);
const CSV_PATH = path.resolve(config.journal.csvPath);

// Ensure journal directory exists
const journalDir = path.dirname(JSON_PATH);
if (!fs.existsSync(journalDir)) fs.mkdirSync(journalDir, { recursive: true });

// Initialize JSON store
function loadTrades() {
  if (!fs.existsSync(JSON_PATH)) return [];
  try {
    return JSON.parse(fs.readFileSync(JSON_PATH, 'utf-8'));
  } catch {
    return [];
  }
}

function saveTrades(trades) {
  fs.writeFileSync(JSON_PATH, JSON.stringify(trades, null, 2));
}

// CSV writer instance (append mode)
const csvWriter = createObjectCsvWriter({
  path: CSV_PATH,
  header: [
    { id: 'id', title: 'ID' },
    { id: 'timestamp', title: 'TIMESTAMP' },
    { id: 'pair', title: 'PAIR' },
    { id: 'side', title: 'SIDE' },
    { id: 'entryPrice', title: 'ENTRY_PRICE' },
    { id: 'exitPrice', title: 'EXIT_PRICE' },
    { id: 'size', title: 'SIZE_USD' },
    { id: 'stopLoss', title: 'STOP_LOSS' },
    { id: 'takeProfit', title: 'TAKE_PROFIT' },
    { id: 'pnl', title: 'PNL_USD' },
    { id: 'pnlPct', title: 'PNL_PCT' },
    { id: 'status', title: 'STATUS' },
    { id: 'entryReason', title: 'ENTRY_REASON' },
    { id: 'exitReason', title: 'EXIT_REASON' },
    { id: 'mode', title: 'MODE' },
  ],
  append: true,
});

/**
 * Records a new trade entry in the journal.
 */
function recordTrade(trade) {
  if (!config.journal.enabled) return;

  const trades = loadTrades();
  trades.push(trade);
  saveTrades(trades);

  // Append to CSV (only closed trades with full data)
  if (trade.status === 'closed') {
    csvWriter.writeRecords([trade]).catch(err => {
      logger.error('Failed to write trade to CSV', { err: err.message });
    });
  }

  logger.trade(trade.status === 'open' ? 'OPENED' : 'CLOSED', {
    id: trade.id,
    pair: trade.pair,
    side: trade.side,
    pnl: trade.pnl,
  });
}

/**
 * Updates an existing trade record (e.g., on close).
 */
function updateTrade(id, updates) {
  if (!config.journal.enabled) return;

  const trades = loadTrades();
  const idx = trades.findIndex(t => t.id === id);
  if (idx === -1) {
    logger.warn(`Journal: trade ${id} not found for update`);
    return;
  }

  trades[idx] = { ...trades[idx], ...updates };
  saveTrades(trades);

  if (trades[idx].status === 'closed') {
    csvWriter.writeRecords([trades[idx]]).catch(err => {
      logger.error('Failed to write trade CSV update', { err: err.message });
    });
  }
}

/**
 * Returns performance summary from journal.
 */
function getStats() {
  const trades = loadTrades();
  const closed = trades.filter(t => t.status === 'closed');

  if (closed.length === 0) {
    return { totalTrades: 0, wins: 0, losses: 0, winRate: 0, totalPnl: 0, avgPnl: 0 };
  }

  const wins = closed.filter(t => t.pnl > 0).length;
  const losses = closed.filter(t => t.pnl <= 0).length;
  const totalPnl = closed.reduce((sum, t) => sum + (t.pnl || 0), 0);

  return {
    totalTrades: closed.length,
    wins,
    losses,
    winRate: ((wins / closed.length) * 100).toFixed(1),
    totalPnl: totalPnl.toFixed(2),
    avgPnl: (totalPnl / closed.length).toFixed(2),
    bestTrade: Math.max(...closed.map(t => t.pnl || 0)).toFixed(2),
    worstTrade: Math.min(...closed.map(t => t.pnl || 0)).toFixed(2),
  };
}

/**
 * Returns all open trades from journal.
 */
function getOpenTrades() {
  return loadTrades().filter(t => t.status === 'open');
}

module.exports = { recordTrade, updateTrade, getStats, getOpenTrades, loadTrades };

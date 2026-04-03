#!/usr/bin/env node
'use strict';

/**
 * CLI Interface for the Crypto Trading Bot
 * Usage: node src/cli/interface.js [command] [options]
 */

const { Command } = require('commander');
const Table = require('cli-table3');
const chalk = require('chalk');

const config = require('../utils/config');
const { getStats, loadTrades, getOpenTrades } = require('../utils/journal');
const { getActiveCooldowns } = require('../risk/cooldown');
const { getState: getPaperState } = require('../execution/paperTrade');
const { getRiskState } = require('../risk/riskManager');

const program = new Command();

program
  .name('trading-bot')
  .description('SMC Crypto Trading Bot CLI')
  .version('1.0.0');

// ─── COMMAND: start ──────────────────────────────────────────────────────────
program
  .command('start')
  .description('Start the trading bot')
  .option('-m, --mode <mode>', 'Trading mode: paper | live', 'paper')
  .option('-i, --interval <seconds>', 'Polling interval in seconds', '30')
  .action((opts) => {
    process.env.BOT_MODE = opts.mode;
    process.env.BOT_INTERVAL = opts.interval;

    console.log(chalk.cyan(`\nStarting bot in ${chalk.bold(opts.mode.toUpperCase())} mode...\n`));

    // Dynamically require bot to pick up env overrides
    const { start } = require('../bot');
    start().catch(err => {
      console.error(chalk.red('Failed to start bot:'), err.message);
      process.exit(1);
    });
  });

// ─── COMMAND: status ─────────────────────────────────────────────────────────
program
  .command('status')
  .description('Show current bot status and open trades')
  .action(() => {
    const paper = getPaperState();
    const risk = getRiskState();
    const stats = getStats();
    const openTrades = getOpenTrades();
    const cooldowns = getActiveCooldowns();

    // ── Account Overview ──
    console.log('\n' + chalk.bold.cyan('═══ ACCOUNT OVERVIEW ═══'));
    const accountTable = new Table({ style: { head: ['cyan'] } });
    accountTable.push(
      [chalk.gray('Balance'), chalk.green(`$${paper.balance.toFixed(2)}`)],
      [chalk.gray('Total PnL'), colorPnl(paper.totalPnl)],
      [chalk.gray('Return'), colorPnl(parseFloat(paper.returnPct))],
      [chalk.gray('Mode'), chalk.yellow(config.bot.mode.toUpperCase())],
      [chalk.gray('Open Trades'), paper.openTradesCount],
    );
    console.log(accountTable.toString());

    // ── Performance ──
    console.log('\n' + chalk.bold.cyan('═══ PERFORMANCE ═══'));
    const perfTable = new Table({ style: { head: ['cyan'] } });
    perfTable.push(
      [chalk.gray('Total Closed'), stats.totalTrades ?? 0],
      [chalk.gray('Wins'), chalk.green(stats.wins ?? 0)],
      [chalk.gray('Losses'), chalk.red(stats.losses ?? 0)],
      [chalk.gray('Win Rate'), `${stats.winRate ?? 0}%`],
      [chalk.gray('Avg PnL'), colorPnl(parseFloat(stats.avgPnl ?? 0))],
      [chalk.gray('Best Trade'), chalk.green(`$${stats.bestTrade ?? 0}`)],
      [chalk.gray('Worst Trade'), chalk.red(`$${stats.worstTrade ?? 0}`)],
    );
    console.log(perfTable.toString());

    // ── Open Trades ──
    if (openTrades.length > 0) {
      console.log('\n' + chalk.bold.cyan('═══ OPEN TRADES ═══'));
      const tradeTable = new Table({
        head: ['ID', 'Pair', 'Side', 'Entry', 'SL', 'TP', 'Size', 'Reason'],
        style: { head: ['cyan'] },
        colWidths: [14, 14, 6, 12, 12, 12, 10, 30],
        wordWrap: true,
      });
      for (const t of openTrades) {
        tradeTable.push([
          chalk.gray(t.id),
          chalk.white(t.pair),
          t.side === 'buy' ? chalk.green('BUY') : chalk.red('SELL'),
          t.entryPrice.toFixed(6),
          chalk.red(t.stopLoss.toFixed(6)),
          chalk.green(t.takeProfit.toFixed(6)),
          `$${t.sizeUSD.toFixed(2)}`,
          chalk.gray(t.entryReason.slice(0, 40)),
        ]);
      }
      console.log(tradeTable.toString());
    } else {
      console.log('\n' + chalk.gray('No open trades.'));
    }

    // ── Cooldowns ──
    if (cooldowns.length > 0) {
      console.log('\n' + chalk.bold.yellow('═══ ACTIVE COOLDOWNS ═══'));
      for (const cd of cooldowns) {
        console.log(chalk.yellow(`  ⏳ ${cd.pair}: ${cd.remainingSec}s remaining — ${cd.reason}`));
      }
    }

    // ── Risk State ──
    console.log('\n' + chalk.bold.cyan('═══ RISK STATE ═══'));
    const riskTable = new Table({ style: { head: ['cyan'] } });
    riskTable.push(
      [chalk.gray('Daily PnL'), colorPnl(risk.dailyPnl)],
      [chalk.gray('Consecutive Losses'), risk.consecutiveLosses > 0 ? chalk.red(risk.consecutiveLosses) : chalk.green(0)],
    );
    console.log(riskTable.toString());
    console.log();
  });

// ─── COMMAND: journal ─────────────────────────────────────────────────────────
program
  .command('journal')
  .description('Show trade journal (last N trades)')
  .option('-n, --count <number>', 'Number of trades to show', '20')
  .option('--all', 'Show all trades', false)
  .action((opts) => {
    const trades = loadTrades();
    const closed = trades.filter(t => t.status === 'closed');
    const count = opts.all ? closed.length : parseInt(opts.count);
    const recent = closed.slice(-count);

    if (recent.length === 0) {
      console.log(chalk.gray('\nNo closed trades in journal.\n'));
      return;
    }

    console.log('\n' + chalk.bold.cyan(`═══ TRADE JOURNAL (last ${recent.length}) ═══`));
    const table = new Table({
      head: ['#', 'Pair', 'Side', 'Entry', 'Exit', 'PnL', 'PnL%', 'Exit Reason'],
      style: { head: ['cyan'] },
      colWidths: [4, 14, 6, 12, 12, 10, 8, 25],
      wordWrap: true,
    });

    recent.forEach((t, i) => {
      table.push([
        chalk.gray(i + 1),
        chalk.white(t.pair),
        t.side === 'buy' ? chalk.green('BUY') : chalk.red('SELL'),
        t.entryPrice?.toFixed?.(6) ?? '-',
        t.exitPrice?.toFixed?.(6) ?? '-',
        colorPnl(t.pnl),
        colorPnl(t.pnlPct, '%'),
        chalk.gray((t.exitReason ?? '').slice(0, 30)),
      ]);
    });
    console.log(table.toString());
    console.log();
  });

// ─── COMMAND: config ──────────────────────────────────────────────────────────
program
  .command('config')
  .description('Show active configuration')
  .action(() => {
    console.log('\n' + chalk.bold.cyan('═══ ACTIVE CONFIGURATION ═══'));
    const safe = JSON.parse(JSON.stringify(config));
    if (safe.wallet?.privateKey) safe.wallet.privateKey = '***hidden***';
    console.log(JSON.stringify(safe, null, 2));
    console.log();
  });

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function colorPnl(value, suffix = '') {
  if (value === null || value === undefined) return chalk.gray('-');
  const num = parseFloat(value);
  const str = `${num >= 0 ? '+' : ''}${num.toFixed(2)}${suffix}`;
  return num >= 0 ? chalk.green(str) : chalk.red(str);
}

// ─── PARSE ───────────────────────────────────────────────────────────────────
program.parse(process.argv);

// Default: show help if no command
if (process.argv.length < 3) {
  program.help();
}

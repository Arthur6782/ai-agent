'use strict';

const winston = require('winston');
const path = require('path');
const fs = require('fs');
const config = require('./config');

// Ensure logs directory exists
const logDir = path.dirname(config.logging.file);
if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });

// Custom format for console: colorized, compact
const consoleFormat = winston.format.combine(
  winston.format.timestamp({ format: 'HH:mm:ss' }),
  winston.format.colorize(),
  winston.format.printf(({ timestamp, level, message, ...meta }) => {
    const metaStr = Object.keys(meta).length ? ' ' + JSON.stringify(meta) : '';
    return `[${timestamp}] ${level}: ${message}${metaStr}`;
  })
);

// File format: full JSON with timestamp
const fileFormat = winston.format.combine(
  winston.format.timestamp(),
  winston.format.json()
);

const logger = winston.createLogger({
  level: config.logging.level,
  transports: [
    new winston.transports.Console({ format: consoleFormat }),
    new winston.transports.File({
      filename: config.logging.file,
      format: fileFormat,
      maxsize: 10 * 1024 * 1024, // 10MB
      maxFiles: config.logging.maxFiles,
    }),
  ],
});

// Convenience method for trade-specific events
logger.trade = (action, data) => {
  logger.info(`[TRADE] ${action}`, data);
};

logger.signal = (type, data) => {
  logger.info(`[SIGNAL] ${type}`, data);
};

logger.risk = (event, data) => {
  logger.warn(`[RISK] ${event}`, data);
};

module.exports = logger;

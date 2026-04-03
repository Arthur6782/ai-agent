"""
Configuration settings for the Crypto Token Analyzer.
API keys and endpoints for data sources.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# API Keys (set via environment variables)
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")
DEXSCREENER_API_KEY = os.getenv("DEXSCREENER_API_KEY", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# API Endpoints
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
DEXSCREENER_BASE_URL = "https://api.dexscreener.com/latest"
ETHERSCAN_BASE_URL = "https://api.etherscan.io/api"
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
DEFILLAMA_BASE_URL = "https://api.llama.fi"

# Analysis Thresholds
MIN_SCORE_THRESHOLD = 7
MAX_WALLET_CONCENTRATION_PCT = 25.0
MIN_LIQUIDITY_USD = 50_000
MAX_RECENT_PUMP_PCT = 100.0
MIN_VOLUME_INCREASE_PCT = 50.0

# Market Cap Categories (USD)
MICRO_CAP_MAX = 10_000_000
LOW_CAP_MAX = 50_000_000
MID_CAP_MAX = 250_000_000

# Smart Money Detection
WHALE_THRESHOLD_USD = 100_000
SMART_MONEY_MIN_TXNS = 3

# Scoring Weights
SCORING_WEIGHTS = {
    "narrative_strength": 0.25,
    "smart_money_activity": 0.25,
    "risk_level": 0.25,
    "entry_timing": 0.25,
}

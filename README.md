# Crypto Token Analyzer

Elite token discovery and analysis engine that identifies high-probability tokens with asymmetric upside before they become mainstream.

## Architecture

```
main.py                  # CLI entry point
src/
  market_context.py      # Market condition & narrative detection
  token_discovery.py     # Multi-source token discovery (CoinGecko, DEXScreener)
  token_filter.py        # Strict filtering: rejects pumps, scams, dead tokens
  fundamental_analysis.py # Narrative, team, utility, community scoring
  smart_money.py         # Whale tracking, wallet concentration, on-chain signals
  technical_analysis.py  # SMC-based: liquidity zones, BOS, supply/demand
  risk_analysis.py       # Liquidity risk, rug pull detection, tokenomics
  scoring.py             # Composite scoring engine (threshold: 7/10)
  display.py             # Rich terminal output
config/
  settings.py            # Thresholds, API endpoints, scoring weights
tests/                   # Unit tests for all modules
```

## Usage

```bash
# Full market scan - discover and analyze tokens
python main.py

# Analyze a specific token
python main.py --token render-token --symbol RNDR --narrative AI

# Focus on a specific narrative
python main.py --narrative AI DePIN

# Market context only
python main.py --market-only

# Limit analysis depth
python main.py --max-tokens 5
```

## Scoring System

Each token is scored 1-10 across four dimensions (equal weight):
- **Narrative Strength** - alignment with dominant market narratives
- **Smart Money Activity** - whale accumulation, wallet distribution
- **Risk Level** - liquidity, rug pull potential, tokenomics
- **Entry Timing** - SMC-based entry quality (demand zones, BOS)

Only tokens scoring **>= 7** are recommended.

## Data Sources

- CoinGecko (trending, market data, fundamentals)
- DEXScreener (new pairs, gainers, liquidity)
- Etherscan (on-chain analysis, contract verification)
- Alternative.me (Fear & Greed Index)
- DefiLlama (TVL data)

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Add your API keys to .env
python main.py
```

## Strict Rules

- Never recommends overhyped tokens
- Never chases pumps (>100% 24h filtered out)
- Rejects scam-pattern names
- Prioritizes 2-10x opportunities, not small gains
- Sniper mentality: entry at demand zones, not mid-range

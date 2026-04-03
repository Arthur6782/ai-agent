"""
Market Context Analyzer
Identifies current market conditions and dominant narratives.
"""

import requests
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from config.settings import COINGECKO_BASE_URL, DEFILLAMA_BASE_URL


class MarketCondition(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"


@dataclass
class MarketContext:
    condition: MarketCondition
    btc_dominance: float
    total_market_cap: float
    market_cap_change_24h: float
    fear_greed_index: Optional[int] = None
    dominant_narratives: list[str] = field(default_factory=list)
    trending_categories: list[str] = field(default_factory=list)


class MarketContextAnalyzer:
    """Analyzes overall crypto market conditions to guide token discovery."""

    NARRATIVE_KEYWORDS = {
        "AI": ["artificial intelligence", "ai", "machine learning", "gpt", "llm", "neural"],
        "DePIN": ["depin", "decentralized physical", "iot", "sensor", "wireless"],
        "RWA": ["real world asset", "rwa", "tokenized", "treasury", "bond"],
        "Meme": ["meme", "doge", "pepe", "shib", "floki"],
        "DeFi": ["defi", "lending", "dex", "yield", "amm", "liquidity"],
        "Gaming": ["gaming", "gamefi", "metaverse", "nft game", "play to earn"],
        "L2/Scaling": ["layer 2", "l2", "rollup", "zk", "optimistic", "scaling"],
        "LST/LSD": ["liquid staking", "lst", "lsd", "restaking", "eigenlayer"],
        "SocialFi": ["socialfi", "social", "friend.tech", "lens", "farcaster"],
        "Modular": ["modular", "data availability", "celestia", "da layer"],
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def get_market_condition(self) -> MarketContext:
        """Determine overall market condition from global data."""
        global_data = self._fetch_global_data()
        fear_greed = self._fetch_fear_greed_index()
        trending = self._fetch_trending_categories()
        narratives = self._identify_narratives(trending)

        mc_change = global_data.get("market_cap_change_percentage_24h_usd", 0)
        if mc_change > 3:
            condition = MarketCondition.BULLISH
        elif mc_change < -3:
            condition = MarketCondition.BEARISH
        else:
            condition = MarketCondition.RANGING

        return MarketContext(
            condition=condition,
            btc_dominance=global_data.get("market_cap_percentage", {}).get("btc", 0),
            total_market_cap=global_data.get("total_market_cap", {}).get("usd", 0),
            market_cap_change_24h=mc_change,
            fear_greed_index=fear_greed,
            dominant_narratives=narratives,
            trending_categories=trending,
        )

    def _fetch_global_data(self) -> dict:
        """Fetch global market data from CoinGecko."""
        try:
            resp = self.session.get(f"{COINGECKO_BASE_URL}/global", timeout=10)
            resp.raise_for_status()
            return resp.json().get("data", {})
        except requests.RequestException:
            return {}

    def _fetch_fear_greed_index(self) -> Optional[int]:
        """Fetch crypto fear & greed index."""
        try:
            resp = self.session.get(
                "https://api.alternative.me/fng/?limit=1", timeout=10
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return int(data[0].get("value", 0))
        except (requests.RequestException, ValueError, IndexError):
            pass
        return None

    def _fetch_trending_categories(self) -> list[str]:
        """Fetch trending categories from CoinGecko."""
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE_URL}/search/trending", timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            categories = []
            for cat in data.get("categories", []):
                name = cat.get("item", {}).get("name", "")
                if name:
                    categories.append(name)
            return categories[:10]
        except requests.RequestException:
            return []

    def _identify_narratives(self, trending_categories: list[str]) -> list[str]:
        """Identify dominant narratives from trending data."""
        active_narratives = []
        combined_text = " ".join(trending_categories).lower()

        for narrative, keywords in self.NARRATIVE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in combined_text:
                    active_narratives.append(narrative)
                    break

        return active_narratives if active_narratives else ["DeFi", "AI"]

    def _fetch_defi_tvl_changes(self) -> dict:
        """Fetch DeFi TVL data from DefiLlama to identify growing protocols."""
        try:
            resp = self.session.get(f"{DEFILLAMA_BASE_URL}/protocols", timeout=10)
            resp.raise_for_status()
            protocols = resp.json()
            growing = {}
            for p in protocols[:100]:
                name = p.get("name", "")
                change_1d = p.get("change_1d", 0)
                if change_1d and change_1d > 10:
                    growing[name] = change_1d
            return growing
        except requests.RequestException:
            return {}

"""
Token Discovery Engine
Finds early-stage tokens gaining traction but not yet overextended.
"""

import requests
from dataclasses import dataclass, field
from typing import Optional

from config.settings import (
    COINGECKO_BASE_URL,
    DEXSCREENER_BASE_URL,
    MICRO_CAP_MAX,
    LOW_CAP_MAX,
    MIN_VOLUME_INCREASE_PCT,
)


@dataclass
class DiscoveredToken:
    name: str
    symbol: str
    contract_address: Optional[str] = None
    chain: str = "ethereum"
    market_cap: float = 0
    price: float = 0
    volume_24h: float = 0
    volume_change_24h: float = 0
    price_change_24h: float = 0
    price_change_7d: float = 0
    liquidity_usd: float = 0
    pair_address: Optional[str] = None
    dex: Optional[str] = None
    narratives: list[str] = field(default_factory=list)
    social_mentions: int = 0
    discovery_source: str = ""


class TokenDiscoveryEngine:
    """Discovers early-stage tokens with high potential across multiple sources."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def discover_tokens(self, narratives: list[str]) -> list[DiscoveredToken]:
        """Run full discovery pipeline and return candidate tokens."""
        candidates = []

        trending = self._discover_trending_coingecko()
        candidates.extend(trending)

        gainers = self._discover_dexscreener_gainers()
        candidates.extend(gainers)

        new_pairs = self._discover_new_pairs()
        candidates.extend(new_pairs)

        filtered = self._apply_initial_filters(candidates, narratives)

        seen = set()
        unique = []
        for token in filtered:
            key = (token.symbol.lower(), token.chain)
            if key not in seen:
                seen.add(key)
                unique.append(token)

        return unique

    def _discover_trending_coingecko(self) -> list[DiscoveredToken]:
        """Find trending tokens on CoinGecko (early social buzz indicator)."""
        tokens = []
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE_URL}/search/trending", timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("coins", []):
                coin = item.get("item", {})
                token = DiscoveredToken(
                    name=coin.get("name", ""),
                    symbol=coin.get("symbol", ""),
                    market_cap=coin.get("data", {}).get("market_cap", 0) or 0,
                    price=coin.get("data", {}).get("price", 0) or 0,
                    price_change_24h=coin.get("data", {}).get(
                        "price_change_percentage_24h", {}
                    ).get("usd", 0) or 0,
                    discovery_source="coingecko_trending",
                )
                tokens.append(token)
        except requests.RequestException:
            pass
        return tokens

    def _discover_dexscreener_gainers(self) -> list[DiscoveredToken]:
        """Find top gainers on DEXScreener with volume surge."""
        tokens = []
        try:
            resp = self.session.get(
                f"{DEXSCREENER_BASE_URL}/dex/tokens/trending", timeout=10
            )
            resp.raise_for_status()
            pairs = resp.json().get("pairs", []) or resp.json()
            if isinstance(pairs, list):
                for pair in pairs[:20]:
                    token = self._parse_dexscreener_pair(pair, "dexscreener_gainer")
                    if token:
                        tokens.append(token)
        except requests.RequestException:
            pass
        return tokens

    def _discover_new_pairs(self) -> list[DiscoveredToken]:
        """Find newly created trading pairs with growing volume."""
        tokens = []
        chains = ["ethereum", "solana", "bsc", "base", "arbitrum"]
        for chain in chains:
            try:
                resp = self.session.get(
                    f"{DEXSCREENER_BASE_URL}/dex/pairs/{chain}", timeout=10
                )
                resp.raise_for_status()
                pairs = resp.json().get("pairs", [])
                if isinstance(pairs, list):
                    for pair in pairs[:10]:
                        token = self._parse_dexscreener_pair(pair, f"new_pair_{chain}")
                        if token:
                            tokens.append(token)
            except requests.RequestException:
                continue
        return tokens

    def _parse_dexscreener_pair(
        self, pair: dict, source: str
    ) -> Optional[DiscoveredToken]:
        """Parse a DEXScreener pair into a DiscoveredToken."""
        try:
            base_token = pair.get("baseToken", {})
            liquidity = pair.get("liquidity", {})
            volume = pair.get("volume", {})
            price_change = pair.get("priceChange", {})

            return DiscoveredToken(
                name=base_token.get("name", "Unknown"),
                symbol=base_token.get("symbol", "???"),
                contract_address=base_token.get("address", ""),
                chain=pair.get("chainId", "ethereum"),
                market_cap=pair.get("fdv", 0) or 0,
                price=float(pair.get("priceUsd", 0) or 0),
                volume_24h=volume.get("h24", 0) or 0,
                price_change_24h=price_change.get("h24", 0) or 0,
                price_change_7d=price_change.get("d7", 0) or 0 if "d7" in price_change else 0,
                liquidity_usd=liquidity.get("usd", 0) or 0,
                pair_address=pair.get("pairAddress", ""),
                dex=pair.get("dexId", ""),
                discovery_source=source,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _apply_initial_filters(
        self, tokens: list[DiscoveredToken], narratives: list[str]
    ) -> list[DiscoveredToken]:
        """Apply initial filters to remove obviously bad tokens."""
        filtered = []
        for token in tokens:
            if token.market_cap > LOW_CAP_MAX and token.market_cap != 0:
                continue
            if token.price_change_24h > 100:
                continue
            if token.volume_24h < 1000 and token.discovery_source != "coingecko_trending":
                continue
            filtered.append(token)
        return filtered

    def search_by_narrative(self, narrative: str) -> list[DiscoveredToken]:
        """Search for tokens matching a specific narrative."""
        tokens = []
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE_URL}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "category": narrative.lower().replace(" ", "-"),
                    "order": "volume_desc",
                    "per_page": 20,
                    "page": 1,
                    "sparkline": False,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for coin in resp.json():
                token = DiscoveredToken(
                    name=coin.get("name", ""),
                    symbol=coin.get("symbol", "").upper(),
                    market_cap=coin.get("market_cap", 0) or 0,
                    price=coin.get("current_price", 0) or 0,
                    volume_24h=coin.get("total_volume", 0) or 0,
                    price_change_24h=coin.get("price_change_percentage_24h", 0) or 0,
                    price_change_7d=coin.get("price_change_percentage_7d_in_currency", 0) or 0,
                    discovery_source=f"narrative_{narrative}",
                )
                tokens.append(token)
        except requests.RequestException:
            pass
        return tokens

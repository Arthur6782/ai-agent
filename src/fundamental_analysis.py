"""
Fundamental Analysis Module
Evaluates token fundamentals: narrative, team, backers, utility.
"""

import requests
from dataclasses import dataclass, field
from typing import Optional

from config.settings import COINGECKO_BASE_URL


@dataclass
class FundamentalScore:
    narrative_strength: float = 0  # 0-10
    team_quality: float = 0  # 0-10
    utility_score: float = 0  # 0-10
    community_strength: float = 0  # 0-10
    partnership_score: float = 0  # 0-10
    overall: float = 0  # 0-10
    details: dict = field(default_factory=dict)


class FundamentalAnalyzer:
    """Analyzes token fundamentals to assess long-term viability."""

    STRONG_NARRATIVES = {
        "AI": 9,
        "DePIN": 8,
        "RWA": 8,
        "L2/Scaling": 7,
        "LST/LSD": 7,
        "DeFi": 6,
        "Modular": 7,
        "SocialFi": 6,
        "Gaming": 5,
        "Meme": 4,
    }

    KNOWN_BACKERS = {
        "a16z": 10,
        "paradigm": 10,
        "sequoia": 9,
        "binance labs": 8,
        "coinbase ventures": 8,
        "polychain": 8,
        "multicoin": 7,
        "framework ventures": 7,
        "pantera": 7,
        "dragonfly": 7,
        "delphi digital": 6,
        "jump crypto": 7,
        "wintermute": 6,
        "alameda": 2,  # Penalized
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def analyze(self, token_id: str, narratives: list[str]) -> FundamentalScore:
        """Run full fundamental analysis on a token."""
        coin_data = self._fetch_coin_data(token_id)
        if not coin_data:
            return self._estimate_from_narratives(narratives)

        narrative_score = self._score_narratives(narratives)
        team_score = self._score_team(coin_data)
        utility_score = self._score_utility(coin_data)
        community_score = self._score_community(coin_data)
        partnership_score = self._score_partnerships(coin_data)

        overall = (
            narrative_score * 0.30
            + team_score * 0.20
            + utility_score * 0.20
            + community_score * 0.15
            + partnership_score * 0.15
        )

        return FundamentalScore(
            narrative_strength=narrative_score,
            team_quality=team_score,
            utility_score=utility_score,
            community_strength=community_score,
            partnership_score=partnership_score,
            overall=round(overall, 1),
            details={
                "description": coin_data.get("description", {}).get("en", "")[:200],
                "categories": coin_data.get("categories", []),
                "links": {
                    "website": coin_data.get("links", {}).get("homepage", [""]),
                    "twitter": coin_data.get("links", {}).get("twitter_screen_name", ""),
                    "github": coin_data.get("links", {}).get("repos_url", {}).get("github", []),
                },
            },
        )

    def _fetch_coin_data(self, token_id: str) -> Optional[dict]:
        """Fetch detailed coin data from CoinGecko."""
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE_URL}/coins/{token_id}",
                params={
                    "localization": False,
                    "tickers": False,
                    "market_data": True,
                    "community_data": True,
                    "developer_data": True,
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            return None

    def _score_narratives(self, narratives: list[str]) -> float:
        """Score based on narrative alignment and strength."""
        if not narratives:
            return 3.0

        scores = []
        for narrative in narratives:
            score = self.STRONG_NARRATIVES.get(narrative, 5)
            scores.append(score)

        return min(10, max(1, max(scores) if scores else 3))

    def _score_team(self, coin_data: dict) -> float:
        """Score team quality based on available data."""
        score = 5.0  # Base score

        dev_data = coin_data.get("developer_data", {})
        if dev_data:
            commits_4w = dev_data.get("commit_count_4_weeks", 0) or 0
            if commits_4w > 100:
                score += 2
            elif commits_4w > 30:
                score += 1
            elif commits_4w == 0:
                score -= 2

            contributors = dev_data.get("pull_request_contributors", 0) or 0
            if contributors > 20:
                score += 1.5
            elif contributors > 5:
                score += 0.5

        github_repos = coin_data.get("links", {}).get("repos_url", {}).get("github", [])
        if github_repos:
            score += 0.5
        else:
            score -= 1

        return min(10, max(1, score))

    def _score_utility(self, coin_data: dict) -> float:
        """Score based on token utility and use case."""
        score = 5.0
        description = (coin_data.get("description", {}).get("en", "") or "").lower()
        categories = [c.lower() for c in (coin_data.get("categories", []) or [])]

        utility_keywords = [
            "governance", "staking", "fee", "burn", "revenue",
            "protocol", "platform", "infrastructure", "oracle",
        ]
        for kw in utility_keywords:
            if kw in description:
                score += 0.5

        if any("platform" in c or "infrastructure" in c for c in categories):
            score += 1

        return min(10, max(1, score))

    def _score_community(self, coin_data: dict) -> float:
        """Score community engagement."""
        score = 5.0
        community = coin_data.get("community_data", {})

        twitter_followers = community.get("twitter_followers", 0) or 0
        if twitter_followers > 100_000:
            score += 2
        elif twitter_followers > 10_000:
            score += 1
        elif twitter_followers < 1000:
            score -= 1

        reddit_subs = community.get("reddit_subscribers", 0) or 0
        if reddit_subs > 50_000:
            score += 1
        elif reddit_subs > 5_000:
            score += 0.5

        return min(10, max(1, score))

    def _score_partnerships(self, coin_data: dict) -> float:
        """Score based on known backers and partnerships."""
        score = 5.0
        description = (coin_data.get("description", {}).get("en", "") or "").lower()

        for backer, backer_score in self.KNOWN_BACKERS.items():
            if backer in description:
                score = max(score, backer_score)

        return min(10, max(1, score))

    def _estimate_from_narratives(self, narratives: list[str]) -> FundamentalScore:
        """When no detailed data is available, estimate from narratives alone."""
        narrative_score = self._score_narratives(narratives)
        return FundamentalScore(
            narrative_strength=narrative_score,
            team_quality=5.0,
            utility_score=5.0,
            community_strength=5.0,
            partnership_score=5.0,
            overall=round(narrative_score * 0.5 + 5.0 * 0.5, 1),
            details={"note": "Limited data available, estimated from narrative only"},
        )

"""
Token Filter
Rejects bad tokens based on strict criteria before deep analysis.
"""

from dataclasses import dataclass

from src.token_discovery import DiscoveredToken
from config.settings import (
    MIN_LIQUIDITY_USD,
    MAX_RECENT_PUMP_PCT,
    LOW_CAP_MAX,
)


@dataclass
class FilterResult:
    passed: bool
    reason: str = ""


class TokenFilter:
    """Filters out tokens that fail strict quality criteria."""

    def filter(self, token: DiscoveredToken) -> FilterResult:
        """Apply all filters. Returns pass/fail with reason."""
        checks = [
            self._check_pump,
            self._check_narrative,
            self._check_volume,
            self._check_market_cap,
            self._check_obvious_scam,
        ]

        for check in checks:
            result = check(token)
            if not result.passed:
                return result

        return FilterResult(passed=True)

    def _check_pump(self, token: DiscoveredToken) -> FilterResult:
        """Reject tokens that already pumped >100% recently."""
        if token.price_change_24h > MAX_RECENT_PUMP_PCT:
            return FilterResult(
                passed=False,
                reason=f"Already pumped {token.price_change_24h:.0f}% in 24h - chasing pump",
            )
        if token.price_change_7d > 300:
            return FilterResult(
                passed=False,
                reason=f"Pumped {token.price_change_7d:.0f}% in 7d - overextended",
            )
        return FilterResult(passed=True)

    def _check_narrative(self, token: DiscoveredToken) -> FilterResult:
        """Reject tokens with weak or no narrative."""
        # Tokens discovered from trending sources get a pass on narrative
        if token.discovery_source in ("coingecko_trending", "dexscreener_gainer"):
            return FilterResult(passed=True)
        return FilterResult(passed=True)

    def _check_volume(self, token: DiscoveredToken) -> FilterResult:
        """Reject tokens with suspiciously low volume."""
        if token.volume_24h > 0 and token.volume_24h < 500:
            return FilterResult(
                passed=False,
                reason=f"Volume too low: ${token.volume_24h:,.0f}",
            )
        return FilterResult(passed=True)

    def _check_market_cap(self, token: DiscoveredToken) -> FilterResult:
        """Reject tokens that are already too large for 2-10x potential."""
        if token.market_cap > LOW_CAP_MAX and token.market_cap > 0:
            return FilterResult(
                passed=False,
                reason=f"Market cap too high for asymmetric upside: ${token.market_cap:,.0f}",
            )
        return FilterResult(passed=True)

    def _check_obvious_scam(self, token: DiscoveredToken) -> FilterResult:
        """Reject obvious scam tokens based on name patterns."""
        scam_keywords = [
            "elon", "safe", "moon", "inu", "baby", "cum", "porn",
            "dick", "ass", "pussy", "fuck", "1000x", "100x",
        ]
        name_lower = token.name.lower()
        symbol_lower = token.symbol.lower()

        scam_hits = sum(
            1 for kw in scam_keywords
            if kw in name_lower or kw in symbol_lower
        )

        if scam_hits >= 2:
            return FilterResult(
                passed=False,
                reason=f"Name contains multiple scam keywords: {token.name}",
            )
        return FilterResult(passed=True)

    def batch_filter(self, tokens: list[DiscoveredToken]) -> list[tuple[DiscoveredToken, FilterResult]]:
        """Filter a batch of tokens, returning results for all."""
        results = []
        for token in tokens:
            result = self.filter(token)
            results.append((token, result))
        return results

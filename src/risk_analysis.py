"""
Risk Analysis Module
Evaluates liquidity risk, rug pull potential, and tokenomics.
"""

import requests
from dataclasses import dataclass, field
from typing import Optional

from config.settings import (
    MIN_LIQUIDITY_USD,
    MAX_WALLET_CONCENTRATION_PCT,
    ETHERSCAN_API_KEY,
    ETHERSCAN_BASE_URL,
)


@dataclass
class RiskScore:
    liquidity_risk: float = 0  # 0-10 (higher = safer)
    rug_pull_risk: float = 0  # 0-10 (higher = safer)
    tokenomics_risk: float = 0  # 0-10 (higher = safer)
    overall: float = 0  # 0-10 (higher = safer)
    red_flags: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class RiskAnalyzer:
    """Evaluates risk factors for token investment."""

    RUG_PULL_INDICATORS = [
        "honeypot",
        "mint function",
        "proxy contract",
        "hidden owner",
        "blacklist function",
        "transfer limit",
        "fee modification",
        "self destruct",
    ]

    def __init__(self):
        self.session = requests.Session()

    def analyze(
        self,
        contract_address: Optional[str] = None,
        chain: str = "ethereum",
        liquidity_usd: float = 0,
        market_cap: float = 0,
        volume_24h: float = 0,
        top_holders_pct: float = 0,
        price_change_24h: float = 0,
    ) -> RiskScore:
        """Run comprehensive risk analysis."""
        red_flags = []

        liquidity_score = self._assess_liquidity_risk(
            liquidity_usd, market_cap, volume_24h, red_flags
        )
        rug_score = self._assess_rug_pull_risk(
            contract_address, chain, top_holders_pct, red_flags
        )
        tokenomics_score = self._assess_tokenomics_risk(
            market_cap, volume_24h, price_change_24h, red_flags
        )

        overall = (
            liquidity_score * 0.35
            + rug_score * 0.40
            + tokenomics_score * 0.25
        )

        return RiskScore(
            liquidity_risk=round(liquidity_score, 1),
            rug_pull_risk=round(rug_score, 1),
            tokenomics_risk=round(tokenomics_score, 1),
            overall=round(overall, 1),
            red_flags=red_flags,
            details={
                "liquidity_usd": liquidity_usd,
                "market_cap": market_cap,
                "mc_to_liquidity_ratio": (
                    round(market_cap / liquidity_usd, 2) if liquidity_usd > 0 else 0
                ),
            },
        )

    def _assess_liquidity_risk(
        self,
        liquidity_usd: float,
        market_cap: float,
        volume_24h: float,
        red_flags: list[str],
    ) -> float:
        """Assess liquidity-related risks."""
        score = 5.0

        if liquidity_usd >= 1_000_000:
            score = 9.0
        elif liquidity_usd >= 500_000:
            score = 8.0
        elif liquidity_usd >= 100_000:
            score = 7.0
        elif liquidity_usd >= MIN_LIQUIDITY_USD:
            score = 6.0
        elif liquidity_usd > 0:
            score = 3.0
            red_flags.append(f"Low liquidity: ${liquidity_usd:,.0f}")
        else:
            score = 5.0  # Unknown

        if market_cap > 0 and liquidity_usd > 0:
            ratio = market_cap / liquidity_usd
            if ratio > 50:
                score -= 2
                red_flags.append(f"High MC/Liquidity ratio: {ratio:.0f}x")
            elif ratio > 20:
                score -= 1

        if volume_24h > 0 and liquidity_usd > 0:
            vol_liq_ratio = volume_24h / liquidity_usd
            if vol_liq_ratio < 0.01:
                score -= 1
                red_flags.append("Very low volume relative to liquidity")

        return min(10, max(1, score))

    def _assess_rug_pull_risk(
        self,
        contract_address: Optional[str],
        chain: str,
        top_holders_pct: float,
        red_flags: list[str],
    ) -> float:
        """Assess rug pull risk factors."""
        score = 6.0

        if top_holders_pct > 80:
            score -= 4
            red_flags.append(f"Extreme holder concentration: top 10 hold {top_holders_pct:.0f}%")
        elif top_holders_pct > 60:
            score -= 2
            red_flags.append(f"High holder concentration: top 10 hold {top_holders_pct:.0f}%")
        elif top_holders_pct > MAX_WALLET_CONCENTRATION_PCT:
            score -= 1
        elif top_holders_pct > 0:
            score += 2

        if contract_address and chain == "ethereum":
            contract_score = self._check_contract_safety(contract_address)
            score = (score + contract_score) / 2

        return min(10, max(1, score))

    def _check_contract_safety(self, contract_address: str) -> float:
        """Check contract for safety indicators."""
        score = 6.0

        if not ETHERSCAN_API_KEY:
            return score

        try:
            resp = self.session.get(
                ETHERSCAN_BASE_URL,
                params={
                    "module": "contract",
                    "action": "getsourcecode",
                    "address": contract_address,
                    "apikey": ETHERSCAN_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json().get("result", [])

            if result and isinstance(result, list) and result[0]:
                contract_info = result[0]

                if contract_info.get("ABI") == "Contract source code not verified":
                    score -= 3  # Unverified contract is a major red flag
                else:
                    score += 1

                source = (contract_info.get("SourceCode", "") or "").lower()
                for indicator in self.RUG_PULL_INDICATORS:
                    if indicator in source:
                        score -= 1

                if contract_info.get("Proxy") == "1":
                    score -= 1  # Proxy contracts can be upgraded maliciously

        except requests.RequestException:
            pass

        return min(10, max(1, score))

    def _assess_tokenomics_risk(
        self,
        market_cap: float,
        volume_24h: float,
        price_change_24h: float,
        red_flags: list[str],
    ) -> float:
        """Assess tokenomics-related risks."""
        score = 6.0

        if market_cap > 0 and volume_24h > 0:
            vol_mc_ratio = volume_24h / market_cap
            if vol_mc_ratio > 0.5:
                score += 1
            elif vol_mc_ratio < 0.01:
                score -= 1
                red_flags.append("Very low volume/MC ratio - potential dead token")

        if abs(price_change_24h) > 50:
            score -= 1
            if price_change_24h > 100:
                red_flags.append(f"Already pumped {price_change_24h:.0f}% in 24h - potential dump incoming")

        return min(10, max(1, score))

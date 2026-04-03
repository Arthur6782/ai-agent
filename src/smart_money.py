"""
On-Chain / Smart Money Analyzer
Tracks whale activity, wallet concentration, and smart money flows.
"""

import requests
from dataclasses import dataclass, field
from typing import Optional

from config.settings import (
    ETHERSCAN_API_KEY,
    ETHERSCAN_BASE_URL,
    WHALE_THRESHOLD_USD,
    MAX_WALLET_CONCENTRATION_PCT,
    SMART_MONEY_MIN_TXNS,
)


@dataclass
class WhaleActivity:
    address: str
    action: str  # "accumulating", "distributing", "holding"
    amount_usd: float
    token_amount: float
    timestamp: int = 0


@dataclass
class SmartMoneyScore:
    whale_accumulation: float = 0  # 0-10
    wallet_concentration_risk: float = 0  # 0-10 (higher = safer)
    unusual_activity: float = 0  # 0-10
    overall: float = 0  # 0-10
    whale_activities: list[WhaleActivity] = field(default_factory=list)
    top_holders_pct: float = 0
    unique_holders: int = 0
    details: dict = field(default_factory=dict)


class SmartMoneyAnalyzer:
    """Analyzes on-chain data to detect smart money movements."""

    KNOWN_SMART_MONEY = [
        "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance Hot Wallet
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Jump Trading
        "0xdbf5e9c5206d0db70a90108bf936da60221dc080",  # Wintermute
        "0xe8e33700b25ccc41bb2fd17e49f9a3c1b6e2b821",  # Alameda
    ]

    def __init__(self):
        self.session = requests.Session()

    def analyze(
        self,
        contract_address: Optional[str],
        chain: str = "ethereum",
        price: float = 0,
    ) -> SmartMoneyScore:
        """Run full smart money analysis for a token."""
        if not contract_address:
            return self._default_score()

        holder_data = self._analyze_holders(contract_address, chain)
        whale_data = self._detect_whale_activity(contract_address, chain, price)
        unusual = self._detect_unusual_activity(contract_address, chain)

        whale_score = self._score_whale_accumulation(whale_data)
        concentration_score = self._score_concentration(holder_data)
        unusual_score = self._score_unusual_activity(unusual)

        overall = (
            whale_score * 0.40
            + concentration_score * 0.35
            + unusual_score * 0.25
        )

        return SmartMoneyScore(
            whale_accumulation=whale_score,
            wallet_concentration_risk=concentration_score,
            unusual_activity=unusual_score,
            overall=round(overall, 1),
            whale_activities=whale_data,
            top_holders_pct=holder_data.get("top10_pct", 0),
            unique_holders=holder_data.get("unique_holders", 0),
            details={
                "chain": chain,
                "contract": contract_address,
                "analysis_note": holder_data.get("note", ""),
            },
        )

    def _analyze_holders(self, contract_address: str, chain: str) -> dict:
        """Analyze token holder distribution."""
        if chain != "ethereum" or not ETHERSCAN_API_KEY:
            return {"top10_pct": 0, "unique_holders": 0, "note": "Chain not supported for holder analysis"}

        try:
            resp = self.session.get(
                ETHERSCAN_BASE_URL,
                params={
                    "module": "token",
                    "action": "tokenholderlist",
                    "contractaddress": contract_address,
                    "page": 1,
                    "offset": 20,
                    "apikey": ETHERSCAN_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            holders = data.get("result", [])

            if not isinstance(holders, list) or not holders:
                return {"top10_pct": 0, "unique_holders": 0, "note": "No holder data available"}

            total_supply = sum(
                float(h.get("TokenHolderQuantity", 0)) for h in holders
            )
            if total_supply == 0:
                return {"top10_pct": 0, "unique_holders": len(holders), "note": "Zero supply detected"}

            top10_supply = sum(
                float(h.get("TokenHolderQuantity", 0)) for h in holders[:10]
            )
            top10_pct = (top10_supply / total_supply) * 100

            return {
                "top10_pct": round(top10_pct, 2),
                "unique_holders": len(holders),
                "note": "Top 20 holders analyzed",
            }
        except (requests.RequestException, ValueError):
            return {"top10_pct": 0, "unique_holders": 0, "note": "API error"}

    def _detect_whale_activity(
        self, contract_address: str, chain: str, price: float
    ) -> list[WhaleActivity]:
        """Detect recent whale transactions."""
        activities = []
        if chain != "ethereum" or not ETHERSCAN_API_KEY:
            return activities

        try:
            resp = self.session.get(
                ETHERSCAN_BASE_URL,
                params={
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": contract_address,
                    "page": 1,
                    "offset": 50,
                    "sort": "desc",
                    "apikey": ETHERSCAN_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            txns = resp.json().get("result", [])

            if not isinstance(txns, list):
                return activities

            for tx in txns:
                value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
                usd_value = value * price if price else 0

                if usd_value >= WHALE_THRESHOLD_USD or value > 1_000_000:
                    to_addr = tx.get("to", "").lower()
                    from_addr = tx.get("from", "").lower()

                    is_smart = (
                        to_addr in self.KNOWN_SMART_MONEY
                        or from_addr in self.KNOWN_SMART_MONEY
                    )

                    if to_addr in self.KNOWN_SMART_MONEY:
                        action = "distributing"
                    elif from_addr in self.KNOWN_SMART_MONEY:
                        action = "accumulating"
                    else:
                        action = "accumulating" if is_smart else "whale_transfer"

                    activities.append(
                        WhaleActivity(
                            address=to_addr,
                            action=action,
                            amount_usd=usd_value,
                            token_amount=value,
                            timestamp=int(tx.get("timeStamp", 0)),
                        )
                    )
        except (requests.RequestException, ValueError):
            pass

        return activities[:10]

    def _detect_unusual_activity(self, contract_address: str, chain: str) -> dict:
        """Detect unusual on-chain activity patterns."""
        if chain != "ethereum" or not ETHERSCAN_API_KEY:
            return {"score": 5, "note": "Chain not supported"}

        try:
            resp = self.session.get(
                ETHERSCAN_BASE_URL,
                params={
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": contract_address,
                    "page": 1,
                    "offset": 100,
                    "sort": "desc",
                    "apikey": ETHERSCAN_API_KEY,
                },
                timeout=10,
            )
            resp.raise_for_status()
            txns = resp.json().get("result", [])

            if not isinstance(txns, list):
                return {"score": 5, "note": "No transaction data"}

            unique_addresses = set()
            for tx in txns:
                unique_addresses.add(tx.get("to", ""))
                unique_addresses.add(tx.get("from", ""))

            tx_count = len(txns)
            addr_count = len(unique_addresses)

            if tx_count > 50 and addr_count > 30:
                return {"score": 8, "note": "High activity, many unique addresses"}
            elif tx_count > 20:
                return {"score": 6, "note": "Moderate activity"}
            else:
                return {"score": 4, "note": "Low activity"}

        except (requests.RequestException, ValueError):
            return {"score": 5, "note": "API error"}

    def _score_whale_accumulation(self, whale_data: list[WhaleActivity]) -> float:
        """Score whale accumulation activity."""
        if not whale_data:
            return 5.0

        accumulating = sum(1 for w in whale_data if w.action == "accumulating")
        distributing = sum(1 for w in whale_data if w.action == "distributing")

        if accumulating > distributing * 2:
            return min(10, 7 + accumulating)
        elif accumulating > distributing:
            return 6.0
        elif distributing > accumulating:
            return 3.0
        return 5.0

    def _score_concentration(self, holder_data: dict) -> float:
        """Score wallet concentration (higher score = safer distribution)."""
        top10_pct = holder_data.get("top10_pct", 0)

        if top10_pct == 0:
            return 5.0  # No data
        elif top10_pct > 80:
            return 2.0  # Extremely concentrated - high risk
        elif top10_pct > 60:
            return 4.0
        elif top10_pct > MAX_WALLET_CONCENTRATION_PCT:
            return 6.0
        elif top10_pct > 15:
            return 8.0
        else:
            return 9.0  # Well distributed

    def _score_unusual_activity(self, unusual: dict) -> float:
        """Score unusual activity detection."""
        return float(unusual.get("score", 5))

    def _default_score(self) -> SmartMoneyScore:
        """Return default score when no contract address is available."""
        return SmartMoneyScore(
            whale_accumulation=5.0,
            wallet_concentration_risk=5.0,
            unusual_activity=5.0,
            overall=5.0,
            details={"note": "No contract address available for analysis"},
        )

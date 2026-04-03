"""
Technical Analysis Module (SMC-Based)
Smart Money Concepts: liquidity zones, supply/demand, break of structure.
"""

import requests
import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from config.settings import COINGECKO_BASE_URL, DEXSCREENER_BASE_URL


@dataclass
class LiquidityZone:
    price_low: float
    price_high: float
    zone_type: str  # "demand", "supply"
    strength: float  # 0-10
    touched: int = 0  # Number of times price visited this zone


@dataclass
class StructureBreak:
    direction: str  # "bullish", "bearish"
    price_level: float
    timestamp: Optional[int] = None
    confirmed: bool = False


@dataclass
class TechnicalScore:
    trend: str  # "bullish", "bearish", "neutral"
    liquidity_zones: list[LiquidityZone] = field(default_factory=list)
    structure_breaks: list[StructureBreak] = field(default_factory=list)
    entry_zone_low: float = 0
    entry_zone_high: float = 0
    current_price: float = 0
    entry_quality: float = 0  # 0-10 (how good is current price for entry)
    overall: float = 0  # 0-10
    details: dict = field(default_factory=dict)


class TechnicalAnalyzer:
    """SMC-based technical analysis for optimal entry identification."""

    def __init__(self):
        self.session = requests.Session()

    def analyze(
        self,
        token_id: Optional[str] = None,
        contract_address: Optional[str] = None,
        chain: str = "ethereum",
        current_price: float = 0,
    ) -> TechnicalScore:
        """Run full SMC-based technical analysis."""
        prices = self._fetch_price_history(token_id, contract_address, chain)

        if not prices or len(prices) < 10:
            return self._default_score(current_price)

        closes = np.array([p[1] for p in prices])
        highs = np.array([p[2] for p in prices]) if len(prices[0]) > 2 else closes * 1.02
        lows = np.array([p[3] for p in prices]) if len(prices[0]) > 3 else closes * 0.98

        current = current_price if current_price else closes[-1]

        trend = self._determine_trend(closes)
        liquidity_zones = self._find_liquidity_zones(highs, lows, closes)
        structure_breaks = self._detect_break_of_structure(highs, lows)
        entry_zone = self._calculate_optimal_entry(
            liquidity_zones, current, trend
        )
        entry_quality = self._score_entry_quality(
            current, entry_zone, trend, liquidity_zones
        )

        overall = self._calculate_overall_score(
            trend, entry_quality, structure_breaks, liquidity_zones
        )

        return TechnicalScore(
            trend=trend,
            liquidity_zones=liquidity_zones,
            structure_breaks=structure_breaks,
            entry_zone_low=entry_zone[0],
            entry_zone_high=entry_zone[1],
            current_price=current,
            entry_quality=entry_quality,
            overall=round(overall, 1),
            details={
                "data_points": len(prices),
                "price_range": f"${min(closes):.6f} - ${max(closes):.6f}",
                "sma_20": float(np.mean(closes[-20:])) if len(closes) >= 20 else float(np.mean(closes)),
            },
        )

    def _fetch_price_history(
        self,
        token_id: Optional[str],
        contract_address: Optional[str],
        chain: str,
    ) -> list:
        """Fetch OHLC price data."""
        if token_id:
            return self._fetch_from_coingecko(token_id)
        if contract_address:
            return self._fetch_from_dexscreener(contract_address, chain)
        return []

    def _fetch_from_coingecko(self, token_id: str) -> list:
        """Fetch price history from CoinGecko."""
        try:
            resp = self.session.get(
                f"{COINGECKO_BASE_URL}/coins/{token_id}/ohlc",
                params={"vs_currency": "usd", "days": 30},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()  # [[timestamp, open, high, low, close], ...]
        except requests.RequestException:
            try:
                resp = self.session.get(
                    f"{COINGECKO_BASE_URL}/coins/{token_id}/market_chart",
                    params={"vs_currency": "usd", "days": 30},
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json().get("prices", [])
            except requests.RequestException:
                return []

    def _fetch_from_dexscreener(self, contract_address: str, chain: str) -> list:
        """Fetch price data from DEXScreener."""
        try:
            resp = self.session.get(
                f"{DEXSCREENER_BASE_URL}/dex/tokens/{contract_address}",
                timeout=10,
            )
            resp.raise_for_status()
            pairs = resp.json().get("pairs", [])
            if pairs:
                pair = pairs[0]
                price = float(pair.get("priceUsd", 0))
                return [[0, price, price * 1.02, price * 0.98]]
        except requests.RequestException:
            pass
        return []

    def _determine_trend(self, closes: np.ndarray) -> str:
        """Determine market trend using SMC principles."""
        if len(closes) < 5:
            return "neutral"

        short_ma = np.mean(closes[-7:])
        long_ma = np.mean(closes[-21:]) if len(closes) >= 21 else np.mean(closes)

        recent_highs = []
        recent_lows = []
        for i in range(2, len(closes) - 2):
            if closes[i] > closes[i - 1] and closes[i] > closes[i + 1]:
                recent_highs.append(closes[i])
            if closes[i] < closes[i - 1] and closes[i] < closes[i + 1]:
                recent_lows.append(closes[i])

        higher_highs = False
        higher_lows = False
        lower_highs = False
        lower_lows = False

        if len(recent_highs) >= 2:
            higher_highs = recent_highs[-1] > recent_highs[-2]
            lower_highs = recent_highs[-1] < recent_highs[-2]

        if len(recent_lows) >= 2:
            higher_lows = recent_lows[-1] > recent_lows[-2]
            lower_lows = recent_lows[-1] < recent_lows[-2]

        if higher_highs and higher_lows and short_ma > long_ma:
            return "bullish"
        elif lower_highs and lower_lows and short_ma < long_ma:
            return "bearish"
        return "neutral"

    def _find_liquidity_zones(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> list[LiquidityZone]:
        """Identify key liquidity/supply-demand zones using SMC."""
        zones = []

        for i in range(2, len(closes) - 2):
            if (
                closes[i] < closes[i - 1]
                and closes[i] < closes[i + 1]
                and closes[i] < closes[i - 2]
            ):
                zone = LiquidityZone(
                    price_low=float(lows[i]) if i < len(lows) else float(closes[i] * 0.98),
                    price_high=float(closes[i]),
                    zone_type="demand",
                    strength=7.0,
                )
                touches = sum(
                    1
                    for j in range(i + 1, len(closes))
                    if zone.price_low <= closes[j] <= zone.price_high
                )
                zone.touched = touches
                zone.strength = max(3, 10 - touches)
                zones.append(zone)

            if (
                closes[i] > closes[i - 1]
                and closes[i] > closes[i + 1]
                and closes[i] > closes[i - 2]
            ):
                zone = LiquidityZone(
                    price_low=float(closes[i]),
                    price_high=float(highs[i]) if i < len(highs) else float(closes[i] * 1.02),
                    zone_type="supply",
                    strength=7.0,
                )
                touches = sum(
                    1
                    for j in range(i + 1, len(closes))
                    if zone.price_low <= closes[j] <= zone.price_high
                )
                zone.touched = touches
                zone.strength = max(3, 10 - touches)
                zones.append(zone)

        zones.sort(key=lambda z: z.strength, reverse=True)
        return zones[:10]

    def _detect_break_of_structure(
        self, highs: np.ndarray, lows: np.ndarray
    ) -> list[StructureBreak]:
        """Detect Break of Structure (BOS) events."""
        breaks = []

        swing_highs = []
        swing_lows = []

        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                swing_highs.append((i, float(highs[i])))
            if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                swing_lows.append((i, float(lows[i])))

        for j in range(1, len(swing_highs)):
            prev_high = swing_highs[j - 1][1]
            curr_idx = swing_highs[j][0]
            if any(
                float(highs[k]) > prev_high
                for k in range(swing_highs[j - 1][0] + 1, min(curr_idx + 1, len(highs)))
            ):
                breaks.append(
                    StructureBreak(
                        direction="bullish",
                        price_level=prev_high,
                        confirmed=True,
                    )
                )

        for j in range(1, len(swing_lows)):
            prev_low = swing_lows[j - 1][1]
            curr_idx = swing_lows[j][0]
            if any(
                float(lows[k]) < prev_low
                for k in range(swing_lows[j - 1][0] + 1, min(curr_idx + 1, len(lows)))
            ):
                breaks.append(
                    StructureBreak(
                        direction="bearish",
                        price_level=prev_low,
                        confirmed=True,
                    )
                )

        return breaks[-5:]

    def _calculate_optimal_entry(
        self,
        liquidity_zones: list[LiquidityZone],
        current_price: float,
        trend: str,
    ) -> tuple[float, float]:
        """Calculate optimal sniper entry zone."""
        demand_zones = [z for z in liquidity_zones if z.zone_type == "demand"]
        supply_zones = [z for z in liquidity_zones if z.zone_type == "supply"]

        if trend == "bullish" and demand_zones:
            nearest_demand = min(
                demand_zones,
                key=lambda z: abs(current_price - z.price_high),
            )
            return (nearest_demand.price_low, nearest_demand.price_high)

        elif trend == "bearish" and supply_zones:
            nearest_supply = min(
                supply_zones,
                key=lambda z: abs(current_price - z.price_low),
            )
            return (nearest_supply.price_low, nearest_supply.price_high)

        if current_price > 0:
            return (current_price * 0.92, current_price * 0.97)
        return (0, 0)

    def _score_entry_quality(
        self,
        current_price: float,
        entry_zone: tuple[float, float],
        trend: str,
        liquidity_zones: list[LiquidityZone],
    ) -> float:
        """Score how good the current price is for entry (sniper mentality)."""
        if current_price == 0 or entry_zone == (0, 0):
            return 5.0

        score = 5.0

        if entry_zone[0] <= current_price <= entry_zone[1]:
            score = 9.0
        elif current_price < entry_zone[0]:
            score = 8.0
        else:
            distance_pct = (
                (current_price - entry_zone[1]) / entry_zone[1] * 100
                if entry_zone[1] > 0
                else 0
            )
            if distance_pct < 5:
                score = 7.0
            elif distance_pct < 10:
                score = 5.0
            else:
                score = 3.0

        if trend == "bullish":
            score += 1
        elif trend == "bearish":
            score -= 1

        return min(10, max(1, score))

    def _calculate_overall_score(
        self,
        trend: str,
        entry_quality: float,
        structure_breaks: list[StructureBreak],
        liquidity_zones: list[LiquidityZone],
    ) -> float:
        """Calculate overall technical score."""
        score = entry_quality * 0.40

        if trend == "bullish":
            score += 3.0
        elif trend == "neutral":
            score += 1.5

        bullish_breaks = sum(
            1 for b in structure_breaks if b.direction == "bullish" and b.confirmed
        )
        bearish_breaks = sum(
            1 for b in structure_breaks if b.direction == "bearish" and b.confirmed
        )
        if bullish_breaks > bearish_breaks:
            score += 1.5
        elif bearish_breaks > bullish_breaks:
            score -= 1.0

        strong_demand = sum(
            1 for z in liquidity_zones if z.zone_type == "demand" and z.strength > 7
        )
        if strong_demand > 0:
            score += 0.5

        return min(10, max(1, score))

    def _default_score(self, current_price: float) -> TechnicalScore:
        """Return default score when insufficient data."""
        return TechnicalScore(
            trend="neutral",
            current_price=current_price,
            entry_quality=5.0,
            overall=5.0,
            details={"note": "Insufficient price data for SMC analysis"},
        )

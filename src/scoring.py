"""
Scoring Engine
Aggregates all analysis modules into a final composite score.
Only recommends tokens with score >= 7.
"""

from dataclasses import dataclass, field
from typing import Optional

from config.settings import MIN_SCORE_THRESHOLD, SCORING_WEIGHTS
from src.fundamental_analysis import FundamentalScore
from src.smart_money import SmartMoneyScore
from src.technical_analysis import TechnicalScore
from src.risk_analysis import RiskScore


@dataclass
class TokenReport:
    name: str
    symbol: str
    chain: str
    contract_address: Optional[str]
    narrative: str
    why_potential: str
    smart_money_signal: str
    entry_zone: str
    risk_level: str
    score: float
    recommended: bool
    fundamental_score: FundamentalScore
    smart_money_score: SmartMoneyScore
    technical_score: TechnicalScore
    risk_score: RiskScore
    breakdown: dict = field(default_factory=dict)


class ScoringEngine:
    """Aggregates analysis scores into a final recommendation."""

    def __init__(self):
        self.weights = SCORING_WEIGHTS
        self.min_threshold = MIN_SCORE_THRESHOLD

    def score_token(
        self,
        name: str,
        symbol: str,
        chain: str,
        contract_address: Optional[str],
        narratives: list[str],
        fundamental: FundamentalScore,
        smart_money: SmartMoneyScore,
        technical: TechnicalScore,
        risk: RiskScore,
    ) -> TokenReport:
        """Calculate final composite score and generate report."""
        narrative_score = fundamental.narrative_strength
        smart_money_activity = smart_money.overall
        risk_level = risk.overall
        entry_timing = technical.entry_quality

        composite = (
            narrative_score * self.weights["narrative_strength"]
            + smart_money_activity * self.weights["smart_money_activity"]
            + risk_level * self.weights["risk_level"]
            + entry_timing * self.weights["entry_timing"]
        )

        if risk.red_flags:
            penalty = min(2.0, len(risk.red_flags) * 0.3)
            composite -= penalty

        if technical.trend == "bullish":
            composite += 0.5
        elif technical.trend == "bearish":
            composite -= 0.5

        composite = round(min(10, max(1, composite)), 1)
        recommended = composite >= self.min_threshold

        narrative_str = ", ".join(narratives) if narratives else "General"
        why_potential = self._generate_potential_summary(
            fundamental, smart_money, technical, narratives
        )
        smart_money_signal = self._generate_smart_money_signal(smart_money)
        entry_zone_str = self._format_entry_zone(technical)
        risk_level_str = self._format_risk_level(risk)

        return TokenReport(
            name=name,
            symbol=symbol,
            chain=chain,
            contract_address=contract_address,
            narrative=narrative_str,
            why_potential=why_potential,
            smart_money_signal=smart_money_signal,
            entry_zone=entry_zone_str,
            risk_level=risk_level_str,
            score=composite,
            recommended=recommended,
            fundamental_score=fundamental,
            smart_money_score=smart_money,
            technical_score=technical,
            risk_score=risk,
            breakdown={
                "narrative_strength": round(narrative_score, 1),
                "smart_money_activity": round(smart_money_activity, 1),
                "risk_level": round(risk_level, 1),
                "entry_timing": round(entry_timing, 1),
                "red_flag_penalty": round(min(2.0, len(risk.red_flags) * 0.3), 1),
                "trend_bonus": 0.5 if technical.trend == "bullish" else (-0.5 if technical.trend == "bearish" else 0),
            },
        )

    def _generate_potential_summary(
        self,
        fundamental: FundamentalScore,
        smart_money: SmartMoneyScore,
        technical: TechnicalScore,
        narratives: list[str],
    ) -> str:
        """Generate a human-readable summary of why the token has potential."""
        reasons = []

        if fundamental.narrative_strength >= 7:
            reasons.append(f"Strong narrative alignment ({', '.join(narratives)})")
        if fundamental.team_quality >= 7:
            reasons.append("High-quality team with active development")
        if smart_money.whale_accumulation >= 7:
            reasons.append("Smart money accumulating")
        if technical.trend == "bullish":
            reasons.append("Bullish market structure with higher highs/lows")
        if technical.entry_quality >= 7:
            reasons.append("Price near optimal entry zone (demand area)")
        if fundamental.community_strength >= 7:
            reasons.append("Strong community engagement")

        if not reasons:
            reasons.append("Moderate potential across multiple factors")

        return "; ".join(reasons)

    def _generate_smart_money_signal(self, smart_money: SmartMoneyScore) -> str:
        """Generate smart money signal description."""
        signals = []

        if smart_money.whale_accumulation >= 7:
            signals.append("Whales actively accumulating")
        elif smart_money.whale_accumulation >= 5:
            signals.append("Neutral whale activity")
        else:
            signals.append("Whales distributing - caution")

        if smart_money.wallet_concentration_risk >= 7:
            signals.append("Well-distributed holders")
        elif smart_money.wallet_concentration_risk < 4:
            signals.append("High concentration risk")

        if smart_money.whale_activities:
            acc_count = sum(
                1 for w in smart_money.whale_activities if w.action == "accumulating"
            )
            if acc_count > 0:
                signals.append(f"{acc_count} whale buy(s) detected")

        return "; ".join(signals) if signals else "No significant smart money data"

    def _format_entry_zone(self, technical: TechnicalScore) -> str:
        """Format entry zone for display."""
        if technical.entry_zone_low > 0 and technical.entry_zone_high > 0:
            low = technical.entry_zone_low
            high = technical.entry_zone_high
            if low < 0.01:
                return f"${low:.8f} - ${high:.8f}"
            elif low < 1:
                return f"${low:.4f} - ${high:.4f}"
            else:
                return f"${low:.2f} - ${high:.2f}"
        return "Insufficient data for entry zone"

    def _format_risk_level(self, risk: RiskScore) -> str:
        """Format risk level for display."""
        if risk.overall >= 8:
            level = "LOW"
        elif risk.overall >= 6:
            level = "MODERATE"
        elif risk.overall >= 4:
            level = "HIGH"
        else:
            level = "VERY HIGH"

        flags = ""
        if risk.red_flags:
            flags = f" | Flags: {', '.join(risk.red_flags[:3])}"

        return f"{level} ({risk.overall}/10){flags}"

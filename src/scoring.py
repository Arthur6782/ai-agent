"""
src/scoring.py
==============
Scoring engine — two complementary models:

4-dimension model  (ScoringEngine.score_token)
    Original model used throughout the pipeline.
    Weights: narrative 25%, smart_money 25%, risk 25%, entry_timing 25%.

5-dimension model  (ScoringEngine.calculate_total_score)
    Extended model that adds Market Context as a fifth dimension.
    Weights: fundamental 25%, technical 25%, smart_money 20%,
             risk 15%, market_context 15%.
    Returns a rich dict instead of a TokenReport so it can be used
    independently (e.g. for batch scoring or API output).

Additional helpers
    generate_recommendation(score, details)  → human-readable verdict string
    explain_score_breakdown(score_details)   → multi-line breakdown report
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import cfg, MIN_SCORE_THRESHOLD, SCORING_WEIGHTS
from src.fundamental_analysis import FundamentalScore
from src.market_context import MarketContext, MarketCondition
from src.risk_analysis import RiskScore
from src.smart_money import SmartMoneyScore
from src.technical_analysis import TechnicalScore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 5-Dimension weight configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FiveDimWeights:
    """
    Weights for the extended 5-dimension composite score.
    All five values must sum to exactly 1.0.
    """
    technical:      float = 0.25
    fundamental:    float = 0.25
    smart_money:    float = 0.20
    risk:           float = 0.15
    market_context: float = 0.15

    def __post_init__(self) -> None:
        total = round(
            self.technical + self.fundamental + self.smart_money
            + self.risk + self.market_context,
            10,
        )
        if total != 1.0:
            raise ValueError(f"FiveDimWeights must sum to 1.0, got {total}")

    def as_dict(self) -> dict[str, float]:
        return {
            "technical":      self.technical,
            "fundamental":    self.fundamental,
            "smart_money":    self.smart_money,
            "risk":           self.risk,
            "market_context": self.market_context,
        }


_DEFAULT_5D_WEIGHTS = FiveDimWeights()

# Recommendation tier table: (min_score, label)
_RECOMMENDATION_TIERS: list[tuple[float, str]] = [
    (9.0, "STRONG BUY — asymmetric setup, very high conviction"),
    (8.0, "BUY — solid across all dimensions, sniper entry valid"),
    (7.0, "WATCH / SMALL POSITION — meets threshold, size accordingly"),
    (5.0, "NEUTRAL — mixed signals, wait for clearer setup"),
    (0.0, "AVOID — risk outweighs potential reward"),
]


# ---------------------------------------------------------------------------
# TokenReport (unchanged — backward-compatible)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# ScoringEngine
# ---------------------------------------------------------------------------

class ScoringEngine:
    """Aggregates analysis module outputs into final composite scores."""

    def __init__(self, weights_5d: Optional[FiveDimWeights] = None) -> None:
        # 4-dimension weights (from config / backward compat)
        self._w4   = SCORING_WEIGHTS
        self._min  = MIN_SCORE_THRESHOLD
        # 5-dimension weights (new model)
        self._w5   = weights_5d or _DEFAULT_5D_WEIGHTS

    # =========================================================================
    # Original 4-dimension scorer (used by analyzer.py — DO NOT CHANGE)
    # =========================================================================

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
        """Calculate 4-dimension composite score and generate a TokenReport."""
        narrative_score = fundamental.narrative_strength
        sm_score        = smart_money.overall
        risk_score      = risk.overall
        entry_score     = technical.entry_quality

        composite = (
            narrative_score * self._w4["narrative_strength"]
            + sm_score      * self._w4["smart_money_activity"]
            + risk_score    * self._w4["risk_level"]
            + entry_score   * self._w4["entry_timing"]
        )

        # Adjustments
        if risk.red_flags:
            penalty    = min(
                cfg.scoring.max_red_flag_penalty,
                len(risk.red_flags) * cfg.scoring.red_flag_penalty_each,
            )
            composite -= penalty

        if technical.trend == "bullish":
            composite += cfg.scoring.bullish_trend_bonus
        elif technical.trend == "bearish":
            composite -= cfg.scoring.bearish_trend_penalty

        composite   = round(min(10.0, max(1.0, composite)), 1)
        recommended = composite >= self._min

        return TokenReport(
            name=name,
            symbol=symbol,
            chain=chain,
            contract_address=contract_address,
            narrative=", ".join(narratives) if narratives else "General",
            why_potential=    self._why_potential(fundamental, smart_money, technical, narratives),
            smart_money_signal=self._sm_signal(smart_money),
            entry_zone=       self._fmt_entry_zone(technical),
            risk_level=       self._fmt_risk_level(risk),
            score=composite,
            recommended=recommended,
            fundamental_score=fundamental,
            smart_money_score=smart_money,
            technical_score=technical,
            risk_score=risk,
            breakdown={
                "narrative_strength":  round(narrative_score, 1),
                "smart_money_activity":round(sm_score,        1),
                "risk_level":          round(risk_score,      1),
                "entry_timing":        round(entry_score,     1),
                "red_flag_penalty":    round(
                    min(cfg.scoring.max_red_flag_penalty,
                        len(risk.red_flags) * cfg.scoring.red_flag_penalty_each), 1),
                "trend_adjustment": (
                    +cfg.scoring.bullish_trend_bonus  if technical.trend == "bullish"
                    else -cfg.scoring.bearish_trend_penalty if technical.trend == "bearish"
                    else 0.0
                ),
            },
        )

    # =========================================================================
    # Extended 5-dimension scorer (new public API)
    # =========================================================================

    def calculate_total_score(self, analysis_results: dict) -> dict:
        """
        Calculate a composite score from all five analysis dimensions.

        Parameters
        ----------
        analysis_results : dict
            Expected keys (all optional — missing keys default to 5.0):
                fundamental_score   : float  (0-10)
                smart_money_score   : float  (0-10)
                technical_score     : float  (0-10)
                risk_score          : float  (0-10)
                market_context      : MarketContext | None
                trend               : str    "bullish"|"bearish"|"neutral"
                red_flags           : list[str]
                narratives          : list[str]
                token_name          : str
                token_symbol        : str

        Returns
        -------
        dict with keys:
            total_score, dimension_scores, weights, adjustments,
            recommendation, breakdown_text, passed_threshold
        """
        w = self._w5

        fundamental_s    = float(analysis_results.get("fundamental_score",  5.0))
        smart_money_s    = float(analysis_results.get("smart_money_score",  5.0))
        technical_s      = float(analysis_results.get("technical_score",    5.0))
        risk_s           = float(analysis_results.get("risk_score",         5.0))
        market_ctx: Optional[MarketContext] = analysis_results.get("market_context")

        market_ctx_s = self._score_market_context(market_ctx)

        raw_composite = (
            technical_s   * w.technical
            + fundamental_s * w.fundamental
            + smart_money_s * w.smart_money
            + risk_s        * w.risk
            + market_ctx_s  * w.market_context
        )

        # Adjustments (same logic as 4D model)
        red_flags  = analysis_results.get("red_flags", [])
        trend      = analysis_results.get("trend", "neutral")
        adjustments: dict[str, float] = {}

        if red_flags:
            penalty = min(
                cfg.scoring.max_red_flag_penalty,
                len(red_flags) * cfg.scoring.red_flag_penalty_each,
            )
            raw_composite   -= penalty
            adjustments["red_flag_penalty"] = -round(penalty, 2)

        if trend == "bullish":
            raw_composite       += cfg.scoring.bullish_trend_bonus
            adjustments["bullish_bonus"] = cfg.scoring.bullish_trend_bonus
        elif trend == "bearish":
            raw_composite       -= cfg.scoring.bearish_trend_penalty
            adjustments["bearish_penalty"] = -cfg.scoring.bearish_trend_penalty

        total = round(min(10.0, max(1.0, raw_composite)), 1)

        dimension_scores = {
            "technical":      round(technical_s,  1),
            "fundamental":    round(fundamental_s, 1),
            "smart_money":    round(smart_money_s, 1),
            "risk":           round(risk_s,        1),
            "market_context": round(market_ctx_s,  1),
        }

        details = {
            "total_score":       total,
            "dimension_scores":  dimension_scores,
            "weights":           w.as_dict(),
            "adjustments":       adjustments,
            "red_flags":         red_flags,
            "recommendation":    self.generate_recommendation(total, dimension_scores),
            "breakdown_text":    self.explain_score_breakdown(
                {**dimension_scores, "total": total, "weights": w.as_dict(),
                 "adjustments": adjustments}
            ),
            "passed_threshold":  total >= self._min,
            "token_name":        analysis_results.get("token_name",   ""),
            "token_symbol":      analysis_results.get("token_symbol", ""),
            "narratives":        analysis_results.get("narratives",   []),
        }
        logger.debug("5D score for %s: %.1f", details["token_symbol"], total)
        return details

    def generate_recommendation(self, total_score: float, details: dict) -> str:
        """
        Translate a numeric score into a concise recommendation string.

        Also appends the single strongest and weakest dimension as context.
        """
        for threshold, label in _RECOMMENDATION_TIERS:
            if total_score >= threshold:
                verdict = label
                break
        else:
            verdict = "AVOID"

        # Annotate with strongest / weakest dimension if available
        dim_scores = {
            k: v for k, v in details.items()
            if isinstance(v, (int, float)) and k not in ("total",)
        }
        if dim_scores:
            best  = max(dim_scores, key=dim_scores.get)    # type: ignore[arg-type]
            worst = min(dim_scores, key=dim_scores.get)    # type: ignore[arg-type]
            verdict += f" | Strongest: {best} ({dim_scores[best]:.1f})"
            if worst != best:
                verdict += f" | Weakest: {worst} ({dim_scores[worst]:.1f})"

        return verdict

    def explain_score_breakdown(self, score_details: dict) -> str:
        """
        Produce a human-readable multi-line breakdown of the composite score.

        Parameters
        ----------
        score_details : dict
            Must contain 'total', 'weights', and dimension score keys.
        """
        total   = score_details.get("total", 0.0)
        weights = score_details.get("weights", {})
        adj     = score_details.get("adjustments", {})

        lines: list[str] = [
            "─" * 52,
            f"  SCORE BREAKDOWN — Total: {total:.1f}/10",
            "─" * 52,
        ]

        _LABELS = {
            "technical":      "Technical (SMC)",
            "fundamental":    "Fundamental",
            "smart_money":    "Smart Money",
            "risk":           "Risk Safety",
            "market_context": "Market Context",
        }

        for dim, label in _LABELS.items():
            raw_score = score_details.get(dim, 5.0)
            weight    = weights.get(dim, 0.0)
            contrib   = round(raw_score * weight, 2)
            bar       = "█" * int(raw_score) + "░" * (10 - int(raw_score))
            lines.append(
                f"  {label:<20} {bar}  {raw_score:4.1f}  ×{weight:.0%} = {contrib:.2f}"
            )

        if adj:
            lines.append("  " + "·" * 48)
            for name, val in adj.items():
                sign = "+" if val >= 0 else ""
                lines.append(f"  Adjustment [{name:<22}] {sign}{val:.2f}")

        lines += [
            "─" * 52,
            f"  Threshold to pass: {self._min:.1f}  |  "
            + ("✓ RECOMMENDED" if total >= self._min else "✗ BELOW THRESHOLD"),
            "─" * 52,
        ]
        return "\n".join(lines)

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _score_market_context(self, ctx: Optional[MarketContext]) -> float:
        """Convert MarketContext fields into a 0-10 score."""
        if ctx is None:
            return 5.0

        score = 5.0

        # Market condition
        if ctx.condition == MarketCondition.BULLISH:
            score += 2.0
        elif ctx.condition == MarketCondition.BEARISH:
            score -= 2.0
        # RANGING → no change

        # Fear & Greed index: <25 = extreme fear (contrarian buy), >75 = greed (risky)
        if ctx.fear_greed_index is not None:
            fg = ctx.fear_greed_index
            if fg < 20:        score += 1.5  # extreme fear = opportunity
            elif fg < 40:      score += 0.5
            elif fg > 80:      score -= 1.5  # extreme greed = risky entry
            elif fg > 65:      score -= 0.5

        # BTC dominance: rising dominance = alt-season risk; falling = alt opportunity
        btc_dom = ctx.btc_dominance
        if btc_dom > 60:    score -= 1.0  # money in BTC, not alts
        elif btc_dom < 40:  score += 1.0  # capital flowing to alts

        # 24h market cap change
        mc_chg = ctx.market_cap_change_24h
        if mc_chg > 5:       score += 0.5
        elif mc_chg < -5:    score -= 0.5

        return round(min(10.0, max(1.0, score)), 1)

    # ── 4-D helpers (unchanged from original) ────────────────────────────────

    def _why_potential(
        self,
        fundamental: FundamentalScore,
        smart_money: SmartMoneyScore,
        technical: TechnicalScore,
        narratives: list[str],
    ) -> str:
        reasons: list[str] = []
        if fundamental.narrative_strength >= 7:
            reasons.append(f"Strong narrative ({', '.join(narratives)})")
        if fundamental.team_quality >= 7:
            reasons.append("Active development team")
        if smart_money.whale_accumulation >= 7:
            reasons.append("Smart money accumulating")
        if technical.trend == "bullish":
            reasons.append("Bullish market structure (HH/HL)")
        if technical.entry_quality >= 7:
            reasons.append("Price at demand zone — optimal entry")
        if fundamental.community_strength >= 7:
            reasons.append("Strong community engagement")
        if getattr(fundamental, "safety_score", 0) >= 8:
            reasons.append("Contract clean — no dangerous functions")
        return "; ".join(reasons) if reasons else "Moderate potential across multiple factors"

    def _sm_signal(self, sm: SmartMoneyScore) -> str:
        parts: list[str] = []
        if sm.whale_accumulation >= 7:
            parts.append("Whales actively accumulating")
        elif sm.whale_accumulation >= 5:
            parts.append("Neutral whale activity")
        else:
            parts.append("Whales distributing — caution")

        if sm.wallet_concentration_risk >= 7:
            parts.append("Well-distributed holders")
        elif sm.wallet_concentration_risk < 4:
            parts.append("High concentration risk")

        acc = sum(1 for w in sm.whale_activities if w.action == "accumulating")
        if acc > 0:
            parts.append(f"{acc} whale buy(s) detected")

        return "; ".join(parts) if parts else "No significant smart money data"

    def _fmt_entry_zone(self, technical: TechnicalScore) -> str:
        lo, hi = technical.entry_zone_low, technical.entry_zone_high
        if lo > 0 and hi > 0:
            fmt = ".8f" if lo < 0.01 else (".4f" if lo < 1 else ".2f")
            return f"${lo:{fmt}} – ${hi:{fmt}}"
        return "Insufficient data for entry zone"

    def _fmt_risk_level(self, risk: RiskScore) -> str:
        if risk.overall >= 8:   level = "LOW"
        elif risk.overall >= 6: level = "MODERATE"
        elif risk.overall >= 4: level = "HIGH"
        else:                   level = "VERY HIGH"

        flags = ""
        if risk.red_flags:
            flags = f" | Flags: {', '.join(risk.red_flags[:3])}"
        return f"{level} ({risk.overall}/10){flags}"

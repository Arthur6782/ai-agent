"""Tests for the scoring engine."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scoring import ScoringEngine
from src.fundamental_analysis import FundamentalScore
from src.smart_money import SmartMoneyScore
from src.technical_analysis import TechnicalScore
from src.risk_analysis import RiskScore


def _make_scores(
    narrative=7, smart=7, risk_overall=7, entry=7, trend="bullish", red_flags=None
):
    """Helper to create score objects."""
    fundamental = FundamentalScore(
        narrative_strength=narrative,
        team_quality=6,
        utility_score=6,
        community_strength=6,
        partnership_score=6,
        overall=6,
    )
    smart_money = SmartMoneyScore(
        whale_accumulation=smart,
        wallet_concentration_risk=6,
        unusual_activity=6,
        overall=smart,
    )
    technical = TechnicalScore(
        trend=trend,
        entry_quality=entry,
        overall=entry,
        current_price=1.0,
        entry_zone_low=0.9,
        entry_zone_high=0.95,
    )
    risk = RiskScore(
        liquidity_risk=risk_overall,
        rug_pull_risk=risk_overall,
        tokenomics_risk=risk_overall,
        overall=risk_overall,
        red_flags=red_flags or [],
    )
    return fundamental, smart_money, technical, risk


def test_high_score_recommended():
    """Token with all high scores should be recommended."""
    engine = ScoringEngine()
    f, s, t, r = _make_scores(narrative=9, smart=8, risk_overall=8, entry=8)
    report = engine.score_token(
        "TestToken", "TEST", "ethereum", None, ["AI"], f, s, t, r
    )
    assert report.recommended
    assert report.score >= 7


def test_low_score_not_recommended():
    """Token with low scores should not be recommended."""
    engine = ScoringEngine()
    f, s, t, r = _make_scores(
        narrative=3, smart=3, risk_overall=3, entry=3, trend="bearish"
    )
    report = engine.score_token(
        "BadToken", "BAD", "ethereum", None, ["Meme"], f, s, t, r
    )
    assert not report.recommended
    assert report.score < 7


def test_red_flags_penalize_score():
    """Red flags should reduce the score."""
    engine = ScoringEngine()
    f1, s1, t1, r1 = _make_scores()
    report_clean = engine.score_token(
        "Clean", "CLN", "ethereum", None, ["AI"], f1, s1, t1, r1
    )

    f2, s2, t2, r2 = _make_scores(
        red_flags=["Low liquidity", "High concentration", "Unverified contract"]
    )
    report_flagged = engine.score_token(
        "Flagged", "FLG", "ethereum", None, ["AI"], f2, s2, t2, r2
    )

    assert report_clean.score > report_flagged.score


def test_bullish_trend_bonus():
    """Bullish trend should give a score bonus over bearish."""
    engine = ScoringEngine()
    f1, s1, t1, r1 = _make_scores(trend="bullish")
    report_bull = engine.score_token(
        "Bull", "BULL", "ethereum", None, ["AI"], f1, s1, t1, r1
    )

    f2, s2, t2, r2 = _make_scores(trend="bearish")
    report_bear = engine.score_token(
        "Bear", "BEAR", "ethereum", None, ["AI"], f2, s2, t2, r2
    )

    assert report_bull.score > report_bear.score


def test_report_fields_populated():
    """All report fields should be populated."""
    engine = ScoringEngine()
    f, s, t, r = _make_scores()
    report = engine.score_token(
        "Test", "TST", "ethereum", "0x123", ["AI", "DePIN"], f, s, t, r
    )

    assert report.name == "Test"
    assert report.symbol == "TST"
    assert report.narrative == "AI, DePIN"
    assert report.entry_zone != ""
    assert report.risk_level != ""
    assert report.why_potential != ""
    assert report.smart_money_signal != ""
    assert report.breakdown


if __name__ == "__main__":
    test_high_score_recommended()
    test_low_score_not_recommended()
    test_red_flags_penalize_score()
    test_bullish_trend_bonus()
    test_report_fields_populated()
    print("All scoring tests passed!")

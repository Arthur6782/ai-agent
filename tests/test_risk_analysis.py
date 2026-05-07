"""Tests for the risk analysis module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.risk_analysis import RiskAnalyzer


def test_high_liquidity_low_risk():
    """High liquidity should result in low risk."""
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(
        liquidity_usd=2_000_000,
        market_cap=10_000_000,
        volume_24h=500_000,
    )
    assert result.liquidity_risk >= 7
    assert not any("liquidity" in f.lower() for f in result.red_flags)


def test_low_liquidity_high_risk():
    """Low liquidity should result in high risk and red flags."""
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(
        liquidity_usd=10_000,
        market_cap=5_000_000,
        volume_24h=1_000,
    )
    assert result.liquidity_risk < 7
    assert len(result.red_flags) > 0


def test_high_concentration_flags():
    """Extreme holder concentration should be flagged."""
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(
        top_holders_pct=85.0,
        liquidity_usd=100_000,
        market_cap=1_000_000,
        volume_24h=50_000,
    )
    assert any("concentration" in f.lower() for f in result.red_flags)


def test_pump_flagged():
    """Tokens that already pumped should be flagged."""
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(
        price_change_24h=150.0,
        liquidity_usd=100_000,
        market_cap=1_000_000,
        volume_24h=50_000,
    )
    assert any("pumped" in f.lower() for f in result.red_flags)


def test_overall_score_range():
    """Overall score should always be between 1 and 10."""
    analyzer = RiskAnalyzer()
    result = analyzer.analyze(
        liquidity_usd=0,
        market_cap=0,
        volume_24h=0,
        top_holders_pct=0,
    )
    assert 1 <= result.overall <= 10


if __name__ == "__main__":
    test_high_liquidity_low_risk()
    test_low_liquidity_high_risk()
    test_high_concentration_flags()
    test_pump_flagged()
    test_overall_score_range()
    print("All risk analysis tests passed!")

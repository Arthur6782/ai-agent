"""Tests for the new 5-dimension scoring API in scoring.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scoring import ScoringEngine, FiveDimWeights
from src.market_context import MarketContext, MarketCondition


def _make_results(
    fundamental=7.0, smart_money=7.0, technical=7.0,
    risk=7.0, condition=MarketCondition.BULLISH,
    fear_greed=50, btc_dom=50.0, mc_chg=3.0,
    trend="bullish", red_flags=None, narratives=None,
):
    ctx = MarketContext(
        condition=condition,
        btc_dominance=btc_dom,
        total_market_cap=2e12,
        market_cap_change_24h=mc_chg,
        fear_greed_index=fear_greed,
        dominant_narratives=narratives or ["AI"],
    )
    return {
        "fundamental_score":  fundamental,
        "smart_money_score":  smart_money,
        "technical_score":    technical,
        "risk_score":         risk,
        "market_context":     ctx,
        "trend":              trend,
        "red_flags":          red_flags or [],
        "narratives":         narratives or ["AI"],
        "token_name":         "TestToken",
        "token_symbol":       "TEST",
    }


# ─── FiveDimWeights ───────────────────────────────────────────────────────────

def test_default_weights_sum_to_one():
    w = FiveDimWeights()
    total = w.technical + w.fundamental + w.smart_money + w.risk + w.market_context
    assert abs(total - 1.0) < 1e-9


def test_custom_weights_invalid_raises():
    try:
        FiveDimWeights(technical=0.5, fundamental=0.5, smart_money=0.5,
                       risk=0.5, market_context=0.5)
        assert False, "Should raise ValueError"
    except ValueError:
        pass


def test_weights_as_dict():
    w = FiveDimWeights()
    d = w.as_dict()
    assert set(d.keys()) == {"technical", "fundamental", "smart_money", "risk", "market_context"}
    assert abs(sum(d.values()) - 1.0) < 1e-9


# ─── calculate_total_score ────────────────────────────────────────────────────

def test_total_score_all_high_recommended():
    engine = ScoringEngine()
    result = engine.calculate_total_score(_make_results(
        fundamental=9, smart_money=9, technical=9, risk=9,
        fear_greed=40, btc_dom=45
    ))
    assert result["total_score"] >= 7
    assert result["passed_threshold"]


def test_total_score_all_low_not_recommended():
    engine = ScoringEngine()
    result = engine.calculate_total_score(_make_results(
        fundamental=2, smart_money=2, technical=2, risk=2,
        condition=MarketCondition.BEARISH, fear_greed=80,
        btc_dom=65, mc_chg=-5, trend="bearish",
    ))
    assert not result["passed_threshold"]


def test_total_score_red_flags_penalise():
    engine = ScoringEngine()
    clean   = engine.calculate_total_score(_make_results())
    flagged = engine.calculate_total_score(_make_results(
        red_flags=["honeypot", "mint function", "no liquidity"]
    ))
    assert clean["total_score"] > flagged["total_score"]


def test_total_score_bearish_market_lowers_score():
    engine = ScoringEngine()
    bull = engine.calculate_total_score(_make_results(condition=MarketCondition.BULLISH))
    bear = engine.calculate_total_score(_make_results(
        condition=MarketCondition.BEARISH, trend="bearish"
    ))
    assert bull["total_score"] > bear["total_score"]


def test_total_score_result_keys():
    engine = ScoringEngine()
    result = engine.calculate_total_score(_make_results())
    required = {"total_score", "dimension_scores", "weights", "adjustments",
                "recommendation", "breakdown_text", "passed_threshold",
                "token_name", "token_symbol", "narratives"}
    assert required.issubset(set(result.keys()))


def test_total_score_dimension_scores_keys():
    engine = ScoringEngine()
    result = engine.calculate_total_score(_make_results())
    assert set(result["dimension_scores"].keys()) == {
        "technical", "fundamental", "smart_money", "risk", "market_context"
    }


def test_total_score_in_range():
    engine = ScoringEngine()
    result = engine.calculate_total_score(_make_results())
    assert 1 <= result["total_score"] <= 10


# ─── generate_recommendation ──────────────────────────────────────────────────

def test_recommendation_strong_buy():
    engine = ScoringEngine()
    rec = engine.generate_recommendation(9.5, {"technical": 9.5, "fundamental": 9.5})
    assert "STRONG BUY" in rec


def test_recommendation_avoid():
    engine = ScoringEngine()
    rec = engine.generate_recommendation(1.0, {"technical": 1.0})
    assert "AVOID" in rec


def test_recommendation_neutral():
    engine = ScoringEngine()
    rec = engine.generate_recommendation(6.0, {"technical": 6.0})
    assert "NEUTRAL" in rec


def test_recommendation_shows_strongest_weakest():
    engine = ScoringEngine()
    rec = engine.generate_recommendation(7.5, {"technical": 9.0, "fundamental": 3.0})
    assert "technical" in rec.lower()
    assert "fundamental" in rec.lower()


# ─── explain_score_breakdown ──────────────────────────────────────────────────

def test_explain_contains_all_dimensions():
    engine = ScoringEngine()
    w = FiveDimWeights()
    text = engine.explain_score_breakdown({
        "total": 7.5, "weights": w.as_dict(),
        "adjustments": {"red_flag_penalty": -0.3},
        "technical": 8.0, "fundamental": 7.0, "smart_money": 7.0,
        "risk": 8.0, "market_context": 6.5,
    })
    for dim in ("Technical", "Fundamental", "Smart Money", "Risk", "Market Context"):
        assert dim in text, f"Missing '{dim}' in breakdown"


def test_explain_shows_threshold():
    engine = ScoringEngine()
    text = engine.explain_score_breakdown({"total": 8.0, "weights": {}, "adjustments": {}})
    assert "Threshold" in text or "threshold" in text.lower()


def test_explain_shows_recommendation_verdict():
    engine = ScoringEngine()
    text = engine.explain_score_breakdown({
        "total": 7.5, "weights": FiveDimWeights().as_dict(), "adjustments": {},
        "technical": 7.5, "fundamental": 7.5, "smart_money": 7.5,
        "risk": 7.5, "market_context": 7.5,
    })
    assert "RECOMMENDED" in text or "THRESHOLD" in text


# ─── market context scoring ───────────────────────────────────────────────────

def test_market_context_none_returns_midpoint():
    engine = ScoringEngine()
    score = engine._score_market_context(None)
    assert score == 5.0


def test_market_context_bullish_scores_high():
    engine = ScoringEngine()
    ctx = MarketContext(
        condition=MarketCondition.BULLISH,
        btc_dominance=45, total_market_cap=2e12,
        market_cap_change_24h=5, fear_greed_index=35,
    )
    assert engine._score_market_context(ctx) > 5.0


def test_market_context_extreme_greed_penalised():
    engine = ScoringEngine()
    ctx = MarketContext(
        condition=MarketCondition.BULLISH,
        btc_dominance=50, total_market_cap=2e12,
        market_cap_change_24h=2, fear_greed_index=90,
    )
    ctx_greed = engine._score_market_context(ctx)

    ctx2 = MarketContext(
        condition=MarketCondition.BULLISH,
        btc_dominance=50, total_market_cap=2e12,
        market_cap_change_24h=2, fear_greed_index=30,
    )
    ctx_fear = engine._score_market_context(ctx2)
    assert ctx_fear > ctx_greed  # extreme fear is a contrarian buy opportunity


if __name__ == "__main__":
    test_default_weights_sum_to_one()
    test_custom_weights_invalid_raises()
    test_weights_as_dict()
    test_total_score_all_high_recommended()
    test_total_score_all_low_not_recommended()
    test_total_score_red_flags_penalise()
    test_total_score_bearish_market_lowers_score()
    test_total_score_result_keys()
    test_total_score_dimension_scores_keys()
    test_total_score_in_range()
    test_recommendation_strong_buy()
    test_recommendation_avoid()
    test_recommendation_neutral()
    test_recommendation_shows_strongest_weakest()
    test_explain_contains_all_dimensions()
    test_explain_shows_threshold()
    test_explain_shows_recommendation_verdict()
    test_market_context_none_returns_midpoint()
    test_market_context_bullish_scores_high()
    test_market_context_extreme_greed_penalised()
    print("All extended scoring tests passed!")

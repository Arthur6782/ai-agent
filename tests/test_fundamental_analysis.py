"""Tests for the new standalone functions in fundamental_analysis.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.fundamental_analysis import (
    check_liquidity,
    check_holder_distribution,
    check_contract_safety,
    analyze_community_metrics,
    calculate_fundamental_score,
    analyze_fundamentals,
    FundamentalScore,
)


# ─── check_liquidity ──────────────────────────────────────────────────────────

def test_liquidity_excellent():
    result = check_liquidity({"liquidity_usd": 3_000_000, "market_cap": 10_000_000})
    assert result["score"] >= 8
    assert result["status"] == "excellent"
    assert not result["warnings"]


def test_liquidity_critical():
    result = check_liquidity({"liquidity_usd": 10_000, "market_cap": 1_000_000})
    assert result["score"] <= 4
    assert result["status"] == "critical"
    assert any("liquidity" in w.lower() for w in result["warnings"])


def test_liquidity_high_mc_ratio():
    result = check_liquidity({"liquidity_usd": 50_000, "market_cap": 10_000_000})
    assert any("ratio" in w.lower() for w in result["warnings"])


def test_liquidity_unknown_when_no_data():
    result = check_liquidity({})
    assert result["status"] == "unknown"
    assert 1 <= result["score"] <= 10


# ─── check_holder_distribution ────────────────────────────────────────────────

def test_holders_extreme_concentration():
    result = check_holder_distribution({"top10_holders_pct": 90.0})
    assert result["risk"] == "extreme"
    assert result["score"] <= 3
    assert result["warnings"]


def test_holders_healthy_distribution():
    result = check_holder_distribution({"top10_holders_pct": 15.0, "unique_holders": 50_000})
    assert result["risk"] in ("low", "very_low")
    assert result["score"] >= 7


def test_holders_unknown():
    result = check_holder_distribution({})
    assert result["risk"] == "unknown"
    assert result["score"] == 5.0


def test_holders_few_unique_penalised():
    result = check_holder_distribution({"top10_holders_pct": 20.0, "unique_holders": 5})
    assert result["warnings"]


# ─── check_contract_safety ────────────────────────────────────────────────────

def test_safety_no_address_returns_neutral():
    result = check_contract_safety({"chain": "ethereum"})
    assert result["score"] == 5.5
    assert not result["is_honeypot"]


def test_safety_solana_returns_neutral():
    result = check_contract_safety({"contract_address": "So11111", "chain": "solana"})
    assert result["score"] == 5.5


def test_safety_all_fields_present():
    result = check_contract_safety({"contract_address": "0x1234", "chain": "bsc"})
    required = {"verified", "is_proxy", "is_honeypot", "has_mint",
                "has_blacklist", "has_pause", "has_selfdestruct",
                "has_fee_modification", "buy_tax_pct", "sell_tax_pct",
                "score", "warnings"}
    assert required.issubset(set(result.keys()))


# ─── analyze_community_metrics ───────────────────────────────────────────────

def test_community_large_twitter():
    # 5.0 base + 2.5 (>500k twitter) - 1.0 (zero-dev penalty) = 6.5
    result = analyze_community_metrics({"twitter_followers": 600_000})
    assert result["score"] >= 6.0


def test_community_no_data():
    # 5.0 base - 1.0 (zero dev activity) = 4.0
    result = analyze_community_metrics({})
    assert result["score"] < 5.0


def test_community_active_github():
    result = analyze_community_metrics({"github_commits_4w": 250, "github_contributors": 30})
    assert result["score"] >= 7


def test_community_dead_github():
    result = analyze_community_metrics({"github_commits_4w": 0, "github_contributors": 0})
    assert result["score"] < 5.0


# ─── calculate_fundamental_score ────────────────────────────────────────────

def test_calculate_score_all_high():
    fd = {
        "narrative":           {"score": 9.0},
        "team":                {"score": 9.0},
        "utility":             {"score": 9.0},
        "community":           {"score": 9.0},
        "backers":             {"score": 9.0},
        "liquidity":           {"score": 9.0},
        "contract_safety":     {"score": 9.0},
        "holder_distribution": {"score": 9.0},
    }
    score = calculate_fundamental_score(fd)
    assert score == 9.0


def test_calculate_score_all_low():
    fd = {
        "narrative":           {"score": 1.0},
        "team":                {"score": 1.0},
        "utility":             {"score": 1.0},
        "community":           {"score": 1.0},
        "backers":             {"score": 1.0},
        "liquidity":           {"score": 1.0},
        "contract_safety":     {"score": 1.0},
        "holder_distribution": {"score": 1.0},
    }
    assert calculate_fundamental_score(fd) == 1.0


def test_calculate_score_missing_keys_fallback():
    # Missing keys should default to 5.0 without raising
    score = calculate_fundamental_score({})
    assert 1 <= score <= 10


# ─── analyze_fundamentals ────────────────────────────────────────────────────

def test_analyze_fundamentals_keys():
    td = {
        "narratives": ["AI"],
        "description": "AI infrastructure protocol",
        "liquidity_usd": 200_000,
        "market_cap": 5_000_000,
    }
    result = analyze_fundamentals(td)
    required = {"liquidity", "holder_distribution", "contract_safety",
                "community", "narrative", "team", "backers", "utility",
                "red_flags", "green_flags", "overall_score"}
    assert required.issubset(set(result.keys()))


def test_analyze_fundamentals_score_in_range():
    td = {"narratives": ["DePIN"], "liquidity_usd": 100_000}
    result = analyze_fundamentals(td)
    assert 1 <= result["overall_score"] <= 10


def test_analyze_fundamentals_narrative_matched():
    td = {
        "narratives": [],
        "description": "ai machine learning inference network",
        "categories": [],
    }
    result = analyze_fundamentals(td)
    assert "AI" in result["narrative"]["matched"]


# ─── FundamentalScore backward compatibility ──────────────────────────────────

def test_fundamental_score_new_fields_have_defaults():
    # Old callers that don't pass new fields must still work
    fs = FundamentalScore(
        narrative_strength=7,
        team_quality=6,
        utility_score=6,
        community_strength=6,
        partnership_score=6,
        overall=6,
    )
    assert fs.liquidity_score == 0.0
    assert fs.safety_score    == 0.0
    assert fs.holder_score    == 0.0


if __name__ == "__main__":
    test_liquidity_excellent()
    test_liquidity_critical()
    test_liquidity_high_mc_ratio()
    test_liquidity_unknown_when_no_data()
    test_holders_extreme_concentration()
    test_holders_healthy_distribution()
    test_holders_unknown()
    test_holders_few_unique_penalised()
    test_safety_no_address_returns_neutral()
    test_safety_solana_returns_neutral()
    test_safety_all_fields_present()
    test_community_large_twitter()
    test_community_no_data()
    test_community_active_github()
    test_community_dead_github()
    test_calculate_score_all_high()
    test_calculate_score_all_low()
    test_calculate_score_missing_keys_fallback()
    test_analyze_fundamentals_keys()
    test_analyze_fundamentals_score_in_range()
    test_analyze_fundamentals_narrative_matched()
    test_fundamental_score_new_fields_have_defaults()
    print("All fundamental analysis tests passed!")

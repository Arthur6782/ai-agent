"""Tests for the token filter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.token_discovery import DiscoveredToken
from src.token_filter import TokenFilter


def test_filter_rejects_pump():
    """Tokens that pumped >100% in 24h should be rejected."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="PumpCoin", symbol="PUMP", price_change_24h=150.0
    )
    result = f.filter(token)
    assert not result.passed
    assert "pumped" in result.reason.lower()


def test_filter_rejects_7d_pump():
    """Tokens that pumped >300% in 7d should be rejected."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="WeekPump", symbol="WP", price_change_7d=350.0
    )
    result = f.filter(token)
    assert not result.passed
    assert "overextended" in result.reason.lower()


def test_filter_rejects_low_volume():
    """Tokens with very low volume should be rejected."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="DeadCoin", symbol="DEAD", volume_24h=100.0
    )
    result = f.filter(token)
    assert not result.passed
    assert "volume" in result.reason.lower()


def test_filter_rejects_high_mcap():
    """Tokens with market cap > LOW_CAP_MAX should be rejected."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="BigCoin", symbol="BIG", market_cap=100_000_000, volume_24h=5000
    )
    result = f.filter(token)
    assert not result.passed
    assert "market cap" in result.reason.lower()


def test_filter_rejects_scam_names():
    """Tokens with multiple scam keywords should be rejected."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="SafeMoonInu", symbol="SMI", volume_24h=5000
    )
    result = f.filter(token)
    assert not result.passed
    assert "scam" in result.reason.lower()


def test_filter_passes_good_token():
    """A reasonable token should pass all filters."""
    f = TokenFilter()
    token = DiscoveredToken(
        name="RenderToken",
        symbol="RNDR",
        market_cap=5_000_000,
        volume_24h=50_000,
        price_change_24h=15.0,
        price_change_7d=30.0,
        discovery_source="coingecko_trending",
    )
    result = f.filter(token)
    assert result.passed


def test_batch_filter():
    """Batch filter should process all tokens."""
    f = TokenFilter()
    tokens = [
        DiscoveredToken(name="Good", symbol="GOOD", volume_24h=5000, market_cap=1_000_000),
        DiscoveredToken(name="PumpCoin", symbol="PUMP", price_change_24h=200.0),
    ]
    results = f.batch_filter(tokens)
    assert len(results) == 2
    assert results[0][1].passed
    assert not results[1][1].passed


if __name__ == "__main__":
    test_filter_rejects_pump()
    test_filter_rejects_7d_pump()
    test_filter_rejects_low_volume()
    test_filter_rejects_high_mcap()
    test_filter_rejects_scam_names()
    test_filter_passes_good_token()
    test_batch_filter()
    print("All token filter tests passed!")

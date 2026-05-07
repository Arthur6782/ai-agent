"""
src/analyzer.py
===============
Main orchestrator — coordinates all analysis modules into a single pipeline.

Cache integration
-----------------
- Market context is cached for 2 minutes (CACHE_TTL["market_data"]).
- Individual token analysis results are cached for 5 minutes.
- Cache is transparent: re-running the same scan within TTL is instant.
"""

import logging
from dataclasses import dataclass, field

from src.fundamental_analysis import FundamentalAnalyzer
from src.market_context import MarketContext, MarketContextAnalyzer
from src.risk_analysis import RiskAnalyzer
from src.scoring import ScoringEngine, TokenReport
from src.smart_money import SmartMoneyAnalyzer
from src.technical_analysis import TechnicalAnalyzer
from src.token_discovery import DiscoveredToken, TokenDiscoveryEngine
from src.token_filter import TokenFilter
from utils.cache import token_cache

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    market_context: MarketContext
    total_discovered: int
    total_filtered: int
    total_analyzed: int
    recommended_tokens: list[TokenReport] = field(default_factory=list)
    rejected_tokens: list[dict] = field(default_factory=list)
    all_reports: list[TokenReport] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class CryptoTokenAnalyzer:
    """Orchestrates the full token analysis pipeline."""

    def __init__(self) -> None:
        self.market_analyzer      = MarketContextAnalyzer()
        self.discovery_engine     = TokenDiscoveryEngine()
        self.token_filter         = TokenFilter()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.smart_money_analyzer = SmartMoneyAnalyzer()
        self.technical_analyzer   = TechnicalAnalyzer()
        self.risk_analyzer        = RiskAnalyzer()
        self.scoring_engine       = ScoringEngine()

    # ── Public entry points ───────────────────────────────────────────────

    def run_full_analysis(self, max_tokens: int = 10) -> AnalysisResult:
        """Run the complete discovery → filter → analyze → score pipeline."""
        logger.info("Starting full analysis (max_tokens=%d)", max_tokens)

        market_context = self._get_market_context()

        discovered = self.discovery_engine.discover_tokens(
            market_context.dominant_narratives
        )
        logger.info("Discovered %d candidate token(s)", len(discovered))

        filter_results = self.token_filter.batch_filter(discovered)
        passed   = [t for t, r in filter_results if r.passed]
        rejected = [
            {"token": t.symbol, "reason": r.reason}
            for t, r in filter_results if not r.passed
        ]
        logger.info("Passed filter: %d | Rejected: %d", len(passed), len(rejected))

        reports: list[TokenReport] = []
        for token in passed[:max_tokens]:
            report = self._analyze_token_cached(token, market_context)
            reports.append(report)

        reports.sort(key=lambda r: r.score, reverse=True)
        recommended = [r for r in reports if r.recommended]
        logger.info(
            "Analysis complete — %d analyzed, %d recommended",
            len(reports), len(recommended),
        )

        return AnalysisResult(
            market_context=market_context,
            total_discovered=len(discovered),
            total_filtered=len(passed),
            total_analyzed=len(reports),
            recommended_tokens=recommended,
            rejected_tokens=rejected,
            all_reports=reports,
        )

    def analyze_specific_token(
        self,
        token_id: str,
        symbol: str,
        name: str,
        contract_address: str = "",
        chain: str = "ethereum",
        narratives: list[str] | None = None,
    ) -> TokenReport:
        """Analyze a single token by its CoinGecko ID or name."""
        market_context = self._get_market_context()
        narr = narratives or market_context.dominant_narratives

        token = DiscoveredToken(
            name=name,
            symbol=symbol,
            contract_address=contract_address or None,
            chain=chain,
            narratives=narr,
        )
        return self._analyze_token(token, market_context)

    # ── Internal pipeline ─────────────────────────────────────────────────

    def _get_market_context(self) -> MarketContext:
        """Fetch market context with a 2-minute in-memory cache."""
        cached = token_cache.get("market_context")
        if cached is not None:
            logger.debug("Using cached market context")
            return cached

        ctx = self.market_analyzer.get_market_condition()
        token_cache.set("market_context", ctx, category="market_data")
        return ctx

    def _analyze_token_cached(
        self, token: DiscoveredToken, market_context: MarketContext
    ) -> TokenReport:
        """Analyze a token, returning a cached result if available."""
        cache_key = f"token_report:{token.symbol.lower()}:{token.chain}"
        cached = token_cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for token report: %s", token.symbol)
            return cached

        report = self._analyze_token(token, market_context)
        token_cache.set(cache_key, report, category="trending")  # 5-min TTL
        return report

    def _analyze_token(
        self, token: DiscoveredToken, market_context: MarketContext
    ) -> TokenReport:
        """Run the full deep analysis on a single token."""
        narratives = token.narratives or market_context.dominant_narratives
        token_id   = token.name.lower().replace(" ", "-")

        logger.debug("Analyzing %s (%s)…", token.symbol, token_id)

        fundamental = self.fundamental_analyzer.analyze(token_id, narratives)

        smart_money = self.smart_money_analyzer.analyze(
            token.contract_address, token.chain, token.price
        )

        technical = self.technical_analyzer.analyze(
            token_id=token_id,
            contract_address=token.contract_address,
            chain=token.chain,
            current_price=token.price,
        )

        risk = self.risk_analyzer.analyze(
            contract_address=token.contract_address,
            chain=token.chain,
            liquidity_usd=token.liquidity_usd,
            market_cap=token.market_cap,
            volume_24h=token.volume_24h,
            top_holders_pct=smart_money.top_holders_pct,
            price_change_24h=token.price_change_24h,
        )

        return self.scoring_engine.score_token(
            name=token.name,
            symbol=token.symbol,
            chain=token.chain,
            contract_address=token.contract_address,
            narratives=narratives,
            fundamental=fundamental,
            smart_money=smart_money,
            technical=technical,
            risk=risk,
        )

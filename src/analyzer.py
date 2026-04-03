"""
Main Analyzer Orchestrator
Coordinates all modules: discovery, filtering, analysis, scoring.
"""

from dataclasses import dataclass, field

from src.market_context import MarketContextAnalyzer, MarketContext
from src.token_discovery import TokenDiscoveryEngine, DiscoveredToken
from src.token_filter import TokenFilter
from src.fundamental_analysis import FundamentalAnalyzer
from src.smart_money import SmartMoneyAnalyzer
from src.technical_analysis import TechnicalAnalyzer
from src.risk_analysis import RiskAnalyzer
from src.scoring import ScoringEngine, TokenReport


@dataclass
class AnalysisResult:
    market_context: MarketContext
    total_discovered: int
    total_filtered: int
    total_analyzed: int
    recommended_tokens: list[TokenReport] = field(default_factory=list)
    rejected_tokens: list[dict] = field(default_factory=list)
    all_reports: list[TokenReport] = field(default_factory=list)


class CryptoTokenAnalyzer:
    """Orchestrates the full token analysis pipeline."""

    def __init__(self):
        self.market_analyzer = MarketContextAnalyzer()
        self.discovery_engine = TokenDiscoveryEngine()
        self.token_filter = TokenFilter()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.smart_money_analyzer = SmartMoneyAnalyzer()
        self.technical_analyzer = TechnicalAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        self.scoring_engine = ScoringEngine()

    def run_full_analysis(self, max_tokens: int = 10) -> AnalysisResult:
        """Run the complete analysis pipeline."""
        # 1. Market Context
        market_context = self.market_analyzer.get_market_condition()

        # 2. Token Discovery
        discovered = self.discovery_engine.discover_tokens(
            market_context.dominant_narratives
        )

        # 3. Filter bad tokens
        filter_results = self.token_filter.batch_filter(discovered)
        passed_tokens = [t for t, r in filter_results if r.passed]
        rejected = [
            {"token": t.symbol, "reason": r.reason}
            for t, r in filter_results
            if not r.passed
        ]

        # 4. Deep analysis on passed tokens (limit to max_tokens)
        reports = []
        for token in passed_tokens[:max_tokens]:
            report = self._analyze_token(token, market_context)
            reports.append(report)

        # 5. Sort by score and filter recommendations
        reports.sort(key=lambda r: r.score, reverse=True)
        recommended = [r for r in reports if r.recommended]

        return AnalysisResult(
            market_context=market_context,
            total_discovered=len(discovered),
            total_filtered=len(passed_tokens),
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
        narratives: list[str] = None,
    ) -> TokenReport:
        """Analyze a specific token by ID."""
        market_context = self.market_analyzer.get_market_condition()
        narr = narratives or market_context.dominant_narratives

        token = DiscoveredToken(
            name=name,
            symbol=symbol,
            contract_address=contract_address or None,
            chain=chain,
            narratives=narr,
        )

        return self._analyze_token(token, market_context)

    def _analyze_token(
        self, token: DiscoveredToken, market_context: MarketContext
    ) -> TokenReport:
        """Run deep analysis on a single token."""
        narratives = token.narratives or market_context.dominant_narratives
        token_id = token.name.lower().replace(" ", "-")

        # Fundamental Analysis
        fundamental = self.fundamental_analyzer.analyze(token_id, narratives)

        # Smart Money Analysis
        smart_money = self.smart_money_analyzer.analyze(
            token.contract_address, token.chain, token.price
        )

        # Technical Analysis
        technical = self.technical_analyzer.analyze(
            token_id=token_id,
            contract_address=token.contract_address,
            chain=token.chain,
            current_price=token.price,
        )

        # Risk Analysis
        risk = self.risk_analyzer.analyze(
            contract_address=token.contract_address,
            chain=token.chain,
            liquidity_usd=token.liquidity_usd,
            market_cap=token.market_cap,
            volume_24h=token.volume_24h,
            top_holders_pct=smart_money.top_holders_pct,
            price_change_24h=token.price_change_24h,
        )

        # Scoring
        report = self.scoring_engine.score_token(
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

        return report

"""
src/fundamental_analysis.py
============================
Fundamental analysis for crypto tokens.

Public API (standalone functions)
----------------------------------
    get_token_info(ca, chain)           fetch + normalise token data
    check_liquidity(token_data)         liquidity depth & quality
    check_holder_distribution(td)       concentration risk
    check_contract_safety(td)           honeypot, mint, blacklist, proxy …
    analyze_community_metrics(td)       Twitter, Reddit, GitHub activity
    calculate_fundamental_score(fd)     aggregate sub-scores → 0-10 float
    analyze_fundamentals(td)            run all checks, return full dict

Class API (backward-compatible with analyzer.py)
-------------------------------------------------
    FundamentalAnalyzer.analyze(token_id, narratives) → FundamentalScore
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import requests

from config.settings import cfg, COINGECKO_BASE_URL, DEXSCREENER_BASE_URL
from utils.cache import token_cache
from utils.retry import retry_on_failure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FundamentalScore:
    """Structured output of the fundamental analysis (used by ScoringEngine)."""

    narrative_strength: float = 0.0   # 0-10
    team_quality: float = 0.0         # 0-10
    utility_score: float = 0.0        # 0-10
    community_strength: float = 0.0   # 0-10
    partnership_score: float = 0.0    # 0-10
    # --- fields added in v2 (backward-compatible: have defaults) ---
    liquidity_score: float = 0.0      # 0-10
    safety_score: float = 0.0         # 0-10
    holder_score: float = 0.0         # 0-10
    overall: float = 0.0              # 0-10 composite
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sub-score weights for calculate_fundamental_score()
# (must sum to 1.0)
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "narrative":  0.20,
    "team":       0.15,
    "utility":    0.15,
    "community":  0.10,
    "backers":    0.10,
    "liquidity":  0.15,
    "safety":     0.10,
    "holders":    0.05,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9, "Fundamental weights must sum to 1.0"


# ===========================================================================
# PUBLIC STANDALONE FUNCTIONS
# ===========================================================================

def get_token_info(ca: str, chain: str = "ethereum") -> dict:
    """
    Fetch and normalise token info from multiple sources by contract address.

    Strategy: DEXScreener (no key, fast) → CoinGecko (richer metadata).
    Both results are merged into a single normalised dict.

    Returns an empty dict if all sources fail.
    """
    info: dict = {"contract_address": ca, "chain": chain}

    dex_data = _fetch_dexscreener_token(ca)
    if dex_data:
        info.update(dex_data)

    cg_id = _resolve_coingecko_id(ca, chain)
    if cg_id:
        cg_raw = _fetch_coingecko_coin(cg_id)
        if cg_raw:
            _merge_coingecko_into(info, cg_raw)

    return info


def check_liquidity(token_data: dict) -> dict:
    """
    Assess liquidity depth and quality.

    Returns
    -------
    {
        usd            : float,
        score          : float (0-10, higher=safer),
        status         : "excellent"|"good"|"adequate"|"low"|"critical"|"unknown",
        mc_to_liq_ratio: float,
        vol_to_liq_ratio: float,
        warnings       : list[str],
    }
    """
    liq_usd    = float(token_data.get("liquidity_usd",  0) or 0)
    market_cap = float(token_data.get("market_cap",     0) or 0)
    vol_24h    = float(token_data.get("volume_24h",     0) or 0)
    warnings: list[str] = []

    # --- absolute liquidity score ---
    if liq_usd >= 2_000_000:
        score, status = 10.0, "excellent"
    elif liq_usd >= 500_000:
        score, status = 8.0,  "good"
    elif liq_usd >= 100_000:
        score, status = 7.0,  "adequate"
    elif liq_usd >= cfg.filters.min_liquidity_usd:
        score, status = 5.0,  "low"
    elif liq_usd > 0:
        score, status = 2.0,  "critical"
        warnings.append(f"Critically low liquidity: ${liq_usd:,.0f}")
    else:
        score, status = 5.0,  "unknown"

    # --- MC / Liquidity ratio ---
    mc_liq = round(market_cap / liq_usd, 2) if liq_usd > 0 else 0.0
    if mc_liq > cfg.filters.max_mc_to_liquidity_ratio:
        penalty = min(3.0, (mc_liq - cfg.filters.max_mc_to_liquidity_ratio) / 10)
        score   = max(1.0, score - penalty)
        warnings.append(f"High MC/Liquidity ratio: {mc_liq:.1f}x (exit risk)")

    # --- Volume / Liquidity ratio ---
    vol_liq = vol_24h / liq_usd if liq_usd > 0 else 0.0
    if 0 < vol_liq < cfg.filters.min_vol_to_liquidity_pct / 100:
        score = max(1.0, score - 1.0)
        warnings.append("Very low volume relative to liquidity — low real demand")

    return {
        "usd":              liq_usd,
        "score":            round(min(10.0, max(1.0, score)), 1),
        "status":           status,
        "mc_to_liq_ratio":  mc_liq,
        "vol_to_liq_ratio": round(vol_liq, 4),
        "warnings":         warnings,
    }


def check_holder_distribution(token_data: dict) -> dict:
    """
    Analyse token holder concentration.

    Returns
    -------
    {
        top10_pct      : float,
        unique_holders : int,
        score          : float (0-10, higher = better distributed),
        risk           : "very_low"|"low"|"moderate"|"high"|"extreme"|"unknown",
        warnings       : list[str],
    }
    """
    top10   = float(token_data.get("top10_holders_pct", 0) or 0)
    holders = int(token_data.get("unique_holders",     0) or 0)
    sm      = cfg.smart_money
    warnings: list[str] = []

    if top10 == 0:
        score, risk = 5.0, "unknown"
    elif top10 >= sm.concentration_extreme_pct:
        score, risk = 2.0, "extreme"
        warnings.append(f"Top-10 wallets hold {top10:.0f}% — extreme rug risk")
    elif top10 >= sm.concentration_high_pct:
        score, risk = 4.0, "high"
        warnings.append(f"Top-10 wallets hold {top10:.0f}%")
    elif top10 >= sm.concentration_moderate_pct:
        score, risk = 6.0, "moderate"
    elif top10 >= sm.max_top10_concentration_pct:
        score, risk = 7.5, "low"
    else:
        score, risk = 9.0, "very_low"

    if holders > 10_000:
        score = min(10.0, score + 1.0)
    elif 0 < holders < sm.min_unique_addrs_for_buzz:
        score = max(1.0, score - 1.0)
        warnings.append(f"Very few unique holders: {holders}")

    return {
        "top10_pct":      top10,
        "unique_holders": holders,
        "score":          round(min(10.0, max(1.0, score)), 1),
        "risk":           risk,
        "warnings":       warnings,
    }


def check_contract_safety(token_data: dict) -> dict:
    """
    Evaluate smart-contract safety.

    Checks performed (where API keys / chain are available):
    - Honeypot detection (honeypot.is API — Ethereum + BSC)
    - Buy / sell tax estimation
    - Etherscan source verification
    - Dangerous functions: mint, blacklist, pause, selfdestruct, fee-setter
    - Upgradeable proxy pattern

    Returns
    -------
    {
        verified           : bool,
        is_proxy           : bool,
        is_honeypot        : bool,
        has_mint           : bool,
        has_blacklist      : bool,
        has_pause          : bool,
        has_selfdestruct   : bool,
        has_fee_modification: bool,
        buy_tax_pct        : float,
        sell_tax_pct       : float,
        score              : float (0-10, higher = safer),
        warnings           : list[str],
    }
    """
    ca    = token_data.get("contract_address", "")
    chain = token_data.get("chain", "ethereum")
    warnings: list[str] = []
    score = 7.0  # neutral start; verified & clean contracts gain points

    result: dict = {
        "verified":            False,
        "is_proxy":            False,
        "is_honeypot":         False,
        "has_mint":            False,
        "has_blacklist":       False,
        "has_pause":           False,
        "has_selfdestruct":    False,
        "has_fee_modification":False,
        "buy_tax_pct":         0.0,
        "sell_tax_pct":        0.0,
        "score":               5.5,
        "warnings":            [],
    }

    if not ca or chain not in ("ethereum", "bsc"):
        # Non-EVM or no address → neutral score, no checks possible
        result["score"] = 5.5
        return result

    # ── Honeypot check ────────────────────────────────────────────────────
    hp = _check_honeypot_api(ca, chain)
    if hp:
        result["is_honeypot"]  = hp.get("is_honeypot", False)
        result["buy_tax_pct"]  = hp.get("buy_tax",  0.0)
        result["sell_tax_pct"] = hp.get("sell_tax", 0.0)

        if result["is_honeypot"]:
            score -= 8.0
            warnings.append("HONEYPOT — tokens cannot be sold")
        if result["sell_tax_pct"] > 15:
            score -= 2.0
            warnings.append(f"High sell tax: {result['sell_tax_pct']:.1f}%")
        elif result["sell_tax_pct"] > 5:
            score -= 1.0
            warnings.append(f"Elevated sell tax: {result['sell_tax_pct']:.1f}%")

    # ── Etherscan source code check ───────────────────────────────────────
    if chain == "ethereum" and cfg.api.etherscan.api_key:
        src = _fetch_contract_source(ca)
        if src:
            result["verified"] = src.get("verified", False)
            result["is_proxy"] = src.get("is_proxy",  False)
            source_lower = src.get("source_code", "").lower()

            if result["verified"]:
                score += 1.0
            else:
                score -= 3.0
                warnings.append("Contract NOT verified on Etherscan")

            if result["is_proxy"]:
                score -= 1.0
                warnings.append("Upgradeable proxy — logic can be replaced by owner")

            _DANGEROUS: dict[str, tuple[str, str]] = {
                "mint":           ("has_mint",             "Mint function — supply inflation possible"),
                "blacklist":      ("has_blacklist",        "Blacklist — wallets can be blocked"),
                "_isblacklisted": ("has_blacklist",        ""),
                "pause":          ("has_pause",            "Pausable — transfers can be frozen"),
                "selfdestruct":   ("has_selfdestruct",     "Self-destruct function present"),
                "suicide":        ("has_selfdestruct",     ""),
                "setfee":         ("has_fee_modification", "Fees can be changed by owner"),
                "settax":         ("has_fee_modification", ""),
                "updatefee":      ("has_fee_modification", ""),
            }
            for kw, (flag, msg) in _DANGEROUS.items():
                if kw in source_lower:
                    result[flag] = True
                    if msg:  # avoid duplicate warnings for aliased keywords
                        score -= 1.0
                        warnings.append(msg)
        else:
            score -= 2.0
            warnings.append("Could not retrieve contract source — treating as unverified")
    else:
        score = 5.5  # No Etherscan key or non-ETH chain → default neutral

    result["score"]    = round(min(10.0, max(1.0, score)), 1)
    result["warnings"] = list(dict.fromkeys(warnings))  # preserve order, deduplicate
    return result


def analyze_community_metrics(token_data: dict) -> dict:
    """
    Score social and developer community metrics.

    Returns
    -------
    {
        twitter_followers  : int,
        reddit_subscribers : int,
        github_commits_4w  : int,
        github_contributors: int,
        score              : float (0-10),
    }
    """
    twitter      = int(token_data.get("twitter_followers",   0) or 0)
    reddit       = int(token_data.get("reddit_subscribers",  0) or 0)
    commits      = int(token_data.get("github_commits_4w",   0) or 0)
    contributors = int(token_data.get("github_contributors", 0) or 0)
    score = 5.0

    # Twitter followers
    if twitter > 500_000:  score += 2.5
    elif twitter > 100_000: score += 2.0
    elif twitter > 50_000:  score += 1.5
    elif twitter > 10_000:  score += 1.0
    elif twitter > 1_000:   score += 0.5
    elif 0 < twitter < 500: score -= 1.0

    # Reddit subscribers
    if reddit > 100_000:  score += 1.0
    elif reddit > 20_000: score += 0.5

    # GitHub: commits in the last 4 weeks
    if commits > 200:      score += 1.5
    elif commits > 100:    score += 1.0
    elif commits > 30:     score += 0.5
    elif commits == 0 and contributors == 0:
        score -= 1.0  # zero dev activity is a yellow flag

    if contributors > 20:  score += 0.5

    return {
        "twitter_followers":   twitter,
        "reddit_subscribers":  reddit,
        "github_commits_4w":   commits,
        "github_contributors": contributors,
        "score":               round(min(10.0, max(1.0, score)), 1),
    }


def calculate_fundamental_score(fund_data: dict) -> float:
    """
    Aggregate sub-analysis results into a single composite score (0-10).

    fund_data is expected to be the output of analyze_fundamentals().
    Missing keys fall back to 5.0.
    """
    raw: dict[str, float] = {
        "narrative": fund_data.get("narrative",          {}).get("score", 5.0),
        "team":      fund_data.get("team",               {}).get("score", 5.0),
        "utility":   fund_data.get("utility",            {}).get("score", 5.0),
        "community": fund_data.get("community",          {}).get("score", 5.0),
        "backers":   fund_data.get("backers",            {}).get("score", 5.0),
        "liquidity": fund_data.get("liquidity",          {}).get("score", 5.0),
        "safety":    fund_data.get("contract_safety",    {}).get("score", 5.5),
        "holders":   fund_data.get("holder_distribution",{}).get("score", 5.0),
    }
    composite = sum(raw[k] * _WEIGHTS[k] for k in _WEIGHTS)
    return round(min(10.0, max(1.0, composite)), 1)


def analyze_fundamentals(token_data: dict) -> dict:
    """
    Main entry point: run all fundamental checks and return a full analysis dict.

    Parameters
    ----------
    token_data : dict
        Normalised token info (from get_token_info() or manually populated).
        Expected keys: contract_address, chain, liquidity_usd, market_cap,
        volume_24h, top10_holders_pct, unique_holders, description, categories,
        narratives, twitter_followers, reddit_subscribers, github_commits_4w,
        github_contributors, github_repos.

    Returns
    -------
    dict with keys:
        liquidity, holder_distribution, contract_safety, community, narrative,
        team, backers, utility, red_flags, green_flags, overall_score
    """
    narratives   = token_data.get("narratives",  [])
    description  = (token_data.get("description", "") or "").lower()
    categories   = [c.lower() for c in (token_data.get("categories", []) or [])]

    liquidity    = check_liquidity(token_data)
    holders      = check_holder_distribution(token_data)
    safety       = check_contract_safety(token_data)
    community    = analyze_community_metrics(token_data)
    narrative    = _score_narrative(narratives, description, categories)
    team         = _score_team(token_data)
    backers      = _score_backers(description)
    utility      = _score_utility(description, categories)

    # Aggregate flags
    red_flags: list[str] = (
        liquidity.get("warnings", [])
        + holders.get("warnings", [])
        + safety.get("warnings", [])
    )
    green_flags: list[str] = []
    if safety.get("verified"):
        green_flags.append("Contract verified on Etherscan")
    if narrative["score"] >= 8:
        green_flags.append(f"Strong narrative: {', '.join(narrative['matched'])}")
    if holders["risk"] in ("low", "very_low"):
        green_flags.append("Well-distributed token supply")
    if community["github_commits_4w"] > 30:
        green_flags.append("Active open-source development")
    if not safety.get("has_mint") and safety.get("verified"):
        green_flags.append("No mint function — fixed supply")

    fund_data = {
        "liquidity":           liquidity,
        "holder_distribution": holders,
        "contract_safety":     safety,
        "community":           community,
        "narrative":           narrative,
        "team":                team,
        "backers":             backers,
        "utility":             utility,
        "red_flags":           red_flags,
        "green_flags":         green_flags,
    }
    fund_data["overall_score"] = calculate_fundamental_score(fund_data)
    return fund_data


# ===========================================================================
# FundamentalAnalyzer — backward-compatible class interface
# ===========================================================================

class FundamentalAnalyzer:
    """
    Class adapter that wraps the standalone functions into the original
    interface consumed by src/analyzer.py.

    The heavy lifting is done by the module-level standalone functions.
    This class only handles data fetching and type conversion.
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def analyze(self, token_id: str, narratives: list[str]) -> FundamentalScore:
        """
        Fetch data for token_id, run all fundamental checks, return FundamentalScore.

        Falls back to a narrative-only estimate when CoinGecko is unavailable.
        """
        coin_raw = self._fetch_coin_data(token_id)
        if not coin_raw:
            logger.warning("No CoinGecko data for %s — estimating from narrative", token_id)
            return self._estimate_from_narratives(narratives)

        token_data = _normalise_coingecko(coin_raw)
        token_data["narratives"] = narratives

        fund = analyze_fundamentals(token_data)

        return FundamentalScore(
            narrative_strength=fund["narrative"]["score"],
            team_quality=       fund["team"]["score"],
            utility_score=      fund["utility"]["score"],
            community_strength= fund["community"]["score"],
            partnership_score=  fund["backers"]["score"],
            liquidity_score=    fund["liquidity"]["score"],
            safety_score=       fund["contract_safety"]["score"],
            holder_score=       fund["holder_distribution"]["score"],
            overall=            fund["overall_score"],
            details={
                "description":     (coin_raw.get("description", {}).get("en", "") or "")[:300],
                "categories":       coin_raw.get("categories", []),
                "red_flags":        fund["red_flags"],
                "green_flags":      fund["green_flags"],
                "contract_safety":  fund["contract_safety"],
                "liquidity":        fund["liquidity"],
                "holder_distribution": fund["holder_distribution"],
                "links": {
                    "website": coin_raw.get("links", {}).get("homepage", []),
                    "twitter": coin_raw.get("links", {}).get("twitter_screen_name", ""),
                    "github":  coin_raw.get("links", {}).get("repos_url", {}).get("github", []),
                },
            },
        )

    @token_cache.cached("fa_coin", category="coin_detail")
    @retry_on_failure(max_retries=3, delay=1.5, exceptions=(requests.RequestException,))
    def _fetch_coin_data(self, token_id: str) -> Optional[dict]:
        """CoinGecko full coin detail — cached and retried."""
        resp = self._session.get(
            f"{COINGECKO_BASE_URL}/coins/{token_id}",
            params={
                "localization":   False,
                "tickers":        False,
                "market_data":    True,
                "community_data": True,
                "developer_data": True,
            },
            timeout=cfg.api.coingecko.timeout_s,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _estimate_from_narratives(narratives: list[str]) -> FundamentalScore:
        narr_score = float(max(
            (cfg.narratives.strength_scores.get(n, cfg.narratives.default_strength)
             for n in narratives),
            default=float(cfg.narratives.default_strength),
        ))
        overall = round(narr_score * 0.40 + 5.0 * 0.60, 1)
        return FundamentalScore(
            narrative_strength=narr_score,
            team_quality=5.0,
            utility_score=5.0,
            community_strength=5.0,
            partnership_score=5.0,
            liquidity_score=5.0,
            safety_score=5.5,
            holder_score=5.0,
            overall=overall,
            details={"note": "Estimated from narrative only — CoinGecko unavailable"},
        )


# ===========================================================================
# Private helpers (module-level, also cached/retried)
# ===========================================================================

@token_cache.cached("dex_token", category="market_data")
@retry_on_failure(max_retries=2, delay=1.0, exceptions=(requests.RequestException,))
def _fetch_dexscreener_token(ca: str) -> dict:
    """Fetch best pair for a contract address from DEXScreener."""
    session = requests.Session()
    resp = session.get(
        f"{DEXSCREENER_BASE_URL}/dex/tokens/{ca}",
        timeout=cfg.api.dexscreener.timeout_s,
    )
    resp.raise_for_status()
    pairs = resp.json().get("pairs") or []
    if not pairs:
        return {}

    best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0)))
    base = best.get("baseToken", {})
    liq  = best.get("liquidity", {})
    vol  = best.get("volume",    {})
    pc   = best.get("priceChange", {})
    return {
        "name":             base.get("name",   ""),
        "symbol":           base.get("symbol", ""),
        "price_usd":        float(best.get("priceUsd", 0) or 0),
        "market_cap":       float(best.get("fdv",       0) or 0),
        "liquidity_usd":    float(liq.get("usd",        0) or 0),
        "volume_24h":       float(vol.get("h24",        0) or 0),
        "price_change_24h": float(pc.get("h24",         0) or 0),
        "source":           "dexscreener",
    }


@token_cache.cached("cg_resolve", category="market_data")
@retry_on_failure(max_retries=2, delay=1.0, exceptions=(requests.RequestException,))
def _resolve_coingecko_id(ca: str, chain: str) -> Optional[str]:
    """Resolve a contract address to a CoinGecko coin ID."""
    _PLATFORM_MAP = {
        "ethereum": "ethereum",
        "bsc":      "binance-smart-chain",
        "base":     "base",
        "arbitrum": "arbitrum-one",
        "polygon":  "polygon-pos",
        "solana":   "solana",
    }
    platform = _PLATFORM_MAP.get(chain, "ethereum")
    session  = requests.Session()
    try:
        resp = session.get(
            f"{COINGECKO_BASE_URL}/coins/{platform}/contract/{ca}",
            timeout=cfg.api.coingecko.timeout_s,
        )
        if resp.status_code == 200:
            return resp.json().get("id")
    except requests.RequestException:
        pass
    return None


@token_cache.cached("cg_full", category="coin_detail")
@retry_on_failure(max_retries=3, delay=1.5, exceptions=(requests.RequestException,))
def _fetch_coingecko_coin(coin_id: str) -> Optional[dict]:
    """Fetch full CoinGecko coin data."""
    session = requests.Session()
    resp = session.get(
        f"{COINGECKO_BASE_URL}/coins/{coin_id}",
        params={
            "localization":   False,
            "tickers":        False,
            "market_data":    True,
            "community_data": True,
            "developer_data": True,
        },
        timeout=cfg.api.coingecko.timeout_s,
    )
    resp.raise_for_status()
    return resp.json()


@token_cache.cached("honeypot", category="honeypot")
@retry_on_failure(max_retries=2, delay=1.0, exceptions=(requests.RequestException,))
def _check_honeypot_api(ca: str, chain: str) -> Optional[dict]:
    """
    Call honeypot.is API to detect buy/sell taxes and honeypot behaviour.
    Only available for Ethereum (chainID=1) and BSC (chainID=56).
    """
    _CHAIN_IDS = {"ethereum": 1, "bsc": 56}
    chain_id = _CHAIN_IDS.get(chain)
    if not chain_id:
        return None

    session = requests.Session()
    resp = session.get(
        "https://api.honeypot.is/v2/IsHoneypot",
        params={"address": ca, "chainID": chain_id},
        timeout=8,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    sim  = data.get("simulationResult") or {}
    return {
        "is_honeypot": bool(data.get("isHoneypot", False)),
        "buy_tax":     float(sim.get("buyTax",  0) or 0),
        "sell_tax":    float(sim.get("sellTax", 0) or 0),
    }


@token_cache.cached("contract_src", category="contract")
@retry_on_failure(max_retries=2, delay=2.0, exceptions=(requests.RequestException,))
def _fetch_contract_source(ca: str) -> Optional[dict]:
    """Fetch and parse Etherscan contract source for safety analysis."""
    if not cfg.api.etherscan.api_key:
        return None
    session = requests.Session()
    resp = session.get(
        cfg.endpoints.etherscan,
        params={
            "module":          "contract",
            "action":          "getsourcecode",
            "address":         ca,
            "apikey":          cfg.api.etherscan.api_key,
        },
        timeout=cfg.api.etherscan.timeout_s,
    )
    resp.raise_for_status()
    results = resp.json().get("result", [])
    if not results or not isinstance(results, list):
        return None
    r = results[0]
    return {
        "verified":    r.get("ABI", "") != "Contract source code not verified" and bool(r.get("SourceCode")),
        "is_proxy":    r.get("Proxy", "0") == "1",
        "source_code": r.get("SourceCode", ""),
        "compiler":    r.get("CompilerVersion", ""),
    }


# ── Helper: merge CoinGecko raw response into a normalised dict ──────────────

def _merge_coingecko_into(info: dict, cg: dict) -> None:
    """Merge CoinGecko coin data into a normalised token_data dict (in-place)."""
    md   = cg.get("market_data",    {}) or {}
    dev  = cg.get("developer_data", {}) or {}
    comm = cg.get("community_data", {}) or {}
    links = cg.get("links",         {}) or {}

    info.setdefault("name",   cg.get("name",   ""))
    info.setdefault("symbol", (cg.get("symbol") or "").upper())
    info["description"]          = (cg.get("description", {}) or {}).get("en", "") or ""
    info["categories"]           = cg.get("categories",   [])
    info["github_repos"]         = (links.get("repos_url") or {}).get("github", [])
    info["twitter_followers"]    = comm.get("twitter_followers",       0) or 0
    info["reddit_subscribers"]   = comm.get("reddit_subscribers",      0) or 0
    info["github_commits_4w"]    = dev.get("commit_count_4_weeks",     0) or 0
    info["github_contributors"]  = dev.get("pull_request_contributors",0) or 0

    if md:
        prices = md.get("current_price") or {}
        info["price_usd"]          = float(prices.get("usd", 0) or 0)
        info["market_cap"]         = float((md.get("market_cap")   or {}).get("usd", 0) or 0)
        info["volume_24h"]         = float((md.get("total_volume") or {}).get("usd", 0) or 0)
        info["price_change_24h"]   = float(md.get("price_change_percentage_24h", 0) or 0)
        info["total_supply"]       = float(md.get("total_supply",       0) or 0)
        info["circulating_supply"] = float(md.get("circulating_supply", 0) or 0)


def _normalise_coingecko(cg: dict) -> dict:
    """Build a fresh normalised dict from a raw CoinGecko response."""
    info: dict = {}
    _merge_coingecko_into(info, cg)
    return info


# ── Internal sub-scorers ─────────────────────────────────────────────────────

def _score_narrative(narratives: list[str], description: str, categories: list[str]) -> dict:
    all_text   = description + " " + " ".join(categories)
    matched: list[str] = []

    for name, keywords in cfg.narratives.keywords.items():
        if any(kw in all_text for kw in keywords) or name in narratives:
            if name not in matched:
                matched.append(name)

    # Fall back to the caller-supplied list if auto-detection found nothing
    if not matched:
        matched = list(narratives)

    top = max(
        (cfg.narratives.strength_scores.get(n, cfg.narratives.default_strength) for n in matched),
        default=float(cfg.narratives.default_strength),
    )
    return {"matched": matched, "score": float(min(10, max(1, top)))}


def _score_team(token_data: dict) -> dict:
    commits      = int(token_data.get("github_commits_4w",   0) or 0)
    contributors = int(token_data.get("github_contributors", 0) or 0)
    has_repo     = bool(token_data.get("github_repos"))
    score = 5.0

    if commits > 200:   score += 3.0;  velocity = "very_high"
    elif commits > 100: score += 2.0;  velocity = "high"
    elif commits > 30:  score += 1.0;  velocity = "moderate"
    elif commits > 0:                  velocity = "low"
    else:               score -= 2.0;  velocity = "none"

    if contributors > 20:  score += 1.5
    elif contributors > 5: score += 0.5

    score += 0.5 if has_repo else -1.0

    return {
        "commit_velocity": velocity,
        "commits_4w":      commits,
        "contributors":    contributors,
        "github_active":   commits > 0,
        "score":           round(min(10.0, max(1.0, score)), 1),
    }


def _score_backers(description: str) -> dict:
    _KNOWN: dict[str, float] = {
        "a16z": 10, "paradigm": 10, "sequoia": 9, "binance labs": 8,
        "coinbase ventures": 8, "polychain": 8, "multicoin": 7,
        "framework ventures": 7, "pantera": 7, "dragonfly": 7,
        "delphi digital": 6, "jump crypto": 7, "wintermute": 6,
        "alameda": 2,  # penalised
    }
    found: list[str] = []
    score = 5.0
    desc  = description.lower()
    for backer, s in _KNOWN.items():
        if backer in desc:
            found.append(backer)
            score = max(score, s)
    return {"known_backers": found, "score": round(min(10.0, max(1.0, score)), 1)}


def _score_utility(description: str, categories: list[str]) -> dict:
    score = 5.0
    _KEYWORDS = [
        "governance", "staking", "fee", "burn", "revenue", "protocol",
        "platform", "infrastructure", "oracle", "settlement", "collateral",
    ]
    for kw in _KEYWORDS:
        if kw in description:
            score += 0.4
    if any("platform" in c or "infrastructure" in c for c in categories):
        score += 1.0
    return {"score": round(min(10.0, max(1.0, score)), 1)}

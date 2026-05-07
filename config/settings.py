"""
config/settings.py
==================
Single source of truth for the Crypto Token Analyzer.

Structure
---------
  PathConfig          – data / cache / log directories
  APIConfig           – keys, timeouts, retries, rate limits (per provider)
  EndpointConfig      – all base URLs (REST + chain RPCs)
  FilterConfig        – discovery filters (market-cap buckets, pump guard, etc.)
  SmartMoneyConfig    – whale thresholds, concentration limits, known wallets
  ScoringConfig       – dimension weights (must sum to 1.0), pass threshold
  SMCConfig           – Smart Money Concepts technical parameters
  NarrativeConfig     – narrative keywords and their base strength scores
  ChainConfig         – per-chain metadata (native token, explorer, DEX)
  AppConfig           – master config assembled from all sub-configs

Usage
-----
  from config.settings import cfg          # full config object
  from config.settings import SCORING_WEIGHTS  # legacy flat constant

All module-level flat constants at the bottom remain for backward compatibility
with the existing src/ imports.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# 1. PATHS
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PathConfig:
    """Filesystem paths used by the analyzer."""

    root: Path = _ROOT
    data_dir: Path = _ROOT / "data"
    cache_dir: Path = _ROOT / "data" / "cache"
    logs_dir: Path = _ROOT / "data" / "logs"
    reports_dir: Path = _ROOT / "data" / "reports"

    def ensure_dirs(self) -> None:
        """Create all directories if they do not exist yet."""
        for d in (self.data_dir, self.cache_dir, self.logs_dir, self.reports_dir):
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 2. API KEYS & CONNECTION SETTINGS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderAPIConfig:
    """Connection parameters for a single external API provider."""

    api_key: str = ""
    timeout_s: int = 10          # seconds per request
    max_retries: int = 3
    retry_backoff_s: float = 1.5 # exponential base: 1.5s, 2.25s, 3.375s ...
    # Requests per minute allowed by the free/paid tier
    rate_limit_rpm: int = 30
    # Minimum seconds to wait between consecutive requests (derived from rpm)
    min_delay_s: float = field(init=False)

    def __post_init__(self) -> None:
        # frozen=True → use object.__setattr__ for computed field
        object.__setattr__(self, "min_delay_s", round(60 / max(self.rate_limit_rpm, 1), 3))


@dataclass(frozen=True)
class APIConfig:
    """Aggregated API credentials and limits for every provider."""

    coingecko: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            api_key=os.getenv("COINGECKO_API_KEY", ""),
            timeout_s=10,
            max_retries=3,
            retry_backoff_s=1.5,
            # Free tier: 30 rpm; Pro tier can be 500 rpm
            rate_limit_rpm=int(os.getenv("COINGECKO_RPM", "30")),
        )
    )
    dexscreener: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            api_key=os.getenv("DEXSCREENER_API_KEY", ""),
            timeout_s=8,
            max_retries=3,
            retry_backoff_s=1.0,
            rate_limit_rpm=60,   # Public endpoint, generous limit
        )
    )
    etherscan: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            api_key=os.getenv("ETHERSCAN_API_KEY", ""),
            timeout_s=10,
            max_retries=2,
            retry_backoff_s=2.0,
            rate_limit_rpm=int(os.getenv("ETHERSCAN_RPM", "5")),  # Free: 5 rpm
        )
    )
    birdeye: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            api_key=os.getenv("BIRDEYE_API_KEY", ""),
            timeout_s=10,
            max_retries=2,
            retry_backoff_s=1.5,
            rate_limit_rpm=30,
        )
    )
    defillama: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            # DefiLlama is fully public — no key needed
            api_key="",
            timeout_s=12,
            max_retries=3,
            retry_backoff_s=1.0,
            rate_limit_rpm=60,
        )
    )
    alternative_me: ProviderAPIConfig = field(
        default_factory=lambda: ProviderAPIConfig(
            api_key="",
            timeout_s=8,
            max_retries=2,
            retry_backoff_s=1.0,
            rate_limit_rpm=10,
        )
    )


# ---------------------------------------------------------------------------
# 3. BASE URLS / ENDPOINTS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EndpointConfig:
    """All REST base URLs. Chain-specific RPCs are in ChainConfig."""

    coingecko: str = "https://api.coingecko.com/api/v3"
    # Pro tier — only used when COINGECKO_API_KEY is set
    coingecko_pro: str = "https://pro-api.coingecko.com/api/v3"
    dexscreener: str = "https://api.dexscreener.com/latest"
    etherscan: str = "https://api.etherscan.io/api"
    bscscan: str = "https://api.bscscan.com/api"
    basescan: str = "https://api.basescan.org/api"
    arbiscan: str = "https://api.arbiscan.io/api"
    birdeye: str = "https://public-api.birdeye.so"
    defillama: str = "https://api.llama.fi"
    fear_greed: str = "https://api.alternative.me/fng"

    def coingecko_effective(self, api_key: str) -> str:
        """Return pro URL when a key is configured, public otherwise."""
        return self.coingecko_pro if api_key else self.coingecko


# ---------------------------------------------------------------------------
# 4. DISCOVERY FILTERS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FilterConfig:
    """
    Hard limits applied during the token discovery phase.

    Tune these to shift between conservative (tight) and aggressive (loose)
    scanning without touching any logic code.
    """

    # ── Market Cap Buckets (USD) ──────────────────────────────────────────
    # Tokens above LOW_CAP_MAX are too large for 2-10x targets.
    micro_cap_max: float = 10_000_000      # < $10 M  → moonshot territory
    low_cap_max: float = 50_000_000        # < $50 M  → primary sweet spot
    mid_cap_max: float = 250_000_000       # < $250 M → still viable if narrative is hot

    # Absolute maximum FDV accepted into the pipeline
    max_fdv_usd: float = 100_000_000       # reject anything fully-diluted > $100 M

    # ── Liquidity ─────────────────────────────────────────────────────────
    # Below this the spread + slippage makes the trade non-viable.
    min_liquidity_usd: float = 50_000

    # Ratio guard: if market_cap / liquidity > this, exit risk is too high.
    max_mc_to_liquidity_ratio: float = 40.0

    # ── Volume ────────────────────────────────────────────────────────────
    min_volume_24h_usd: float = 5_000       # absolute floor
    # Minimum 24 h volume as a % of total liquidity (proxy for real interest)
    min_vol_to_liquidity_pct: float = 5.0
    # Flag a token when 24 h volume surges by at least this % vs prior day
    min_volume_increase_pct: float = 50.0

    # ── Pump Guard ────────────────────────────────────────────────────────
    # Reject tokens already extended beyond these thresholds.
    max_24h_pump_pct: float = 100.0         # > 100 % in a day → chasing
    max_7d_pump_pct: float = 300.0          # > 300 % in a week → overextended
    max_30d_pump_pct: float = 1000.0        # > 1000 % in a month → exit zone

    # Minimum drawdown from ATH before a token is "interesting again"
    min_drawdown_from_ath_pct: float = 30.0

    # ── Age / Maturity ────────────────────────────────────────────────────
    # Ignore brand-new tokens younger than this (hours) – too risky at launch
    min_token_age_hours: int = 48

    # ── Holder Count ─────────────────────────────────────────────────────
    min_unique_holders: int = 100           # absolute floor; < 100 is likely a test token

    # ── Discovery Batch Sizes ─────────────────────────────────────────────
    max_tokens_per_source: int = 20
    max_tokens_for_deep_analysis: int = 10


# ---------------------------------------------------------------------------
# 5. SMART MONEY & ON-CHAIN
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmartMoneyConfig:
    """
    Parameters for whale detection and wallet distribution analysis.
    """

    # ── Whale Size ────────────────────────────────────────────────────────
    # Single transaction value (USD) that qualifies as a whale move.
    whale_tx_threshold_usd: float = 100_000
    # Minimum token units (fallback when price data is absent)
    whale_tx_threshold_tokens: float = 1_000_000

    # ── Smart Money Detection ─────────────────────────────────────────────
    # A wallet must have made at least this many buys to be flagged as
    # "smart money accumulation" rather than a lucky one-off.
    smart_money_min_txns: int = 3

    # Look-back window for recent whale activity (hours)
    activity_lookback_hours: int = 72

    # ── Wallet Concentration ──────────────────────────────────────────────
    # Top-10 holders owning more than this % triggers a concentration flag.
    max_top10_concentration_pct: float = 25.0

    # Thresholds that map concentration % → risk rating
    concentration_extreme_pct: float = 80.0  # score ≤ 2 / 10
    concentration_high_pct: float = 60.0     # score ≤ 4 / 10
    concentration_moderate_pct: float = 40.0 # score ≤ 6 / 10
    # Below moderate_pct → healthy distribution → score ≥ 7

    # ── Known Smart-Money Wallets (Ethereum, lowercase) ───────────────────
    known_smart_wallets: tuple[str, ...] = (
        "0x28c6c06298d514db089934071355e5743bf21d60",  # Binance: Hot Wallet 1
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549",  # Jump Trading
        "0xdbf5e9c5206d0db70a90108bf936da60221dc080",  # Wintermute
        "0x9696f59e4d72e237be84ffd425dcad154bf96976",  # Wintermute 2
        "0x4862733b5fddfd35f35ea8ccf08f5045e57388b3",  # DWF Labs
        "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621",  # Alameda (penalised in scorer)
    )

    # ── Anomaly Detection ─────────────────────────────────────────────────
    # Number of unique addresses in the look-back window that signals buzz.
    min_unique_addrs_for_buzz: int = 30
    # Minimum raw transaction count to flag "high activity"
    min_txns_for_high_activity: int = 50


# ---------------------------------------------------------------------------
# 6. SCORING
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringConfig:
    """
    Composite score weights.

    All four weights MUST sum to exactly 1.0.
    Final score is on a 1–10 scale; only tokens ≥ pass_threshold are surfaced.
    """

    # ── Dimension Weights ─────────────────────────────────────────────────
    weight_narrative: float = 0.25    # Narrative strength & trend alignment
    weight_smart_money: float = 0.25  # Whale activity + wallet health
    weight_risk: float = 0.25         # Liquidity, rug-pull, tokenomics safety
    weight_entry_timing: float = 0.25 # SMC entry quality (are we at demand?)

    # ── Bonus / Penalty Caps ─────────────────────────────────────────────
    max_red_flag_penalty: float = 2.0   # Total points deducted per red flag batch
    red_flag_penalty_each: float = 0.30 # Points lost per individual red flag
    bullish_trend_bonus: float = 0.50   # Added when trend == "bullish"
    bearish_trend_penalty: float = 0.50 # Subtracted when trend == "bearish"

    # ── Gate ─────────────────────────────────────────────────────────────
    pass_threshold: float = 7.0  # Minimum score to be "recommended"

    def __post_init__(self) -> None:
        total = round(
            self.weight_narrative
            + self.weight_smart_money
            + self.weight_risk
            + self.weight_entry_timing,
            10,
        )
        if total != 1.0:
            raise ValueError(
                f"ScoringConfig weights must sum to 1.0, got {total:.10f}"
            )

    @property
    def as_dict(self) -> dict[str, float]:
        return {
            "narrative_strength": self.weight_narrative,
            "smart_money_activity": self.weight_smart_money,
            "risk_level": self.weight_risk,
            "entry_timing": self.weight_entry_timing,
        }


# ---------------------------------------------------------------------------
# 7. SMC TECHNICAL PARAMETERS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SMCConfig:
    """
    Smart Money Concepts parameters for the technical analysis engine.

    All values are in candle-count or percentage units unless stated otherwise.
    """

    # ── Data Fetching ─────────────────────────────────────────────────────
    # How many days of OHLC history to request (more = slower but richer zones)
    ohlc_days: int = 30
    # Minimum candles needed before the engine attempts any SMC analysis
    min_candles_required: int = 10

    # ── Swing High / Low Detection ────────────────────────────────────────
    # A pivot needs this many candles on each side to qualify as a swing point.
    swing_lookback: int = 2

    # ── Supply / Demand Zones ─────────────────────────────────────────────
    # A zone that has been revisited this many times loses significance.
    max_zone_touches: int = 3
    # Price must be within this % of the zone boundary to count as a "touch"
    zone_tolerance_pct: float = 0.5

    # ── Break of Structure (BOS) ──────────────────────────────────────────
    # Candles after the structural high/low that must confirm the break
    bos_confirmation_candles: int = 1

    # ── Optimal Trade Entry (OTE) ─────────────────────────────────────────
    # Fibonacci retracement band that defines the "sniper zone" inside a move
    ote_fib_low: float = 0.618
    ote_fib_high: float = 0.786

    # ── Moving Averages (trend filter) ────────────────────────────────────
    ma_short_period: int = 7    # fast MA for near-term bias
    ma_long_period: int = 21    # slow MA for structural trend

    # ── Entry Guard ───────────────────────────────────────────────────────
    # Reject an entry if price is more than this % above the top of the demand zone
    max_entry_distance_pct: float = 10.0

    # Default discount if price is below the demand zone (already swept liquidity)
    below_zone_entry_score: float = 8.0
    inside_zone_entry_score: float = 9.0


# ---------------------------------------------------------------------------
# 8. NARRATIVE CONFIG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NarrativeConfig:
    """
    Narrative taxonomy used by the market-context and fundamental modules.

    strength_scores reflect current (2025) market meta — update each quarter.
    """

    # ── Keyword Map (narrative → matching keywords, lowercase) ────────────
    keywords: dict[str, list[str]] = field(default_factory=lambda: {
        "AI":         ["artificial intelligence", " ai ", "machine learning",
                       "gpt", "llm", "neural", "inference", "agent"],
        "DePIN":      ["depin", "decentralized physical", "iot", "sensor",
                       "wireless", "helium", "hotspot", "node"],
        "RWA":        ["real world asset", "rwa", "tokenized", "treasury",
                       "bond", "real estate", "private credit"],
        "L2/Scaling": ["layer 2", " l2 ", "rollup", " zk ", "optimistic",
                       "scaling", "validium", "starknet", "arbitrum", "base"],
        "LST/LSD":    ["liquid staking", "lst", " lsd ", "restaking",
                       "eigenlayer", "liquid restaking", "lrt"],
        "Modular":    ["modular", "data availability", "celestia",
                       "da layer", "rollup-as-a-service"],
        "DeFi":       ["defi", "lending", " dex ", "yield", " amm ",
                       "liquidity", "perp", "derivatives"],
        "SocialFi":   ["socialfi", "social", "friend.tech", "lens",
                       "farcaster", "creator economy"],
        "Gaming":     ["gaming", "gamefi", "metaverse", "nft game",
                       "play to earn", " p2e "],
        "Meme":       ["meme", "doge", "pepe", "shib", "floki",
                       "bonk", "wif", "brett"],
    })

    # ── Narrative Strength Scores (1–10) ──────────────────────────────────
    # Used by FundamentalAnalyzer._score_narratives()
    strength_scores: dict[str, int] = field(default_factory=lambda: {
        "AI":         9,
        "DePIN":      8,
        "RWA":        8,
        "L2/Scaling": 7,
        "LST/LSD":    7,
        "Modular":    7,
        "DeFi":       6,
        "SocialFi":   6,
        "Gaming":     5,
        "Meme":       4,
    })

    # Fallback score when no narrative is matched
    default_strength: int = 4


# ---------------------------------------------------------------------------
# 9. CHAIN CONFIG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SingleChainConfig:
    """Metadata for one supported blockchain."""

    name: str
    chain_id: int
    native_token: str
    block_explorer_api: str
    block_explorer_url: str
    primary_dex: str
    avg_block_time_s: float
    # Whether on-chain holder analysis is implemented for this chain
    holder_analysis_supported: bool = False


@dataclass(frozen=True)
class ChainConfig:
    """All supported chains, keyed by their canonical short name."""

    chains: dict[str, SingleChainConfig] = field(default_factory=lambda: {
        "ethereum": SingleChainConfig(
            name="Ethereum",
            chain_id=1,
            native_token="ETH",
            block_explorer_api="https://api.etherscan.io/api",
            block_explorer_url="https://etherscan.io",
            primary_dex="uniswap_v3",
            avg_block_time_s=12.0,
            holder_analysis_supported=True,
        ),
        "bsc": SingleChainConfig(
            name="BNB Smart Chain",
            chain_id=56,
            native_token="BNB",
            block_explorer_api="https://api.bscscan.com/api",
            block_explorer_url="https://bscscan.com",
            primary_dex="pancakeswap_v3",
            avg_block_time_s=3.0,
            holder_analysis_supported=False,
        ),
        "base": SingleChainConfig(
            name="Base",
            chain_id=8453,
            native_token="ETH",
            block_explorer_api="https://api.basescan.org/api",
            block_explorer_url="https://basescan.org",
            primary_dex="aerodrome",
            avg_block_time_s=2.0,
            holder_analysis_supported=False,
        ),
        "arbitrum": SingleChainConfig(
            name="Arbitrum One",
            chain_id=42161,
            native_token="ETH",
            block_explorer_api="https://api.arbiscan.io/api",
            block_explorer_url="https://arbiscan.io",
            primary_dex="camelot",
            avg_block_time_s=0.25,
            holder_analysis_supported=False,
        ),
        "solana": SingleChainConfig(
            name="Solana",
            chain_id=0,   # not EVM — chain_id is not meaningful
            native_token="SOL",
            block_explorer_api="https://api.solscan.io",
            block_explorer_url="https://solscan.io",
            primary_dex="raydium",
            avg_block_time_s=0.4,
            holder_analysis_supported=False,
        ),
        "polygon": SingleChainConfig(
            name="Polygon PoS",
            chain_id=137,
            native_token="MATIC",
            block_explorer_api="https://api.polygonscan.com/api",
            block_explorer_url="https://polygonscan.com",
            primary_dex="quickswap",
            avg_block_time_s=2.1,
            holder_analysis_supported=False,
        ),
    })

    default_chain: str = "ethereum"

    def get(self, chain_name: str) -> SingleChainConfig:
        return self.chains.get(chain_name, self.chains[self.default_chain])

    def supported_names(self) -> list[str]:
        return list(self.chains.keys())


# ---------------------------------------------------------------------------
# 10. MASTER APP CONFIG
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    """
    Master configuration object.

    Construct via AppConfig.from_env() to pick up all environment variables.
    All sub-configs are immutable (frozen dataclasses) so settings cannot be
    accidentally mutated at runtime.
    """

    paths: PathConfig = field(default_factory=PathConfig)
    api: APIConfig = field(default_factory=APIConfig)
    endpoints: EndpointConfig = field(default_factory=EndpointConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    smart_money: SmartMoneyConfig = field(default_factory=SmartMoneyConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    smc: SMCConfig = field(default_factory=SMCConfig)
    narratives: NarrativeConfig = field(default_factory=NarrativeConfig)
    chains: ChainConfig = field(default_factory=ChainConfig)

    # ── Global Feature Flags ──────────────────────────────────────────────
    enable_onchain_analysis: bool = field(
        default_factory=lambda: bool(os.getenv("ETHERSCAN_API_KEY"))
    )
    enable_birdeye_solana: bool = field(
        default_factory=lambda: bool(os.getenv("BIRDEYE_API_KEY"))
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    )

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Factory: build a fully-populated AppConfig from the environment."""
        load_dotenv()
        return cls()

    def coingecko_base_url(self) -> str:
        """Return pro URL when key is available, public URL otherwise."""
        return self.endpoints.coingecko_effective(self.api.coingecko.api_key)


# ---------------------------------------------------------------------------
# Singleton — import `cfg` everywhere instead of re-instantiating
# ---------------------------------------------------------------------------

cfg: AppConfig = AppConfig.from_env()


# ---------------------------------------------------------------------------
# BACKWARD-COMPATIBLE FLAT CONSTANTS
# (Every name below is imported by at least one src/ module.)
# Do NOT remove these; update the values from `cfg` so they stay in sync.
# ---------------------------------------------------------------------------

# ── API Keys ──────────────────────────────────────────────────────────────
COINGECKO_API_KEY: str = cfg.api.coingecko.api_key
DEXSCREENER_API_KEY: str = cfg.api.dexscreener.api_key
ETHERSCAN_API_KEY: str = cfg.api.etherscan.api_key

# ── Base URLs ─────────────────────────────────────────────────────────────
COINGECKO_BASE_URL: str = cfg.coingecko_base_url()
DEXSCREENER_BASE_URL: str = cfg.endpoints.dexscreener
ETHERSCAN_BASE_URL: str = cfg.endpoints.etherscan
BIRDEYE_BASE_URL: str = cfg.endpoints.birdeye
DEFILLAMA_BASE_URL: str = cfg.endpoints.defillama

# ── Scoring ───────────────────────────────────────────────────────────────
MIN_SCORE_THRESHOLD: float = cfg.scoring.pass_threshold
SCORING_WEIGHTS: dict[str, float] = cfg.scoring.as_dict

# ── Filters ───────────────────────────────────────────────────────────────
MIN_LIQUIDITY_USD: float = cfg.filters.min_liquidity_usd
MAX_RECENT_PUMP_PCT: float = cfg.filters.max_24h_pump_pct
MIN_VOLUME_INCREASE_PCT: float = cfg.filters.min_volume_increase_pct
MICRO_CAP_MAX: float = cfg.filters.micro_cap_max
LOW_CAP_MAX: float = cfg.filters.low_cap_max
MID_CAP_MAX: float = cfg.filters.mid_cap_max

# ── Smart Money ───────────────────────────────────────────────────────────
MAX_WALLET_CONCENTRATION_PCT: float = cfg.smart_money.max_top10_concentration_pct
WHALE_THRESHOLD_USD: float = cfg.smart_money.whale_tx_threshold_usd
SMART_MONEY_MIN_TXNS: int = cfg.smart_money.smart_money_min_txns

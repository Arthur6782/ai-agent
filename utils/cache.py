"""
utils/cache.py
==============
Two-level cache: fast in-process memory layer backed by a persistent JSON
disk layer.  Designed for caching external API responses.

Usage
-----
    from utils.cache import token_cache

    # Imperative style
    value = token_cache.get("my_key")
    if value is None:
        value = expensive_call()
        token_cache.set("my_key", value, category="coin_detail")

    # Decorator style — works on plain functions AND instance methods
    @token_cache.cached("cg_coin", category="coin_detail")
    def fetch_coin(coin_id: str) -> dict:
        ...

    class MyAnalyzer:
        @token_cache.cached("dex_pair", category="market_data")
        def _fetch_pair(self, address: str) -> dict:
            ...

TTL categories (seconds)
------------------------
    coin_detail   600    (10 min)
    market_data   120    (2 min)
    trending      300    (5 min)
    ohlc          900    (15 min)
    holders       1800   (30 min)
    contract      86400  (24 h)
    honeypot      3600   (1 h)
    defi_tvl      600    (10 min)
    default       300    (5 min)
"""

import hashlib
import inspect
import json
import logging
import time
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-category TTLs (seconds)
# ---------------------------------------------------------------------------

CACHE_TTL: dict[str, int] = {
    "coin_detail": 600,
    "market_data": 120,
    "trending": 300,
    "ohlc": 900,
    "holders": 1_800,
    "contract": 86_400,
    "honeypot": 3_600,
    "defi_tvl": 600,
    "default": 300,
}


# ---------------------------------------------------------------------------
# In-memory layer
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    value: Any
    expires_at: float  # monotonic clock seconds

    def is_alive(self) -> bool:
        return time.monotonic() < self.expires_at


class InMemoryCache:
    """Simple dict-backed cache with TTL.  Not thread-safe (CLI is single-threaded)."""

    def __init__(self) -> None:
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if not entry.is_alive():
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._store[key] = _Entry(value=value, expires_at=time.monotonic() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def evict_expired(self) -> int:
        dead = [k for k, v in self._store.items() if not v.is_alive()]
        for k in dead:
            del self._store[k]
        return len(dead)

    def __len__(self) -> int:
        self.evict_expired()
        return len(self._store)


# ---------------------------------------------------------------------------
# Disk layer
# ---------------------------------------------------------------------------

class DiskCache:
    """
    Persistent JSON cache — one file per entry (SHA-256 hashed filename).
    Survives process restarts within the TTL window.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:20]
        return self._dir / f"c_{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            data: dict = json.loads(path.read_text(encoding="utf-8"))
            if time.time() > data["exp"]:
                path.unlink(missing_ok=True)
                return None
            return data["v"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        path = self._path(key)
        try:
            payload = json.dumps(
                {"v": value, "exp": time.time() + ttl},
                default=str,  # fall back to str() for non-serialisable objects
                ensure_ascii=False,
            )
            path.write_text(payload, encoding="utf-8")
        except (OSError, TypeError, OverflowError) as exc:
            logger.debug("DiskCache.set failed for key=%s: %s", key[:40], exc)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for f in self._dir.glob("c_*.json"):
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Two-level facade
# ---------------------------------------------------------------------------

class TokenCache:
    """
    Two-level cache: checks memory first, falls back to disk.

    The `cached()` decorator transparently handles both plain functions and
    instance methods (detects `self`/`cls` by inspecting the function signature).
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self._mem = InMemoryCache()
        self._disk = DiskCache(cache_dir) if cache_dir else None

    # ── Low-level access ──────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        val = self._mem.get(key)
        if val is not None:
            logger.debug("cache [mem]  HIT  %s", key[:70])
            return val

        if self._disk:
            val = self._disk.get(key)
            if val is not None:
                logger.debug("cache [disk] HIT  %s", key[:70])
                # Promote to memory with a short TTL (we already trust the disk value)
                self._mem.set(key, val, ttl=60)
                return val

        logger.debug("cache        MISS %s", key[:70])
        return None

    def set(self, key: str, value: Any, category: str = "default") -> None:
        ttl = CACHE_TTL.get(category, CACHE_TTL["default"])
        self._mem.set(key, value, ttl=ttl)
        if self._disk:
            self._disk.set(key, value, ttl=ttl)

    def delete(self, key: str) -> None:
        self._mem.delete(key)
        if self._disk:
            self._disk.delete(key)

    def clear_all(self) -> None:
        self._mem.clear()
        if self._disk:
            self._disk.clear()

    def stats(self) -> dict:
        return {"memory_entries": len(self._mem)}

    # ── Decorator ─────────────────────────────────────────────────────────

    def cached(self, prefix: str, category: str = "default") -> Callable:
        """
        Transparent caching decorator for functions and instance methods.

        For instance methods the first parameter (`self` or `cls`) is excluded
        from the cache key so that all instances share the same cache namespace.

        Parameters
        ----------
        prefix : str
            Stable human-readable prefix (e.g. "cg_coin", "dex_pair").
        category : str
            Selects the TTL bucket from CACHE_TTL.
        """
        def decorator(func: Callable) -> Callable:
            # Detect whether the first param is self/cls at decoration time.
            try:
                params = list(inspect.signature(func).parameters.keys())
                skip_first = bool(params) and params[0] in ("self", "cls")
            except (ValueError, TypeError):
                skip_first = False

            @wraps(func)
            def wrapper(*args, **kwargs):
                key_args = args[1:] if skip_first else args
                key = (
                    prefix
                    + ":"
                    + ":".join(str(a) for a in key_args)
                    + (
                        (":" + ":".join(f"{k}={v}" for k, v in sorted(kwargs.items())))
                        if kwargs
                        else ""
                    )
                )

                cached_val = self.get(key)
                if cached_val is not None:
                    return cached_val

                result = func(*args, **kwargs)
                if result is not None:
                    self.set(key, result, category=category)
                return result

            return wrapper

        return decorator


# ---------------------------------------------------------------------------
# Module-level singleton (import this everywhere)
# ---------------------------------------------------------------------------

def _build_singleton() -> TokenCache:
    try:
        from config.settings import cfg
        cache_dir: Optional[Path] = cfg.paths.cache_dir
    except Exception:
        cache_dir = None
    return TokenCache(cache_dir=cache_dir)


token_cache: TokenCache = _build_singleton()

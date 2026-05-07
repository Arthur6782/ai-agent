"""Tests for utils/retry.py and utils/cache.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from utils.retry import retry_on_failure
from utils.cache import InMemoryCache, TokenCache, CACHE_TTL


# ─── retry ────────────────────────────────────────────────────────────────────

def test_retry_succeeds_on_first_try():
    @retry_on_failure(max_retries=3, delay=0, exceptions=(Exception,))
    def ok():
        return "yes"
    assert ok() == "yes"


def test_retry_retries_and_succeeds():
    attempts = []
    @retry_on_failure(max_retries=3, delay=0.001, exceptions=(ValueError,))
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("not yet")
        return "done"
    assert flaky() == "done"
    assert len(attempts) == 3


def test_retry_reraises_after_exhaustion():
    @retry_on_failure(max_retries=2, delay=0.001, exceptions=(RuntimeError,))
    def always_fails():
        raise RuntimeError("boom")
    try:
        always_fails()
        assert False, "Should have raised"
    except RuntimeError as e:
        assert "boom" in str(e)


def test_retry_does_not_catch_unlisted_exception():
    @retry_on_failure(max_retries=3, delay=0.001, exceptions=(ValueError,))
    def raises_type_error():
        raise TypeError("wrong type")
    try:
        raises_type_error()
        assert False
    except TypeError:
        pass  # expected — TypeError is not in the catch list


def test_retry_zero_retries():
    calls = []
    @retry_on_failure(max_retries=0, delay=0, exceptions=(Exception,))
    def single():
        calls.append(1)
        raise Exception("x")
    try:
        single()
    except Exception:
        pass
    assert len(calls) == 1  # no retries, just one attempt


# ─── cache ────────────────────────────────────────────────────────────────────

def test_memory_cache_set_get():
    c = InMemoryCache()
    c.set("k", [1, 2, 3], ttl=60)
    assert c.get("k") == [1, 2, 3]


def test_memory_cache_miss():
    c = InMemoryCache()
    assert c.get("nonexistent") is None


def test_memory_cache_ttl_expiry():
    c = InMemoryCache()
    c.set("tmp", "hello", ttl=1)
    assert c.get("tmp") == "hello"
    time.sleep(1.1)
    assert c.get("tmp") is None


def test_memory_cache_delete():
    c = InMemoryCache()
    c.set("del_me", 99, ttl=60)
    c.delete("del_me")
    assert c.get("del_me") is None


def test_memory_cache_clear():
    c = InMemoryCache()
    c.set("a", 1, ttl=60)
    c.set("b", 2, ttl=60)
    c.clear()
    assert c.get("a") is None
    assert c.get("b") is None


def test_token_cache_set_get():
    tc = TokenCache()  # memory-only (no disk dir)
    tc.set("hello", {"value": 42}, category="default")
    assert tc.get("hello") == {"value": 42}


def test_token_cache_miss_returns_none():
    tc = TokenCache()
    assert tc.get("definitely_not_there_xyz") is None


def test_token_cache_decorator_function():
    tc = TokenCache()
    call_count = [0]

    @tc.cached("test_func", category="default")
    def compute(x: int) -> int:
        call_count[0] += 1
        return x * 10

    tc.delete("test_func:7")  # ensure clean slate
    assert compute(7) == 70
    assert compute(7) == 70   # cache hit
    assert call_count[0] == 1


def test_token_cache_decorator_method():
    tc = TokenCache()

    class Service:
        def __init__(self):
            self.calls = 0

        @tc.cached("svc_fetch", category="default")
        def fetch(self, key: str) -> str:
            self.calls += 1
            return f"result:{key}"

    svc = Service()
    tc.delete("svc_fetch:test_key")
    r1 = svc.fetch("test_key")
    r2 = svc.fetch("test_key")
    assert r1 == r2 == "result:test_key"
    assert svc.calls == 1   # second call was served from cache


def test_token_cache_different_args_different_entries():
    tc = TokenCache()
    call_count = [0]

    @tc.cached("multi", category="default")
    def fn(x: int) -> int:
        call_count[0] += 1
        return x

    tc.delete("multi:1")
    tc.delete("multi:2")
    fn(1)
    fn(2)
    fn(1)  # cache hit
    assert call_count[0] == 2  # only 2 unique calls


def test_cache_ttl_constants_complete():
    required = {"coin_detail", "market_data", "trending", "ohlc",
                "holders", "contract", "honeypot", "defi_tvl", "default"}
    assert required.issubset(set(CACHE_TTL.keys()))
    assert all(v > 0 for v in CACHE_TTL.values())


if __name__ == "__main__":
    test_retry_succeeds_on_first_try()
    test_retry_retries_and_succeeds()
    test_retry_reraises_after_exhaustion()
    test_retry_does_not_catch_unlisted_exception()
    test_retry_zero_retries()
    test_memory_cache_set_get()
    test_memory_cache_miss()
    test_memory_cache_ttl_expiry()
    test_memory_cache_delete()
    test_memory_cache_clear()
    test_token_cache_set_get()
    test_token_cache_miss_returns_none()
    test_token_cache_decorator_function()
    test_token_cache_decorator_method()
    test_token_cache_different_args_different_entries()
    test_cache_ttl_constants_complete()
    print("All utils tests passed!")
